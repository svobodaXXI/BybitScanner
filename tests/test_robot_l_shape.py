import unittest
from decimal import Decimal

import robot_l_shape
import robot_protection
import robot_state_machine
from robot_restart_recovery import RESUME_WAITING, reconcile_restart
from terminal.domain.models import OrderSide


def _snapshot(*, direction="LONG", reference="100", target="110", stop="96"):
    return {
        "pattern": "L-shape",
        "symbol": "TESTUSDT",
        "timeframe": "5",
        "scanner_source_timeframe": "5",
        "robot_handoff_ready": True,
        "l_shape": {
            "direction": direction,
            "source_timeframe": "5",
            "breakout_time_ms": 1_000_000,
            "extreme_time_ms": 900_000,
            "reference": reference,
            "target": target,
            "stop": stop,
            "stop_kind": "STRUCTURAL",
            "structural_stop": stop,
            "potential_percent": "10",
            "reward_risk": "2.5",
        },
    }


def _candidate(snapshot=None):
    return {
        "candidate_id": "candidate-lshape",
        "status": "APPROVED",
        "timeframe": "5",
        "signal_snapshot": snapshot or _snapshot(),
    }


class RobotLShapePolicyTests(unittest.TestCase):
    def test_horizontal_retest_builds_one_wv_limit_and_frozen_protection(self):
        candidate = _candidate()
        state, event = robot_l_shape.initialize_state(candidate)
        self.assertEqual(event, robot_l_shape.EVENT_INITIALIZED)
        self.assertEqual(state["phase"], robot_l_shape.PHASE_WAITING_RETEST)

        state, event = robot_l_shape.process_closed_candle(
            candidate["signal_snapshot"],
            state,
            {"time_ms": 1_060_000, "high": "101", "low": "99.5", "close": "100.4"},
        )
        self.assertEqual(event, robot_l_shape.EVENT_RETEST)
        self.assertEqual(state["phase"], robot_state_machine.PHASE_RETEST_DETECTED)

        plan = robot_l_shape.build_initial_retest_limit(
            candidate, state, tick_size=Decimal("0.1"),
        )
        self.assertEqual(plan.request.side, OrderSide.BUY)
        self.assertEqual(plan.request.limit_price, Decimal("100.2"))
        self.assertEqual(plan.request.volume.amount, Decimal("1"))

        protection = robot_protection.build_l_shape_protection_plan(
            candidate, state, average_entry=Decimal("100.2"),
        )
        self.assertEqual(protection.stop_price, Decimal("96"))
        self.assertEqual(protection.take_price, Decimal("110"))

    def test_target_or_stop_before_entry_invalidates_without_retest(self):
        candidate = _candidate()
        state, _ = robot_l_shape.initialize_state(candidate)

        target_state, target_event = robot_l_shape.process_closed_candle(
            candidate["signal_snapshot"],
            state,
            {"time_ms": 1_060_000, "high": "110", "low": "105", "close": "109"},
        )
        self.assertEqual(target_event, robot_l_shape.EVENT_INVALIDATED_TARGET)
        self.assertEqual(target_state["phase"], robot_l_shape.PHASE_INVALIDATED)

        stop_state, stop_event = robot_l_shape.process_closed_candle(
            candidate["signal_snapshot"],
            state,
            {"time_ms": 1_060_000, "high": "99", "low": "96", "close": "97"},
        )
        self.assertEqual(stop_event, robot_l_shape.EVENT_INVALIDATED_STOP)
        self.assertEqual(stop_state["phase"], robot_l_shape.PHASE_INVALIDATED)

    def test_restart_preserves_durable_l_shape_state_without_wedge_geometry(self):
        candidate = _candidate()
        state, _ = robot_l_shape.initialize_state(candidate)
        mode, decisions = reconcile_restart(
            durable_mode="ROBOT_RUNNING",
            open_robot_positions=(),
            approved_candidates=({
                "candidate_id": candidate["candidate_id"],
                "status": "APPROVED",
                "signal_snapshot": candidate["signal_snapshot"],
                "robot_state": state,
            },),
            latest_geometry_index_by_candidate={},
        )
        self.assertEqual(mode, "ROBOT_RUNNING")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0].status, RESUME_WAITING)
        self.assertEqual(decisions[0].state, state)

    def test_frozen_contract_rejects_signal_threshold_drift(self):
        below_potential = _snapshot()
        below_potential["l_shape"]["potential_percent"] = "0.79"
        with self.assertRaises(robot_l_shape.RobotLShapeError):
            robot_l_shape.frozen_terms(below_potential)

        below_rr = _snapshot()
        below_rr["l_shape"]["reward_risk"] = "1.99"
        with self.assertRaises(robot_l_shape.RobotLShapeError):
            robot_l_shape.frozen_terms(below_rr)


if __name__ == "__main__":
    unittest.main()
