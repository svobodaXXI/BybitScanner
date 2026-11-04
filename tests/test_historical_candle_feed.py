"""Pure historical Bybit pagination and CLOSED higher-timeframe replay checks."""
from decimal import Decimal
import unittest

from research.historical_candle_feed import (
    ClosedHigherTimeframeFeed, FIVE_MINUTES_MS,
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
            candles=[bar(i) for i in range(13)],
            on_closed_context=strategy,
            taker_fee_rate=Decimal(0),
        )
        self.assertEqual(views[10][1:], (False, False))
        self.assertEqual(views[11][1:], (True, False))
        self.assertEqual(views[12][1:], (True, False))
        self.assertEqual(result.trades[0].entry_time_ms, 12 * FIVE_MINUTES_MS)
        self.assertEqual(result.trades[0].exit_reason, "STOP")
        self.assertEqual(result.trades[0].source, "SIMULATION")


if __name__ == "__main__":
    unittest.main()
