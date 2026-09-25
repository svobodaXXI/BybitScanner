"""One isolated durable handoff check; no execution or prior PR test reruns."""
import tempfile
import unittest
from pathlib import Path

from robot_restart_recovery import reconcile_restart, RESUME_WAITING
from terminal.domain.models import Symbol
from terminal.persistence.sqlite_store import SQLiteStore, DuplicateIdentity, PersistenceError
from tests.test_box_plan_persistence import snapshot, ACCOUNT


class BoxRobotHandoffTests(unittest.TestCase):
    def test_durable_idempotent_linked_handoff_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.sqlite3"
            store = SQLiteStore.open(path)
            try:
                source, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
                args = dict(symbol=source.symbol, expected_snapshot_sha256=source.snapshot_sha256,
                            approved_at_ms=3002)
                with self.assertRaises(PersistenceError):
                    store.handoff_box_plan_to_robot("missing", **args)
                for overrides in ({"symbol": Symbol("ETHUSDT")}, {"expected_snapshot_sha256": "wrong"}):
                    with self.subTest(source_conflict=overrides), self.assertRaises(DuplicateIdentity):
                        store.handoff_box_plan_to_robot(source.candidate_id, **{**args, **overrides})
                self.assertEqual(store.load_robot_candidates(ACCOUNT), (source,))
                target_id = "box-robot-" + source.candidate_id.removeprefix("box-plan-")
                target_snapshot = {**source.signal_snapshot, "source_box_candidate_id": source.candidate_id}
                for account, symbol, data in (
                    (type(ACCOUNT)("foreign"), source.symbol, target_snapshot),
                    (ACCOUNT, Symbol("ETHUSDT"), target_snapshot),
                    (ACCOUNT, source.symbol, {**target_snapshot, "source_box_candidate_id": "foreign"}),
                ):
                    store.create_robot_candidate(candidate_id=target_id, trading_account_id=account,
                        symbol=symbol, signal_snapshot=data, status="APPROVED",
                        approved_at_ms=3002, updated_at_ms=3002)
                    with self.assertRaises(DuplicateIdentity):
                        store.handoff_box_plan_to_robot(source.candidate_id, **args)
                    store._connection.execute("DELETE FROM robot_candidates WHERE candidate_id=?", (target_id,))
                candidate, created = store.handoff_box_plan_to_robot(source.candidate_id, **args)
                self.assertTrue(created)
                self.assertNotEqual(candidate.candidate_id, source.candidate_id)
                self.assertEqual(candidate.status, "APPROVED")
                self.assertEqual(candidate.robot_state["phase"], "BOX_ENTRY_READY")
                self.assertEqual(candidate.signal_snapshot, target_snapshot)
                self.assertEqual(candidate.robot_state["source_box_candidate_id"], source.candidate_id)
                self.assertFalse(candidate.robot_state["execution_authorized"])
            finally:
                store.close()
            store = SQLiteStore.open(path)
            try:
                repeated, created = store.handoff_box_plan_to_robot(source.candidate_id,
                    **{**args, "approved_at_ms": 4000})
                self.assertFalse(created)
                self.assertEqual(repeated, candidate)
                self.assertEqual(store.get_robot_candidate(source.candidate_id), source)
                approved = store.load_robot_candidates_by_status(ACCOUNT, ("APPROVED",))
                self.assertEqual(approved, (candidate,))
                mode, decisions = reconcile_restart(durable_mode="ROBOT_RUNNING", open_robot_positions=(),
                    approved_candidates=({"candidate_id": candidate.candidate_id, "status": candidate.status,
                        "signal_snapshot": candidate.signal_snapshot, "robot_state": candidate.robot_state},),
                    latest_geometry_index_by_candidate={})
                self.assertEqual(mode, "ROBOT_RUNNING")
                self.assertEqual(decisions[0].status, RESUME_WAITING)
                self.assertEqual(decisions[0].reason, "BOX_ENTRY_READY")
                self.assertEqual(decisions[0].state, candidate.robot_state)
                advanced = store.save_robot_candidate_state(candidate.candidate_id, status="INVALIDATED",
                    robot_state={**candidate.robot_state, "phase": "INVALIDATED"}, expected_revision=1,
                    updated_at_ms=4001)
                self.assertEqual(store.handoff_box_plan_to_robot(source.candidate_id,
                    **{**args, "approved_at_ms": 5000}), (advanced, False))
                for table in ("paper_limit_orders", "robot_trades", "trading_commands", "executions"):
                    self.assertEqual(store._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
            finally:
                store.close()
