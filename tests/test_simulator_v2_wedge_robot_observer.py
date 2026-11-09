"""Original Robot wedge breakout/retest and read-only LIMIT planning on virtual M1.

Fixtures inject an already-observed Scanner wedge; they do NOT claim the
pattern was found in real Bybit data or that a virtual LIMIT has filled.
"""
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from research.historical_market_replay import Candle
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_exchange import MarketRequest
from research.simulator_v2.wedge_observer import WedgeObservation, WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig

D = Decimal
M5_MS = 5 * MINUTE_MS


def bar(i: int, *, closing="100", low="99", high="101") -> Candle:
    close = D(closing)
    return Candle(
        start_ms=i * MINUTE_MS, interval_ms=MINUTE_MS,
        open=close, high=max(D(high), close), low=min(D(low), close),
        close=close, volume=D("1"),
    )


def fake_wedge(frame, pattern: str = "Falling Wedge", approved=True) -> WedgeObservation:
    # Frozen 1m coordinates and source M5: this is a controlled test fixture.
    geometry = {
        "upper_line": {"slope": 0.0, "intercept": 100.0 if pattern == "Falling Wedge" else 105.0},
        "lower_line": {"slope": 0.0, "intercept": 95.0 if pattern == "Falling Wedge" else 100.0},
        "apex": {"index": 200, "valid_intersection": True},
        "current_index": 49,
        "robot_coordinate_timeframe": "1",
    }
    return WedgeObservation(
        simulation_run_id=frame.simulation_run_id,
        symbol=frame.symbol,
        source_candle_start_ms=frame.newly_closed_5m.start_ms,
        available_at_ms=frame.virtual_time_ms,
        pattern=pattern, formation_id=f"{30*M5_MS}:{35*M5_MS}",
        final_score=80, quality="A Setup",
        scanner_filter_approved=approved, scanner_filter_reason="approved",
        robot_geometry_ready=True, robot_geometry=geometry,
    )


def make_session(*, run="simtest", selected=None, balance="1000"):
    return VirtualReplaySession(
        simulation_run_id=run, symbol="BTCUSDT",
        initial_balance=D(balance), wedge_scanner_config=WedgeScannerConfig(
            window_bars=50, mode="hunter", min_score=50,
        ),
        wedge_robot_config=SimWedgeRobotConfig(
            selected_patterns=frozenset(selected or {"Falling Wedge", "Rising Wedge"}),
            tick_size=D("0.01"),
        ),
    )


def seed_50_m5(session, pattern="Falling Wedge", approved=True):
    for i in range(249):
        session.step(bar(i))
    with patch.object(session.wedge_scanner, "_evaluate",
                      side_effect=lambda *, frame, bars: fake_wedge(frame, pattern, approved)):
        session.step(bar(249))


class PureWedgeRobotTests(unittest.TestCase):
    def test_original_fsm_and_original_limit_planner_for_both_wedge_directions(self):
        for pattern, opening, retest, side, expected_price in [
            ("Falling Wedge", "102", "101", "BUY", D("100.02")),
            ("Rising Wedge", "98", "99", "SELL", D("99.98")),
        ]:
            with self.subTest(pattern=pattern):
                session = make_session(run=pattern.replace(" ", ""))
                seed_50_m5(session, pattern)
                self.assertEqual(len(session.wedge_robot.decisions), 1)
                self.assertEqual(session.wedge_robot.decisions[0].event, "INITIALIZED")
                self.assertEqual(session.wedge_robot.active_count, 1)
                self.assertEqual(session.account.fills, ())
                session.step(bar(250, closing=opening, low="97", high="103"))
                session.step(bar(251, closing=retest, low="99", high="101"))
                self.assertEqual(
                    [d.event for d in session.wedge_robot.decisions],
                    ["INITIALIZED", "BREAKOUT", "RETEST"],
                )
                self.assertEqual(session.wedge_robot.active_count, 0)
                plan, = session.wedge_robot.limit_plans
                self.assertEqual(plan.request.side.value, side)
                self.assertEqual(plan.request.limit_price, expected_price)
                self.assertEqual(plan.request.volume.amount, D("1"))
                self.assertEqual(plan.request.symbol, "BTCUSDT")
                self.assertEqual(session.account.fills, ())
                self.assertEqual(session.exchange.events, ())
                self.assertTrue(all(
                    event.kind.startswith("SIM_WEDGE_")
                    for event in session.events if event.source == "ROBOT"
                ))
                self.assertTrue(any(
                    event.kind == "SIM_WEDGE_LIMIT_PLANNED"
                    and dict(event.details)["note"] == "NOT_SUBMITTED"
                    for event in session.events
                ))

    def test_selected_pattern_and_scanner_filter_are_strict(self):
        for pattern, approved in (("Rising Wedge", True), ("Falling Wedge", False)):
            with self.subTest(pattern=pattern, approved=approved):
                session = make_session(selected={"Falling Wedge"})
                seed_50_m5(session, pattern=pattern, approved=approved)
                self.assertEqual(session.wedge_robot.decisions, ())
                self.assertEqual(session.wedge_robot.limit_plans, ())
                self.assertEqual(session.wedge_robot.active_count, 0)

    def test_failed_exchange_discards_scanner_and_robot_staging(self):
        session = make_session(run="rollback", balance="0.01")
        for i in range(249):
            session.step(bar(i))
        session.submit(MarketRequest("unfunded", "BUY", D("1")))
        with patch.object(session.wedge_scanner, "_evaluate",
                          side_effect=lambda *, frame, bars: fake_wedge(frame)):
            with self.assertRaises(StepBlocked):
                session.step(bar(249))
            self.assertEqual(session.timeline.paused_stage, "EXCHANGE")
            self.assertEqual(session.wedge_scanner.observations, ())
            self.assertEqual(session.wedge_robot.decisions, ())
            self.assertEqual(session.wedge_robot.limit_plans, ())
            self.assertEqual(session.wedge_robot.active_count, 0)
            self.assertEqual(session.virtual_time_ms, 249 * MINUTE_MS)
            session.cancel_pending("unfunded")
            session.resume()
            session.step(bar(249))
        self.assertEqual(len(session.wedge_robot.decisions), 1)
        self.assertEqual(session.wedge_robot.active_count, 1)
        self.assertEqual(len(session.wedge_scanner.observations), 1)
        self.assertEqual(session.account.fills, ())

    def test_formation_identity_deduplicated_across_later_scanner_pass(self):
        session = make_session(run="dedup")
        seed_50_m5(session)
        self.assertEqual(len(session.wedge_robot.decisions), 1)
        for i in range(250, 254):
            session.step(bar(i, closing="100"))
        with patch.object(session.wedge_scanner, "_evaluate",
                          side_effect=lambda *, frame, bars: fake_wedge(frame)):
            session.step(bar(254))
        self.assertEqual(
            sum(dec.event == "INITIALIZED" for dec in session.wedge_robot.decisions), 1,
        )
        self.assertEqual(session.wedge_robot.limit_plans, ())
        self.assertEqual(session.account.fills, ())

    def test_robot_is_explicit_opt_in_and_configuration_fails_closed(self):
        default = VirtualReplaySession(
            simulation_run_id="default", symbol="BTCUSDT", initial_balance=D("1000"),
            wedge_scanner_config=WedgeScannerConfig(
                window_bars=50, mode="hunter", min_score=50,
            ),
        )
        self.assertIsNone(default.wedge_robot)
        with self.assertRaises(ValueError):
            VirtualReplaySession(
                simulation_run_id="bad", symbol="BTCUSDT", initial_balance=D("1000"),
                wedge_robot_config=SimWedgeRobotConfig(
                    selected_patterns=frozenset({"Falling Wedge"}), tick_size=D("0.01"),
                ),
            )
        with self.assertRaises(ValueError):
            SimWedgeRobotConfig(
                selected_patterns=frozenset({"Triangle Compression"}), tick_size=D("0.01"),
            )
        with self.assertRaises(ValueError):
            SimWedgeRobotConfig(
                selected_patterns=frozenset({"Rising Wedge"}), tick_size=D("-1"),
            )


if __name__ == "__main__":
    unittest.main()
