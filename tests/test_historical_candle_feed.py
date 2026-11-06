"""Pure historical Bybit pagination and CLOSED higher-timeframe replay checks."""
from decimal import Decimal
import unittest

from research.historical_candle_feed import (
    ClosedHigherTimeframeFeed, FIVE_MINUTES_MS, ONE_HOUR_MS,
    load_closed_five_minute_history, replay_with_closed_context,
)
from research.historical_market_replay import Candle, EntryIntent


def bar(index: int, *, close=100) -> Candle:
    t = index * FIVE_MINUTES_MS
    return Candle(t, FIVE_MINUTES_MS, 100, 102, 98, close, 3)


def fake_exchange(rows, *, omit=None):
    calls = []

    def fetch(symbol, interval, limit, *, end_ms):
        assert symbol == "BTCUSDT" and interval == "5"
        calls.append(end_ms)
        available = [
            r for r in rows if int(r["time"]) <= end_ms
            and int(r["time"]) != omit
        ]
        return list(reversed(available[-limit:]))

    return fetch, calls


def rows(indices):
    return [
        dict(time=i * FIVE_MINUTES_MS, open="100", high="102",
             low="98", close="100", volume="3")
        for i in indices
    ]


class HistoricalCandleFeedTests(unittest.TestCase):
    def test_closed_history_paginates_without_network_or_future_bars(self):
        fetch, calls = fake_exchange(rows(range(8)))
        candles = load_closed_five_minute_history(
            symbol="BTCUSDT", start_ms=0, end_ms=5 * FIVE_MINUTES_MS,
            fetch_candles=fetch, page_limit=2,
        )
        self.assertEqual([x.start_ms for x in candles], [
            i * FIVE_MINUTES_MS for i in range(5)
        ])
        self.assertGreater(len(calls), 1)
        self.assertEqual(calls[0], 5 * FIVE_MINUTES_MS - 1)
        self.assertTrue(all(x.end_ms <= 5 * FIVE_MINUTES_MS for x in candles))

    def test_missing_bar_and_nonprogressing_history_fail_closed(self):
        fetch, _ = fake_exchange(rows(range(5)), omit=2 * FIVE_MINUTES_MS)
        with self.assertRaisesRegex(ValueError, "missing historical"):
            load_closed_five_minute_history(
                symbol="BTCUSDT", start_ms=0,
                end_ms=5 * FIVE_MINUTES_MS, fetch_candles=fetch,
                page_limit=2,
            )

        def stalled(_symbol, _interval, _limit, *, end_ms):
            return rows([999])
        with self.assertRaisesRegex(ValueError, "pagination did not advance"):
            load_closed_five_minute_history(
                symbol="BTCUSDT", start_ms=0,
                end_ms=5 * FIVE_MINUTES_MS, fetch_candles=stalled,
            )

    def test_h1_h4_are_not_visible_before_their_last_constituent_close(self):
        feed = ClosedHigherTimeframeFeed()
        records = [feed.observe_closed_five_minute(bar(i)) for i in range(49)]
        self.assertIsNone(records[10][0])  # 55 min, no closed 1h
        self.assertIsNone(records[46][1])  # 235 min, no closed 4h
        self.assertEqual(records[11][0].end_ms, 3_600_000)
        self.assertEqual(records[47][1].end_ms, 14_400_000)
        self.assertEqual(records[47][2].end_ms, 14_400_000)
        self.assertEqual(records[47][3].end_ms, 14_400_000)
        self.assertEqual(records[48][1].end_ms, 14_400_000)
        self.assertIsNone(records[48][3])

    def test_missing_constituent_never_publishes_incomplete_h4(self):
        feed = ClosedHigherTimeframeFeed()
        last = None
        for i in range(48):
            if i != 3:
                last = feed.observe_closed_five_minute(bar(i))
        self.assertIsNone(last[1])   # first H4 is incomplete
        self.assertIsNone(last[3])   # no new H4 close
        self.assertIsNotNone(last[0])  # last H1 is complete (hour 3)

    def test_higher_context_strategy_fills_at_next_five_minute_open(self):
        views = []

        def strategy(view):
            views.append((
                view.five_minute.signal_time_ms,
                view.last_closed_1h is not None,
                view.last_closed_4h is not None,
            ))
            if view.newly_closed_1h is not None:
                return EntryIntent("LONG", Decimal(1), Decimal(95), Decimal(108))
            return None

        result = replay_with_closed_context(
            simulation_run_id="context-a",
            candles=[bar(i) if i != 12 else Candle(12 * FIVE_MINUTES_MS, FIVE_MINUTES_MS, 100, 102, 94, 100, 3) for i in range(13)],
            on_closed_context=strategy,
            taker_fee_rate=Decimal(0),
        )
        self.assertEqual(views[10][1:], (False, False))
        self.assertEqual(views[11][1:], (True, False))
        self.assertEqual(views[12][1:], (True, False))
        self.assertEqual(result.trades[0].entry_time_ms, 12 * FIVE_MINUTES_MS)
        self.assertEqual(result.trades[0].exit_reason, "STOP")
        self.assertEqual(result.trades[0].source, "SIMULATION")


    def test_blue_retirement_uses_exported_version_after_h1_revision(self):
        """Same M5 correction + revised H1 must survive JSON identity validation."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from research.causal_trend_geometry import CausalLine, ConfirmedPivot
        from research.export_historical_replay import build_market_only_document

        t0 = 8 * ONE_HOUR_MS
        bars = [
            Candle(t0, FIVE_MINUTES_MS, 100, 101, 99, 100, 3),
            Candle(t0 + FIVE_MINUTES_MS, FIVE_MINUTES_MS, 100, 101, 99, 100, 3),
            Candle(t0 + 2 * FIVE_MINUTES_MS, FIVE_MINUTES_MS, 110, 111, 109, 110, 3),
        ]
        # Fixture carries genuine time-ordered four-pivot identities: fitting
        # points may differ, but a published line cannot invent source swings.
        h1_pivots = (
            ConfirmedPivot("LOW", 1, ONE_HOUR_MS, 4 * ONE_HOUR_MS, Decimal(90)),
            ConfirmedPivot("HIGH", 2, 2 * ONE_HOUR_MS, 5 * ONE_HOUR_MS, Decimal(120)),
            ConfirmedPivot("LOW", 3, 3 * ONE_HOUR_MS, 6 * ONE_HOUR_MS, Decimal(91)),
            ConfirmedPivot("HIGH", 4, 4 * ONE_HOUR_MS, 7 * ONE_HOUR_MS, Decimal(121)),
        )
        main = CausalLine(h1_pivots[0], h1_pivots[2], t0 + FIVE_MINUTES_MS)
        target = CausalLine(h1_pivots[1], h1_pivots[3], t0 + FIVE_MINUTES_MS)
        blue_pivots = (
            ConfirmedPivot("HIGH", 1, t0 - 7 * FIVE_MINUTES_MS,
                           t0 - 6 * FIVE_MINUTES_MS, Decimal(105)),
            ConfirmedPivot("LOW", 2, t0 - 6 * FIVE_MINUTES_MS,
                           t0 - 5 * FIVE_MINUTES_MS, Decimal(100)),
            ConfirmedPivot("HIGH", 3, t0 - 5 * FIVE_MINUTES_MS,
                           t0 - 4 * FIVE_MINUTES_MS, Decimal(104)),
            ConfirmedPivot("LOW", 4, t0 - 4 * FIVE_MINUTES_MS,
                           t0 - 3 * FIVE_MINUTES_MS, Decimal(99)),
        )
        blue = CausalLine(blue_pivots[0], blue_pivots[2], t0 + FIVE_MINUTES_MS)
        h1_first = t0 + FIVE_MINUTES_MS
        h1_revised = t0 + 2 * FIVE_MINUTES_MS
        trends = [
            SimpleNamespace(side="BULL", main=main, target=target,
                            pivot_sequence=h1_pivots, available_at_ms=h1_first),
            SimpleNamespace(side="BULL", main=main, target=target,
                            pivot_sequence=h1_pivots, available_at_ms=h1_revised),
        ]

        def replay_fixture(**kwargs):
            for i, candle in enumerate(bars):
                trend = trends[0] if i == 0 else trends[1]
                snapshot = SimpleNamespace(
                    time_ms=candle.end_ms, plus_di=None, minus_di=None,
                    adx=None, crossings=())
                view = SimpleNamespace(
                    five_minute=SimpleNamespace(
                        bar=candle, signal_time_ms=candle.end_ms),
                    dmi_5m=snapshot, hourly_trend=trend,
                    reference_5m=blue if i < 2 else None,
                    reference_5m_pivots=blue_pivots if i < 2 else None,
                    acceleration_5m=None, acceleration_5m_pivots=None,
                    hourly_prior_price=main.second.price,
                    hourly_prior_touch_ms=main.second.at_ms)
                kwargs["on_closed_context"](view)
                kwargs["on_visual_event"](
                    SimpleNamespace(to_payload=lambda: {"kind": "CANDLE_CLOSED"}))
            return SimpleNamespace(trades=(), open_position=None)

        with (
            patch("research.export_historical_replay.load_closed_five_minute_history",
                  return_value=tuple(bars)),
            patch("research.export_historical_replay.replay_with_closed_context",
                  side_effect=replay_fixture),
            patch("research.export_historical_replay.blue_open_risk_preview",
                  return_value=None),
        ):
            doc = build_market_only_document(
                symbol="BTCUSDT", start_ms=t0,
                end_ms=t0 + len(bars) * FIVE_MINUTES_MS,
                run_id="h1_revision_test", fetch_candles=lambda *a, **k: None)

        self.assertEqual(len(doc["hourly_prior_updates"]), 1)
        self.assertEqual(doc["hourly_prior_updates"][0]["price"], "91")
        self.assertEqual(doc["hourly_prior_updates"][0]["at_ms"],
                         main.second.at_ms)
        published = [item for item in doc["geometry"]
                     if item["kind"] == "REFERENCE_5M"]
        self.assertEqual(len(published), 2)
        self.assertEqual([item["trend_version"] for item in published],
                         [h1_first, h1_revised])
        retired = doc["reference_5m_retirements"]
        self.assertEqual(len(retired), 1)
        self.assertEqual(retired[0]["blue_available_at_ms"], h1_revised)
        self.assertEqual(retired[0]["trend_version"], h1_revised)
        self.assertEqual(
            [(item["available_at_ms"], item["trend_version"])
             for item in published
             if item["available_at_ms"] == retired[0]["blue_available_at_ms"]
             and item["trend_version"] == retired[0]["trend_version"]],
            [(h1_revised, h1_revised)],
        )
        self.assertEqual(doc["mode"], "MARKET_ONLY")
        self.assertEqual(len(doc["events"]), 3)


if __name__ == "__main__":
    unittest.main()
