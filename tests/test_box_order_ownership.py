"""Bounded ownership proof on temporary SQLite; no runtime or planner calls."""
from decimal import Decimal as D
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, OrderId, OrderSide,
    PositionKey, PositionSide, Price, Quantity, Notional, Symbol, TradingAccountId,
)
from terminal.paper.box_ownership import BoxOwnershipError
from terminal.persistence import schema
from terminal.persistence.sqlite_store import (
    SQLiteStore, PositionProjectionUpdate, DuplicateIdentity, PersistenceError,
    ExecutionApplyResult, SchemaError,
)
from tests.test_box_plan_persistence import snapshot, trade_args


class BoxOrderOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.store = SQLiteStore.open(self.path)
        self.account = TradingAccountId("paper")
        self.key = PositionKey(self.account, Category.LINEAR, Symbol("BTCUSDT"), 0)
        self.plan, _ = self.store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
        with self.store._transaction():
            self.store._write_projection(self.projection("0", None, 4000))
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        for order, role, slot in (("entry-1", "ENTRY", 1), ("entry-2", "ENTRY", 2),
                                  ("exit-1", "EXIT", 1), ("stop", "EXIT", 0)):
            self.store.reserve_box_order_identity(
                self.plan.candidate_id, order_id=OrderId(order), role=role, slot=slot)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def projection(self, remaining, average, at, side=PositionSide.LONG):
        current = self.store.get_position_projection(self.key)
        qty = D(remaining)
        return PositionProjectionUpdate(
            self.key, side if qty else PositionSide.FLAT, Quantity(qty),
            Price(D(average)) if average is not None else None, D(0), D(0),
            Notional(qty * D(average or 0)), "synced",
            current.version if current else None, at)

    def fill(self, eid, order, side, qty, price, remaining, average, at,
             position_side=PositionSide.LONG):
        execution = Execution(
            ExecutionDedupKey(self.account, Category.LINEAR, ExecutionId(eid)),
            OrderId(order), self.key.symbol, side, Price(D(price)), Quantity(D(qty)), D(0), at)
        projection = self.projection(remaining, average, at, position_side)
        self.assertEqual(self.store.apply_execution_once(execution, projection), ExecutionApplyResult.APPLIED)
        return execution, projection

    def proof(self):
        return self.store.prove_box_owned_position(self.plan.candidate_id)

    def test_owned_limit_identity_and_order_are_one_transaction(self):
        order, created = self.store.create_box_owned_paper_limit(
            self.plan.candidate_id, role="ENTRY", slot=3,
            client_action_id="box-entry-3", request_fingerprint="box-entry-3-fp",
            order_id=OrderId("entry-3"), order_link_id="box-entry-3-link",
            trading_account_id=self.account, symbol=self.key.symbol,
            side=OrderSide.BUY, price=D("93"), quantity=D("2"), created_at_ms=4500,
        )
        self.assertTrue(created)
        self.assertEqual(order.order_id, OrderId("entry-3"))
        replay, replay_created = self.store.create_box_owned_paper_limit(
            self.plan.candidate_id, role="ENTRY", slot=3,
            client_action_id="box-entry-3", request_fingerprint="box-entry-3-fp",
            order_id=OrderId("entry-3"), order_link_id="box-entry-3-link",
            trading_account_id=self.account, symbol=self.key.symbol,
            side=OrderSide.BUY, price=D("93"), quantity=D("2"), created_at_ms=4500,
        )
        self.assertFalse(replay_created)
        self.assertEqual(replay, order)

        self.store.create_paper_limit(
            client_action_id="foreign", request_fingerprint="foreign-fp",
            order_id=OrderId("foreign"), order_link_id="occupied-link",
            trading_account_id=self.account, symbol=self.key.symbol,
            side=OrderSide.BUY, price=D("92"), quantity=D("1"), created_at_ms=4600,
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.create_box_owned_paper_limit(
                self.plan.candidate_id, role="ENTRY", slot=4,
                client_action_id="box-entry-4", request_fingerprint="box-entry-4-fp",
                order_id=OrderId("entry-4"), order_link_id="occupied-link",
                trading_account_id=self.account, symbol=self.key.symbol,
                side=OrderSide.BUY, price=D("92"), quantity=D("2"), created_at_ms=4700,
            )
        self.assertIsNone(self.store._connection.execute(
            "SELECT 1 FROM box_order_ownership WHERE order_id='entry-4'"
        ).fetchone())

    def test_partial_entry_growth_exit_duplicate_and_restart(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        self.assertEqual(self.proof().remaining_quantity, D(1))
        self.fill("e2", "entry-1", OrderSide.BUY, "1", "94", "2", "94", 6000)
        self.fill("e3", "entry-2", OrderSide.BUY, "2", "93.2", "4", "93.6", 7000)
        self.assertEqual(self.proof().remaining_quantity, D(4))
        execution, projection = self.fill("x1", "exit-1", OrderSide.SELL, "1", "99.2", "3", "93.6", 8000)
        proof = self.proof()
        self.assertEqual((proof.entry_quantity, proof.exit_quantity, proof.remaining_quantity), (D(4), D(1), D(3)))
        self.assertEqual(proof.average_entry, D("93.6"))
        self.assertFalse(proof.execution_authorized)
        self.assertEqual(self.store.apply_execution_once(execution, projection), ExecutionApplyResult.DUPLICATE)
        self.assertEqual(self.proof(), proof)
        self.store.close()
        self.store = SQLiteStore.open(self.path)
        self.assertFalse(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertFalse(self.store.reserve_box_order_identity(
            self.plan.candidate_id, order_id=OrderId("entry-1"), role="ENTRY", slot=1))
        self.assertEqual(self.proof(), proof)
        self.assertEqual(self.store.get_robot_candidate(self.plan.candidate_id), self.plan)
        self.fill("x2", "stop", OrderSide.SELL, "3", "89.6", "0", None, 9000)
        self.assertEqual(self.proof().remaining_quantity, D(0))

    def test_balanced_foreign_mutations_do_not_hide_in_same_net_position(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        self.fill("f1", "manual-buy", OrderSide.BUY, "1", "94", "2", "94", 6000)
        self.fill("f2", "manual-sell", OrderSide.SELL, "1", "94", "1", "94", 7000)
        with self.assertRaisesRegex(BoxOwnershipError, "foreign"):
            self.proof()

    def test_projection_mutation_and_missing_execution_fail_closed(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        with self.store._transaction():
            self.store._write_projection(self.projection("1", "94", 6000))
        with self.assertRaisesRegex(BoxOwnershipError, "version"):
            self.proof()
        self.store._connection.execute("DELETE FROM executions WHERE exec_id='e1'")
        with self.assertRaisesRegex(BoxOwnershipError, "missing execution"):
            self.proof()

    def test_conflicting_and_retrospective_ownership_rejected(self):
        other = snapshot()
        other["identity"]["a_time_ms"] = 999
        candidate, _ = self.store.save_box_plan_only(snapshot=other, created_at_ms=3001)
        self.store.begin_box_attempt_ownership(candidate.candidate_id)
        with self.assertRaises(DuplicateIdentity):
            self.store.reserve_box_order_identity(candidate.candidate_id,
                order_id=OrderId("entry-1"), role="ENTRY", slot=1)
        with self.assertRaises(DuplicateIdentity):
            self.store.reserve_box_order_identity(self.plan.candidate_id,
                order_id=OrderId("replacement"), role="ENTRY", slot=1)
        self.store.create_paper_limit(client_action_id="manual", request_fingerprint="manual",
            order_id=OrderId("manual"), order_link_id="manual", trading_account_id=self.account,
            symbol=self.key.symbol, side=OrderSide.BUY, price=D(92), quantity=D(1), created_at_ms=4001)
        with self.assertRaisesRegex(DuplicateIdentity, "pre-existing"):
            self.store.reserve_box_order_identity(self.plan.candidate_id,
                order_id=OrderId("manual"), role="ENTRY", slot=3)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store._connection.execute("UPDATE box_order_ownership SET role='EXIT'")

    def test_position_mismatch_and_ambiguous_chronology_rejected(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "95", 5000)
        with self.assertRaisesRegex(BoxOwnershipError, "actual position"):
            self.proof()
        self.fill("e2", "entry-1", OrderSide.BUY, "1", "94", "2", "94", 5000)
        with self.assertRaisesRegex(BoxOwnershipError, "chronology"):
            self.proof()

    def test_wrong_entry_side_rejected(self):
        self.fill("e1", "entry-1", OrderSide.SELL, "1", "94", "1", "94", 5000, PositionSide.SHORT)
        with self.assertRaisesRegex(BoxOwnershipError, "direction"):
            self.proof()

    def test_exit_cannot_reverse_and_grid_part_cannot_overfill(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        self.fill("x1", "stop", OrderSide.SELL, "2", "89", "1", "89", 6000, PositionSide.SHORT)
        with self.assertRaisesRegex(BoxOwnershipError, "exceeds"):
            self.proof()

    def test_grid_part_cannot_overfill(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "3", "94", "3", "94", 5000)
        with self.assertRaisesRegex(BoxOwnershipError, "grid part"):
            self.proof()

    def test_late_execution_cannot_rewrite_baseline(self):
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 3999)
        with self.assertRaisesRegex(BoxOwnershipError, "baseline execution"):
            self.proof()

    def test_reserved_identity_cannot_execute_another_symbol(self):
        self.key = PositionKey(self.account, Category.LINEAR, Symbol("ETHUSDT"), 0)
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        with self.assertRaisesRegex(BoxOwnershipError, "foreign execution scope"):
            self.proof()

    def test_missing_baseline_cannot_be_adopted_after_entry(self):
        other = snapshot()
        other["identity"]["a_time_ms"] = 998
        candidate, _ = self.store.save_box_plan_only(snapshot=other, created_at_ms=3001)
        with self.assertRaisesRegex(BoxOwnershipError, "baseline"):
            self.store.prove_box_owned_position(candidate.candidate_id)
        self.fill("e1", "entry-1", OrderSide.BUY, "1", "94", "1", "94", 5000)
        with self.assertRaisesRegex(PersistenceError, "FLAT"):
            self.store.begin_box_attempt_ownership(candidate.candidate_id)

    def test_v22_migration_preserves_wedge_attestations_and_rolls_back(self):
        path = Path(self.tmp.name) / "legacy.sqlite3"
        con = sqlite3.connect(path, isolation_level=None)
        con.row_factory = sqlite3.Row
        for statement in schema.SCHEMA_STATEMENTS[:-len(schema.SCHEMA_V23_MIGRATION_STATEMENTS)]:
            con.execute(statement)
        con.execute("PRAGMA user_version=22")
        legacy = SQLiteStore(con, path, 5000)
        legacy.create_robot_candidate(candidate_id="wedge", trading_account_id=self.account,
            symbol=self.key.symbol, status="APPROVED", signal_snapshot={"pattern": "Falling Wedge"},
            approved_at_ms=1, updated_at_ms=1)
        legacy.create_robot_trade(**trade_args("wedge"))
        before = legacy.get_robot_trade("trade-1")
        legacy.close()
        with patch("terminal.persistence.sqlite_store.SCHEMA_V23_MIGRATION_STATEMENTS",
                   schema.SCHEMA_V23_MIGRATION_STATEMENTS + ("INVALID SQL",)):
            with self.assertRaises(SchemaError):
                SQLiteStore.open(path)
        con = sqlite3.connect(path)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 22)
        self.assertIsNone(con.execute("SELECT name FROM sqlite_master WHERE name='box_attempt_ownership'").fetchone())
        con.close()
        migrated = SQLiteStore.open(path)
        try:
            self.assertEqual(migrated.get_robot_trade("trade-1"), before)
            self.assertEqual(migrated.get_robot_candidate("wedge").status, "OPEN")
            self.assertEqual(migrated._connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(migrated._connection.execute("PRAGMA user_version").fetchone()[0], 23)
        finally:
            migrated.close()
