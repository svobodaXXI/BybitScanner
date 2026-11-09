"""Regression: real Scanner wedge functions in one-symbol read-only SIMULATION."""
import unittest
from decimal import Decimal
from unittest.mock import patch

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_exchange import MarketRequest
from research.simulator_v2.wedge_observer import WedgeScannerConfig, ReadOnlyWedgeScanner

D = Decimal


def bar(i: int) -> Candle:
    return Candle(
        start_ms=i * MINUTE_MS, interval_ms=MINUTE_MS,
        open=D("100"), high=D("101"), low=D("99"),
        close=D("100"), volume=D("2"),
    )


def new_session(*, run="wedge", balance="1000"):
    return VirtualReplaySession(
        simulation_run_id=run, symbol="BTCUSDT",
        initial_balance=D(balance),
        wedge_scanner_config=WedgeScannerConfig(
            window_bars=50, mode="hunter", min_score=50,
        ),
    )


class ActualWedgeObserverTests(unittest.TestCase):
    def test_exactly_closed_5m_only_and_no_paper_or_robot_side_effects(self):
        session = new_session()
        self.assertIsInstance(session.wedge_scanner, ReadOnlyWedgeScanner)
        for i in range(249):
            session.step(bar(i))
        self.assertEqual(session.wedge_scanner.closed_m5_count, 49)
        self.assertEqual(session.wedge_scanner.observations, ())
        self.assertEqual(session.account.fills, ())
        # Only at the fiftieth full M5 close can the scanner inspect 50 bars.
        with patch("pivots.find_pivots", return_value=([], [])) as pivot:
            session.step(bar(249))
            self.assertEqual(pivot.call_count, 1)
            df = pivot.call_args.args[0]
            self.assertEqual(len(df), 50)
            self.assertEqual(df["time"].iloc[-1], 49 * 300_000)
            self.assertEqual(df["close"].iloc[-1], 100.0)
        self.assertEqual(session.wedge_scanner.closed_m5_count, 50)
        self.assertEqual(session.wedge_scanner.observations, ())
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.events, ())
        self.assertTrue(all(e.source == "MARKET" for e in session.events))
        self.assertEqual(sum(e.kind == "M5_CLOSED" for e in session.events), 50)

    def test_uses_original_scanner_confirmation_score_quality_and_filter(self):
        session = new_session(run="original")
        for i in range(249):
            session.step(bar(i))
        result = {
            "pattern": "Falling Wedge", "score": 80,
            "geometry": {
                "upper_line": {"slope": -0.1, "intercept": 120, "anchor_index": 10},
                "lower_line": {"slope": -0.05, "intercept": 110, "anchor_index": 12},
                "apex": {"index": 220, "valid_intersection": True},
                "current_index": 49,
                "validation": {"valid": True},
                "compression": {"compression_percent": 20},
                "touches": {"total_touches": 5},
            },
            "detection": {"features": {"containment_violations": None}},
        }
        # Freeze just the original detector's RESULT. The genuine downstream
        # scoring, quality, filter and 1m projection still run unchanged.
        with patch("pivots.find_pivots", return_value=(
            [{"index": i, "price": float(i), "type": "high"} for i in (2, 10, 30)],
            [{"index": i, "price": float(i), "type": "low"} for i in (3, 12, 32)],
        )), patch("wedge.analyze_wedge", return_value=result), patch(
            "confirmation.confirm_signal", return_value={
                "breakout": True, "volume": True, "retest": True,
                "confirmed": True, "confirmation_score": 25,
            }
        ):
            session.step(bar(249))
        actual, = session.wedge_scanner.observations
        self.assertEqual(actual.pattern, "Falling Wedge")
        self.assertEqual(actual.available_at_ms, 250 * MINUTE_MS)
        self.assertEqual(actual.source_candle_start_ms, 49 * 300_000)
        self.assertEqual(actual.formation_id, f"{10*300_000}:{12*300_000}")
        self.assertEqual(actual.final_score, 100)
        self.assertEqual(actual.quality, "Elite Setup")
        self.assertTrue(actual.scanner_filter_approved)
        self.assertTrue(actual.robot_geometry_ready)
        self.assertEqual(actual.robot_geometry["robot_coordinate_timeframe"], "1")
        self.assertEqual(actual.robot_geometry["current_index"], 49)
        self.assertEqual(actual.robot_geometry["upper_line"]["slope"], -0.02)
        self.assertEqual(session.wedge_scanner.observations_at(249 * MINUTE_MS), ())
        self.assertEqual(session.wedge_scanner.observations_at(250 * MINUTE_MS), (actual,))
        self.assertEqual(session.account.fills, ())
        self.assertFalse(any(e.source == "SCANNER" for e in session.events))

    def test_failed_exchange_minute_cannot_publish_or_duplicate_wedge(self):
        session = new_session(run="refill", balance="1")
        for i in range(249):
            session.step(bar(i))
        session.submit(MarketRequest("oversized", "BUY", D("1")))
        with self.assertRaises(StepBlocked):
            session.step(bar(249))
        self.assertEqual(session.wedge_scanner.closed_m5_count, 49)
        self.assertEqual(session.wedge_scanner.observations, ())
        self.assertEqual(session.virtual_time_ms, 249 * MINUTE_MS)
        session.cancel_pending("oversized")
        session.resume()
        session.step(bar(249))
        self.assertEqual(session.wedge_scanner.closed_m5_count, 50)
        self.assertEqual(session.wedge_scanner.observations, ())
        self.assertEqual(session.account.fills, ())
        self.assertEqual(sum(e.kind == "M5_CLOSED" for e in session.events), 50)

    def test_config_is_explicit_and_default_has_no_scanner(self):
        with self.assertRaises(ValueError):
            WedgeScannerConfig(window_bars=49, mode="hunter", min_score=50)
        with self.assertRaises(ValueError):
            WedgeScannerConfig(window_bars=50, mode="live", min_score=50)
        with self.assertRaises(ValueError):
            WedgeScannerConfig(window_bars=50, mode="hunter", min_score=float("nan"))
        default = VirtualReplaySession(
            simulation_run_id="empty", symbol="BTCUSDT", initial_balance=D("100"),
        )
        self.assertIsNone(default.wedge_scanner)
        self.assertIsNone(default.timeline._stages[0][1])


if __name__ == "__main__":
    unittest.main()
