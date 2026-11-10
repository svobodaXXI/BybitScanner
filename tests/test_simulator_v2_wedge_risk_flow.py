"""Native frozen Wedge risk lineage, virtual Robot preflight and rollback.

These tests do NOT equate a risk preview to an admitted order or a traded PnL.
No production PAPER process/store and no network calls are involved.
"""
import unittest
from dataclasses import replace
from decimal import Decimal as D
from unittest.mock import patch

from robot_protection import (
    RobotProtectionError, wedge_frozen_reference_target,
    wedge_structural_extreme,
)
from research.simulator_v2.session import VirtualReplaySession
from research.simulator_v2.timeline import MINUTE_MS, StepBlocked
from research.simulator_v2.virtual_exchange import MarketRequest
from research.simulator_v2.wedge_observer import WedgeScannerConfig
from research.simulator_v2.wedge_robot_observer import SimWedgeRobotConfig
from research.simulator_v2.wedge_risk_preflight import SimWedgeRiskSettings
from tests.test_simulator_v2_wedge_robot_observer import bar, fake_wedge


def frozen_snapshot():
    return {
        "geometry": {
            "touches": {
                "lower_touch_points": [
                    {"price": 99.7, "counted": True},
                    {"price": 80, "counted": False},
                    {"price": 99.5, "counted": True},
                ],
                "upper_touch_points": [
                    {"price": 100.4, "counted": True},
                    {"price": 130, "counted": False},
                    {"price": 100.2, "counted": True},
                ],
            },
            "pair_metrics": {"reference_price": 100, "start_width": 5},
        },
    }


def risk_settings():
    return SimWedgeRiskSettings(
        tick_size=D("0.01"),
        contracts_per_working_volume=D("1"),
        quantity_step=D("0.01"), minimum_quantity=D("0.01"),
        max_notional_usdt=D("200"), max_risk_usdt=D("5"),
        entry_fee_rate=D("0.0006"), exit_fee_rate=D("0.0006"),
    )


def make_session(*, run="wedge-risk", balance="1000", settings=None):
    return VirtualReplaySession(
        simulation_run_id=run, symbol="BTCUSDT",
        initial_balance=D(balance),
        wedge_scanner_config=WedgeScannerConfig(
            window_bars=50, mode="hunter", min_score=50,
        ),
        wedge_robot_config=SimWedgeRobotConfig(
            selected_patterns=frozenset({"Falling Wedge", "Rising Wedge"}),
            tick_size=D("0.01"),
        ),
        wedge_risk_settings=risk_settings() if settings is None else settings,
    )


def seed(session, *, pattern="Falling Wedge", frozen=True):
    for i in range(249):
        session.step(bar(i))

    def detector(*, frame, bars):
        raw = fake_wedge(frame, pattern)
        if not frozen:
            return raw
        source = frozen_snapshot()
        direction = "LONG" if pattern == "Falling Wedge" else "SHORT"
        extreme = wedge_structural_extreme(source, direction)
        reference, target = wedge_frozen_reference_target(source, direction)
        return replace(
            raw, frozen_structural_extreme=extreme,
            frozen_reference_price=reference, frozen_target_price=target,
        )

    with patch.object(session.wedge_scanner, "_evaluate", side_effect=detector):
        session.step(bar(249))


class WedgeRiskSourceAndStageTests(unittest.TestCase):
    def test_native_robot_frozen_touch_and_target_are_shared_in_both_directions(self):
        source = frozen_snapshot()
        self.assertEqual(wedge_structural_extreme(source, "LONG"), D("99.5"))
        self.assertEqual(wedge_structural_extreme(source, "SHORT"), D("100.4"))
        self.assertEqual(wedge_frozen_reference_target(source, "LONG"), (D("100"), D("105")))
        self.assertEqual(wedge_frozen_reference_target(source, "SHORT"), (D("100"), D("95")))

    def test_missing_or_nonfinite_native_risk_inputs_are_blocked(self):
        for payload, direction in (
            ({"geometry": {"touches": {}, "pair_metrics": {"reference_price": 100, "start_width": 5}}}, "LONG"),
            ({"geometry": {"touches": {"lower_touch_points": [{"price": 90, "counted": False}]}}}, "LONG"),
            ({"geometry": {"touches": {"lower_touch_points": [{"price": "NaN", "counted": True}]}}}, "LONG"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(RobotProtectionError):
                    wedge_structural_extreme(payload, direction)
        for payload, direction in (
            ({"geometry": {"pair_metrics": {}}}, "SHORT"),
            ({"geometry": {"pair_metrics": {"reference_price": 100, "start_width": 0}}}, "LONG"),
            ({"geometry": {"pair_metrics": {"reference_price": 100, "start_width": "Infinity"}}}, "LONG"),
            ({"geometry": {"pair_metrics": {"reference_price": 1, "start_width": 5}}}, "SHORT"),
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(RobotProtectionError):
                    wedge_frozen_reference_target(payload, direction)

    def test_original_robot_retest_produces_both_protected_previews_without_trade(self):
        for pattern, opening, retest, side, stop, take in (
            ("Falling Wedge", "102", "101", "BUY", D("99.49"), D("104.5")),
            ("Rising Wedge", "98", "99", "SELL", D("100.41"), D("95.5")),
        ):
            with self.subTest(pattern=pattern):
                session = make_session(run=pattern.replace(" ", ""))
                seed(session, pattern=pattern)
                self.assertEqual(session.wedge_robot.risk_previews, ())
                session.step(bar(250, closing=opening, low="97", high="103"))
                session.step(bar(251, closing=retest, low="99", high="101"))
                self.assertFalse(
                    [dict(e.details) for e in session.events
                     if e.kind == "SIM_WEDGE_RISK_BLOCKED"],
                    "Native Wedge risk preflight blocked an otherwise complete test fixture",
                )
                preview, = session.wedge_robot.risk_previews
                self.assertEqual(preview.status, "PREVIEW_ONLY")
                self.assertEqual(preview.request.namespace, "SIMULATION")
                self.assertEqual(preview.request.side, side)
                self.assertEqual(preview.request.quantity, D("1"))
                self.assertEqual(preview.stop_price, stop)
                self.assertEqual(preview.take_price, take)
                self.assertGreater(preview.projected_net_rr, D("1.5"))
                self.assertEqual(len(session.wedge_robot.limit_plans), 1)
                risk_events = [
                    event for event in session.events
                    if event.source == "ROBOT" and event.kind == "SIM_WEDGE_RISK_PREVIEW"
                ]
                self.assertEqual(len(risk_events), 1)
                self.assertEqual(dict(risk_events[0].details)["note"], "PREVIEW_ONLY_NOT_SUBMITTED")
                self.assertEqual(session.account.fills, ())
                self.assertIsNone(session.exchange.pending)

    def test_missing_frozen_scanner_terms_at_retest_never_creates_preview(self):
        session = make_session(run="no-evidence")
        seed(session, frozen=False)
        session.step(bar(250, closing="102", low="97", high="103"))
        session.step(bar(251, closing="101", low="99", high="101"))
        self.assertEqual(session.wedge_robot.risk_previews, ())
        blockers = [
            event for event in session.events
            if event.source == "ROBOT" and event.kind == "SIM_WEDGE_RISK_BLOCKED"
        ]
        self.assertEqual(len(blockers), 1)
        self.assertIn("frozen Scanner", dict(blockers[0].details)["reason"])
        self.assertEqual(session.account.fills, ())
        self.assertEqual(session.exchange.events, ())

    def test_failed_exchange_cannot_publish_preflight_until_same_m1_retries(self):
        session = make_session(run="atomic-risk", balance="0.01")
        seed(session)
        session.step(bar(250, closing="102", low="97", high="103"))
        session.submit(MarketRequest("unfunded", "BUY", D("1")))
        with self.assertRaises(StepBlocked):
            session.step(bar(251, closing="101", low="99", high="101"))
        self.assertEqual(session.timeline.paused_stage, "EXCHANGE")
        self.assertEqual(session.wedge_robot.risk_previews, ())
        self.assertEqual(session.wedge_robot.limit_plans, ())
        self.assertEqual(session.account.fills, ())
        self.assertFalse(any(
            event.kind == "SIM_WEDGE_RISK_PREVIEW" for event in session.events
        ))
        session.cancel_pending("unfunded")
        session.resume()
        session.step(bar(251, closing="101", low="99", high="101"))
        self.assertFalse([dict(e.details) for e in session.events
                          if e.kind == "SIM_WEDGE_RISK_BLOCKED"])
        self.assertEqual(len(session.wedge_robot.risk_previews), 1)
        self.assertEqual(len(session.wedge_robot.limit_plans), 1)
        self.assertEqual(sum(
            event.kind == "SIM_WEDGE_RISK_PREVIEW" for event in session.events
        ), 1)
        self.assertEqual(session.account.fills, ())

    def test_opt_in_cannot_understate_actual_virtual_fee_rates(self):
        with self.assertRaisesRegex(ValueError, "fees"):
            make_session(settings=replace(risk_settings(), entry_fee_rate=D("0.0002")))
        with self.assertRaisesRegex(ValueError, "fees"):
            make_session(settings=replace(risk_settings(), exit_fee_rate=D("0.0002")))
        with self.assertRaisesRegex(ValueError, "tick"):
            make_session(settings=replace(risk_settings(), tick_size=D("0.05")))
        with self.assertRaisesRegex(ValueError, "requires explicit virtual Robot"):
            VirtualReplaySession(
                simulation_run_id="no-robot", symbol="BTCUSDT",
                initial_balance=D("1000"), wedge_risk_settings=risk_settings(),
            )


if __name__ == "__main__":
    unittest.main()
