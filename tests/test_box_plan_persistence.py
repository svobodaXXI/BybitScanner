"""Isolated persistence/admission checks. No services or planner recomputation."""
import copy
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import Mock, patch

from robot_candidate_store import create_signal_snapshot
from terminal.application.robot_admission import admit_robot_candidate, RobotAdmissionRejected
from terminal.application.robot_breakout_monitor import RobotBreakoutMonitor
from terminal.application.robot_recovery import RobotRecoveryCoordinator
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence import schema
from terminal.persistence.sqlite_store import SQLiteStore, DuplicateIdentity, PersistenceError, SchemaError

ACCOUNT = TradingAccountId("paper")


def snapshot():
    # Fixed explicit fixture from the already verified approved LONG planner.
    def exposure(q, e, profit, loss, rr):
        return dict(quantity=q, average_entry=e, net_target_profit=profit,
                    net_stop_loss=loss, reward_risk=rr)
    return dict(
        contract_version=1, planner_version="099cfedc", pattern="IKIGAI_BOX",
        environment="PAPER", execution_authorized=False, attempt=1,
        identity=dict(venue="bybit", market="linear", symbol="BTCUSDT", timeframe="5",
                      direction="LONG", a_time_ms=1000, b_time_ms=2000),
        decision_time_ms=3000, anchors=dict(a_price="112.94498381877023", b_price="100"),
        fibonacci=dict(f1="100", f1618="92", f2618="79.05501618122977"),
        inputs=dict(working_quantity="8", tick_size="0.01", entry_fee_rate="0",
                    target_fee_rate="0", stop_fee_rate="0", structural_stop=None),
        plan=dict(direction="LONG", limit_prices=["94", "93.2", "92.4", "91.6"],
                  limit_quantities=["2"] * 4, frozen_f1="100", frozen_f1618="92",
                  take_price="99.2", grid_spacing="0.8", stop_price="89.6",
                  stop_basis="FULL_GRID_RR_CAP", environment="PAPER", execution_authorized=False,
                  full_position=exposure("8", "92.8", "51.2", "25.6", "2"),
                  slices=[exposure("2", "94", "10.4", "8.8", "1.181818181818181818181818182"),
                          exposure("2", "93.2", "12", "7.2", "1.666666666666666666666666667"),
                          exposure("2", "92.4", "13.6", "5.6", "2.428571428571428571428571429"),
                          exposure("2", "91.6", "15.2", "4", "3.8")],
                  partial_fill_loss_upper_bound="25.6",
                  minimum_partial_fill_rr="1.181818181818181818181818182"))


def trade_args(candidate_id):
    return dict(trade_id="trade-1", trading_account_id=ACCOUNT, candidate_id=candidate_id,
                symbol=Symbol("BTCUSDT"), direction="LONG", pattern="Falling Wedge",
                source_timeframe="1", signal_time_ms=1, entry_time_ms=2, entry_path="LIMIT",
                actual_wv=D("1"), average_entry=D("94"), stop_price=D("89.6"), take_price=D("99.2"),
                entry_quantity=D("8"), entry_position_version=1, created_at_ms=4)


class BoxPlanPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"

    def open(self):
        store = SQLiteStore.open(self.path)
        self.addCleanup(store.close)
        return store

    def legacy(self):
        con = sqlite3.connect(self.path, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        for statement in schema.SCHEMA_STATEMENTS[:-len(schema.SCHEMA_V22_MIGRATION_STATEMENTS)]:
            con.execute(statement)
        con.execute("PRAGMA user_version=21")
        return SQLiteStore(con, self.path, 5000)

    def test_legacy_migration_preserves_approved_open_trade_and_foreign_keys(self):
        old = self.legacy()
        for name in ("approved", "open"):
            old.create_robot_candidate(candidate_id=name, trading_account_id=ACCOUNT,
                symbol=Symbol("BTCUSDT"), status="APPROVED",
                signal_snapshot={"symbol": "BTCUSDT", "name": name}, approved_at_ms=1, updated_at_ms=1)
        old.create_robot_trade(**trade_args("open"))
        before = {name: old.get_robot_candidate(name) for name in ("approved", "open")}
        trade = old.get_robot_trade("trade-1")
        old.close()
        store = self.open()
        for name, record in before.items():
            self.assertEqual(store.get_robot_candidate(name), record)
        self.assertEqual(store.get_robot_trade("trade-1"), trade)
        self.assertEqual(store._connection.execute("PRAGMA user_version").fetchone()[0], 22)
        self.assertEqual(store._connection.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(store._connection.execute("PRAGMA foreign_key_check").fetchall(), [])
        saved, created = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
        self.assertTrue(created)
        self.assertIsNone(saved.approved_at_ms)

    def test_failed_migration_rolls_back_legacy_rows_and_version(self):
        old = self.legacy()
        old.create_robot_candidate(candidate_id="old", trading_account_id=ACCOUNT,
            symbol=Symbol("BTCUSDT"), status="APPROVED", signal_snapshot={"old": True},
            approved_at_ms=1, updated_at_ms=1)
        old.close()
        with patch("terminal.persistence.sqlite_store.SCHEMA_V22_MIGRATION_STATEMENTS",
                   schema.SCHEMA_V22_MIGRATION_STATEMENTS + ("INVALID SQL",)):
            with self.assertRaises(SchemaError):
                SQLiteStore.open(self.path)
        with closing(sqlite3.connect(self.path)) as con:
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 21)
            self.assertEqual(con.execute("SELECT status FROM robot_candidates").fetchone()[0], "APPROVED")

    def test_canonical_idempotence_conflict_immutability_and_reopen(self):
        store = self.open()
        original = snapshot()
        record, created = store.save_box_plan_only(snapshot=original, created_at_ms=3001)
        self.assertTrue(created)
        equivalent = copy.deepcopy(original)
        equivalent["plan"]["take_price"] = "99.2000"
        repeated, created = store.save_box_plan_only(snapshot=equivalent, created_at_ms=9999)
        self.assertFalse(created)
        self.assertEqual(record, repeated)
        original["plan"]["take_price"] = "98"
        with self.assertRaises(DuplicateIdentity):
            store.save_box_plan_only(snapshot=original, created_at_ms=4000)
        with self.assertRaises(sqlite3.IntegrityError):
            store._connection.execute("UPDATE robot_candidates SET status='APPROVED', approved_at_ms=1 WHERE candidate_id=?", (record.candidate_id,))
        other = self.open()
        self.assertEqual(other.get_robot_candidate(record.candidate_id), record)
        changed = snapshot()
        changed["identity"]["timeframe"] = "1"
        distinct, _ = store.save_box_plan_only(snapshot=changed, created_at_ms=3001)
        self.assertNotEqual(distinct.candidate_id, record.candidate_id)

    def test_invalid_contract_rejected_without_persistence(self):
        store = self.open()
        for key, value in (("environment", "LIVE"), ("execution_authorized", True),
                           ("attempt", 2), ("decision_time_ms", 1)):
            data = snapshot()
            data[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                store.save_box_plan_only(snapshot=data, created_at_ms=3001)
        data = snapshot()
        data["plan"]["take_price"] = float("nan")
        with self.assertRaises(ValueError):
            store.save_box_plan_only(snapshot=data, created_at_ms=3001)
        self.assertEqual(store.load_robot_candidates(ACCOUNT), ())

    def test_hash_corruption_fails_closed(self):
        store = self.open()
        record, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
        # Simulate disk/out-of-band corruption, bypassing the normal immutability trigger.
        store._connection.execute("DROP TRIGGER box_plan_no_update")
        store._connection.execute("UPDATE robot_candidates SET snapshot_sha256=?", ("0" * 64,))
        with self.assertRaisesRegex(SchemaError, "hash mismatch"):
            store.get_robot_candidate(record.candidate_id)

    def test_plan_cannot_be_admitted_promoted_traded_monitored_or_recovered(self):
        store = self.open()
        record, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
        for status in ("APPROVED", "OPEN", "BOX_PLAN_ONLY"):
            with self.subTest(status=status), self.assertRaises(PersistenceError):
                store.save_robot_candidate_state(record.candidate_id, status=status,
                    robot_state={}, expected_revision=0, updated_at_ms=4000)
        with self.assertRaises(DuplicateIdentity):
            store.create_robot_candidate(candidate_id=record.candidate_id, trading_account_id=ACCOUNT,
                symbol=Symbol("BTCUSDT"), status="APPROVED", signal_snapshot=record.signal_snapshot,
                approved_at_ms=4000, updated_at_ms=4000)
        with self.assertRaises(PersistenceError):
            store.create_robot_trade(**trade_args(record.candidate_id))
        candidates = Path(self.tmp.name) / "candidates"
        # Same durable identity disguised as a valid Wedge handoff must not bypass the guard.
        create_signal_snapshot({"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
            timeframe="1", candidate_id=record.candidate_id, store_dir=candidates)
        with self.assertRaisesRegex(RobotAdmissionRejected, "BOX_PLAN_ONLY"):
            admit_robot_candidate(record.candidate_id, store_dir=candidates, database_path=self.path)
        create_signal_snapshot({"symbol": "BTCUSDT", "pattern": "IKIGAI_BOX"},
            timeframe="1", candidate_id="box-handoff", store_dir=candidates)
        with self.assertRaisesRegex(RobotAdmissionRejected, "BOX_PLAN_ONLY"):
            admit_robot_candidate("box-handoff", store_dir=candidates, database_path=self.path)
        forbidden = Mock(side_effect=AssertionError("execution dependency was called"))
        monitor = RobotBreakoutMonitor(lambda: store, ACCOUNT, get_closed_candle=forbidden,
            action_executor=forbidden, tick_size_provider=forbidden, clock_ms=lambda: 5000)
        self.assertEqual(monitor.tick(), ())
        runtime = store.initialize_robot_runtime_state(ACCOUNT, updated_at_ms=4000)
        store.update_robot_runtime_state(ACCOUNT, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=runtime.version, updated_at_ms=4001)
        recovery = RobotRecoveryCoordinator(store, ACCOUNT,
            latest_geometry_index_provider=forbidden, clock_ms=lambda: 5000)
        recovery.recover()
        forbidden.assert_not_called()
        self.assertEqual(store.get_robot_candidate(record.candidate_id), record)
        self.assertEqual(store.load_active_robot_candidate_states(ACCOUNT), ())
        self.assertIsNone(store.get_robot_trade("trade-1"))
