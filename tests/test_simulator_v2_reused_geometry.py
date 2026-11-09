"""Prove reuse of the real, pure H1/M5 geometry with virtual M1 clock.

No production Scanner/Robot import, exchange credentials, H-017 mutation or
simulated trading strategy. The original CausalGeometryFeed is the oracle.
"""
import unittest
from decimal import Decimal

from research.causal_trend_geometry import CausalGeometryFeed
from research.historical_candle_feed import ClosedHigherTimeframeFeed
from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_exchange import MarketRequest

D = Decimal
FIVE_M1 = 5 * MINUTE_MS


def bar(i: int) -> Candle:
    # Explicit bounded fixture; deterministic and valid, not Bybit price data.
    opening = D("100") + D((i // 7) % 10)
    closing = D("100") + D((i // 7 + 1) % 10)
    return Candle(
        start_ms=i * MINUTE_MS, interval_ms=MINUTE_MS,
        open=opening, high=max(opening, closing) + D("1"),
        low=min(opening, closing) - D("1"),
        close=closing, volume=D("2"),
    )


def five_bar(group: list[Candle]) -> Candle:
    return Candle(
        start_ms=group[0].start_ms,
        interval_ms=FIVE_M1,
        open=group[0].open, high=max(item.high for item in group),
        low=min(item.low for item in group),
        close=group[-1].close,
        volume=sum((item.volume for item in group), D("0")),
    )


def instance(run_id="geometry", **kwargs) -> VirtualReplaySession:
    return VirtualReplaySession(
        simulation_run_id=run_id, symbol="BTCUSDT",
        initial_balance=D("1000"), enable_reused_geometry=True, **kwargs,
    )


class ReusedGeometryTests(unittest.TestCase):
    def test_replays_actual_existing_geometry_on_only_closed_m5_and_h1(self):
        session = instance()
        expected = CausalGeometryFeed()
        higher = ClosedHigherTimeframeFeed()
        minute_bars: list[Candle] = []
        expected_count = 0
        for i in range(125):
            minute = bar(i)
            minute_bars.append(minute)
            balance = session.step(minute)
            self.assertEqual(balance.position_quantity, D("0"))
            self.assertEqual(balance.balance, D("1000"))
            self.assertEqual(len(session.reused_geometry.snapshots), (i + 1) // 5)
            if (i + 1) % 5:
                continue
            new_m5 = five_bar(minute_bars[-5:])
            _, _, new_h1, _ = higher.observe_closed_five_minute(new_m5)
            actual_trend, actual_corr = expected.observe_closed(new_m5, new_h1)
            last = session.reused_geometry.snapshots[-1]
            self.assertEqual(last.h1_trend, actual_trend)
            self.assertEqual(last.m5_correction, actual_corr)
            self.assertEqual(last.confirmed_hourly_prior,
                             expected.confirmed_hourly_prior)
            self.assertEqual(last.virtual_time_ms, minute.end_ms)
            expected_count += 1
        self.assertEqual(expected_count, 25)
        self.assertTrue(any(e.kind == "H1_CLOSED" for e in session.events))
        # Distinguish a reusable RESEARCH algorithm from actual production Scanner.
        self.assertTrue(all(e.source == "MARKET" for e in session.events))
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.events, ())

    def test_rejected_virtual_fill_discards_geometry_preparation_and_retries_once(self):
        session = instance("rejected", taker_fee_rate=D("0.1"))
        # Fee = 10 for quantity one and price 100, but deposit will be one:
        # For this regression explicitly use a separate low-deposit session.
        session = VirtualReplaySession(
            simulation_run_id="rejected", symbol="BTCUSDT",
            initial_balance=D("1"), taker_fee_rate=D("0.1"),
            enable_reused_geometry=True,
        )
        for i in range(4):
            session.step(bar(i))
        self.assertEqual(session.reused_geometry.snapshots, ())
        session.submit(MarketRequest("unfunded", "BUY", D("1")))
        with self.assertRaises(StepBlocked):
            session.step(bar(4))  # M5 would close, but exchange rejects fee.
        self.assertEqual(session.virtual_time_ms, 4 * MINUTE_MS)
        self.assertEqual(session.reused_geometry.snapshots, ())
        self.assertEqual(session.account.fills, ())
        self.assertIsNone(session.reused_geometry.projection_at(5 * MINUTE_MS))
        self.assertEqual(sum(e.kind == "M5_CLOSED" for e in session.events), 0)
        session.cancel_pending("unfunded")
        session.resume()
        session.step(bar(4))
        self.assertEqual(len(session.reused_geometry.snapshots), 1)
        self.assertEqual(session.reused_geometry.snapshots[0].virtual_time_ms,
                         5 * MINUTE_MS)
        self.assertEqual(sum(e.kind == "M5_CLOSED" for e in session.events), 1)
        self.assertEqual(session.account.fills, ())

    def test_rewind_changes_only_projection_and_not_live_state(self):
        session = instance("rewind")
        for i in range(15):
            session.step(bar(i))
        frozen = session.reused_geometry.snapshots
        journal = session.events
        as_of_ten = session.reused_geometry.projection_at(10 * MINUTE_MS)
        self.assertEqual(as_of_ten, frozen[1])
        self.assertIsNone(session.reused_geometry.projection_at(4 * MINUTE_MS))
        self.assertEqual(session.reused_geometry.projection_at(15 * MINUTE_MS),
                         frozen[-1])
        self.assertEqual(session.reused_geometry.snapshots, frozen)
        self.assertEqual(session.events, journal)
        self.assertEqual(session.virtual_time_ms, 15 * MINUTE_MS)
        with self.assertRaises(ValueError):
            session.reused_geometry.projection_at(-1)

    def test_default_off_and_no_implicit_trading(self):
        default = VirtualReplaySession(
            simulation_run_id="default", symbol="BTCUSDT", initial_balance=D("1000"),
        )
        self.assertIsNone(default.reused_geometry)
        self.assertIsNone(default.timeline._stages[0][1])
        with self.assertRaises(TypeError):
            VirtualReplaySession(
                simulation_run_id="wrong", symbol="BTCUSDT",
                initial_balance=D("1000"), enable_reused_geometry="yes",
            )


if __name__ == "__main__":
    unittest.main()
