from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from robot_restart_recovery import (
    EXPIRED_AT_APEX,
    RECONCILIATION_REQUIRED,
    RESUME_OPEN_POSITION,
    RESUME_WAITING,
    ROBOT_RUNNING,
    ROBOT_STOPPED,
    initial_robot_mode,
    reconcile_restart,
)
from robot_trade_store import create_trade_record, close_trade_record, load_trade_record, RobotTradeStoreError
from robot_state_machine import initialize_state, process_closed_candle


def _snapshot():
    return {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _candidate_with_state():
    candidate = {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "symbol": "TESTUSDT",
        "signal_snapshot": _snapshot(),
    }
    state, _ = initialize_state(candidate)
    candidate["robot_state"] = {**state, "revision": 1}
    return candidate


class RobotRestartRecoveryTests(unittest.TestCase):
    def test_first_run_defaults_to_stopped(self):
        self.assertEqual(initial_robot_mode(None), ROBOT_STOPPED)

    def test_stopped_with_surviving_position_requires_reconciliation(self):
        status, decisions = reconcile_restart(
            durable_mode=ROBOT_STOPPED,
            open_robot_positions=({"symbol": "TESTUSDT", "candidate_id": "candidate-1"},),
            approved_candidates=(),
            latest_geometry_index_by_symbol={},
        )
        self.assertEqual(status, RECONCILIATION_REQUIRED)
        self.assertEqual(decisions[0].status, RECONCILIATION_REQUIRED)

    def test_running_restores_open_position(self):
        status, decisions = reconcile_restart(
            durable_mode=ROBOT_RUNNING,
            open_robot_positions=({"symbol": "TESTUSDT", "candidate_id": "candidate-1"},),
            approved_candidates=(),
            latest_geometry_index_by_symbol={},
        )
        self.assertEqual(status, ROBOT_RUNNING)
        self.assertEqual(decisions[0].status, RESUME_OPEN_POSITION)

    def test_waiting_candidate_advances_cursor_without_replaying_breakout(self):
        candidate = _candidate_with_state()
        status, decisions = reconcile_restart(
            durable_mode=ROBOT_RUNNING,
            open_robot_positions=(),
            approved_candidates=(candidate,),
            latest_geometry_index_by_symbol={"TESTUSDT": 105},
        )
        self.assertEqual(status, ROBOT_RUNNING)
        decision = decisions[0]
        self.assertEqual(decision.status, RESUME_WAITING)
        self.assertEqual(decision.state["geometry_cursor"], 105)
        self.assertEqual(decision.state["phase"], "WAITING_BREAKOUT")

        missed_breakout = {
            "closed": True, "timeframe": "1", "geometry_index": 104,
            "high": 98, "low": 96, "close": 97,
        }
        replayed, event = process_closed_candle(candidate["signal_snapshot"], decision.state, missed_breakout)
        self.assertEqual(event, "IGNORED_STALE_CANDLE")
        self.assertEqual(replayed["phase"], "WAITING_BREAKOUT")

    def test_waiting_candidate_expires_if_downtime_reaches_apex(self):
        candidate = _candidate_with_state()
        status, decisions = reconcile_restart(
            durable_mode=ROBOT_RUNNING,
            open_robot_positions=(),
            approved_candidates=(candidate,),
            latest_geometry_index_by_symbol={"TESTUSDT": 110},
        )
        self.assertEqual(status, ROBOT_RUNNING)
        self.assertEqual(decisions[0].status, EXPIRED_AT_APEX)

    def test_trade_record_open_and_close_are_durable_and_close_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            created = create_trade_record(
                trade_id="trade-1", symbol="TESTUSDT", direction="LONG", pattern="Falling Wedge",
                source_timeframe="1", signal_time="2026-09-09T00:00:00Z", signal_snapshot_id="candidate-1",
                entry_time="2026-09-09T00:05:00Z", entry_path="LIMIT", actual_wv=Decimal("0.8"),
                average_entry=Decimal("100"), stop_price=Decimal("98"), take_price=Decimal("106"),
                store_dir=root,
            )
            self.assertEqual(created["actual_wv"], "0.8")
            self.assertIsNone(created["exit_time"])

            closed, changed = close_trade_record(
                "trade-1", exit_time="2026-09-09T01:00:00Z", exit_price=Decimal("106"),
                exit_reason="TAKE", realized_pnl_usdt=Decimal("12.5"), realized_pnl_pct=Decimal("6"),
                fees_costs_usdt=Decimal("0.4"), store_dir=root,
            )
            self.assertTrue(changed)
            self.assertEqual(closed["exit_reason"], "TAKE")
            replay, changed = close_trade_record(
                "trade-1", exit_time="2026-09-09T01:00:00Z", exit_price=Decimal("106"),
                exit_reason="TAKE", realized_pnl_usdt=Decimal("12.5"), realized_pnl_pct=Decimal("6"),
                fees_costs_usdt=Decimal("0.4"), store_dir=root,
            )
            self.assertFalse(changed)
            self.assertEqual(load_trade_record("trade-1", store_dir=root), replay)

    def test_trade_record_conflicting_second_close_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            create_trade_record(
                trade_id="trade-2", symbol="TESTUSDT", direction="SHORT", pattern="Rising Wedge",
                source_timeframe="1", signal_time="s", signal_snapshot_id="candidate-2", entry_time="e",
                entry_path="MIXED", actual_wv=Decimal("1"), average_entry=Decimal("100"),
                stop_price=Decimal("102"), take_price=Decimal("94"), store_dir=root,
            )
            close_trade_record(
                "trade-2", exit_time="x", exit_price=Decimal("94"), exit_reason="TAKE",
                realized_pnl_usdt=Decimal("10"), realized_pnl_pct=Decimal("6"), store_dir=root,
            )
            with self.assertRaisesRegex(RobotTradeStoreError, "different result"):
                close_trade_record(
                    "trade-2", exit_time="y", exit_price=Decimal("102"), exit_reason="STOP",
                    realized_pnl_usdt=Decimal("-4"), realized_pnl_pct=Decimal("-2"), store_dir=root,
                )


if __name__ == "__main__":
    unittest.main()
