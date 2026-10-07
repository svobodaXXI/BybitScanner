"""Pristine PAPER symbol Box baseline on schema 24 (no migration).

A never-traded symbol has no projection row; its first execution creates the row
at version 1, so the symbol is a virtual version-0 FLAT state. Schema 24 keeps
``baseline_position_version >= 1``, so the pristine baseline is stored as the
marker (version 1, time 0, zero executions, empty-journal hash) and proven as
virtual version 0. Temporary SQLite only; no runtime, network or real PAPER DB.
"""
from decimal import Decimal as D
from pathlib import Path
import sqlite3
import tempfile
import unittest

from terminal.domain.models import (
    Category, Execution, ExecutionDedupKey, ExecutionId, Notional, OrderId, OrderSide,
    PositionKey, PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.paper.box_ownership import BoxOwnershipError, journal_hash
from terminal.persistence import schema
from terminal.persistence.sqlite_store import (
    BoxOwnedPaperLimitSpec, BoxOwnedPaperMarketSpec, ExecutionApplyResult,
    PersistenceError, PositionProjectionUpdate, SQLiteStore,
)
from tests.test_box_plan_persistence import snapshot

ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BTCUSDT")
KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)
EMPTY_JOURNAL = journal_hash(())
PRISTINE_MARKER = (1, 0, 0, EMPTY_JOURNAL)


def plan_snapshot(a_time_ms=1000):
    data = snapshot()
    data["identity"]["a_time_ms"] = a_time_ms
    return data


class PristineBaselineTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(schema.SCHEMA_VERSION, 24)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "paper.sqlite3"
        self.store = SQLiteStore.open(self.path)
        self.addCleanup(lambda: self.store.close())
        self.plan, _ = self.store.save_box_plan_only(snapshot=plan_snapshot(), created_at_ms=3001)

    def baseline(self, candidate_id=None):
        return self.store._connection.execute(
            "SELECT * FROM box_attempt_ownership WHERE candidate_id=?",
            (candidate_id or self.plan.candidate_id,),
        ).fetchone()

    def marker(self, row):
        return (row["baseline_position_version"], row["baseline_time_ms"],
                row["baseline_execution_count"], row["baseline_execution_hash"])

    def other_plan(self, a_time_ms=999):
        plan, _ = self.store.save_box_plan_only(snapshot=plan_snapshot(a_time_ms), created_at_ms=3002)
        return plan

    def write_projection(self, side, quantity, average, sync_state, at, store=None):
        store = store or self.store
        current = store.get_position_projection(KEY)
        qty = D(quantity)
        with store._transaction():
            store._write_projection(PositionProjectionUpdate(
                KEY, side, Quantity(qty), Price(D(average)) if average else None, D(0), D(0),
                Notional(qty * D(average or 0)), sync_state,
                current.version if current else None, at,
            ))

    def fill(self, eid, order, qty, price, remaining, average, at):
        current = self.store.get_position_projection(KEY)
        quantity = D(remaining)
        projection = PositionProjectionUpdate(
            KEY, PositionSide.LONG if quantity else PositionSide.FLAT, Quantity(quantity),
            Price(D(average)) if average is not None else None, D(0), D(0),
            Notional(quantity * D(average or 0)), "synced",
            current.version if current else None, at,
        )
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId(eid)),
            OrderId(order), SYMBOL, OrderSide.BUY, Price(D(price)), Quantity(D(qty)), D(0), at,
        )
        self.assertEqual(self.store.apply_execution_once(execution, projection), ExecutionApplyResult.APPLIED)

    # --- pristine symbol establishes the schema-24 pristine marker ---

    def test_pristine_symbol_establishes_baseline_without_inventing_projection(self):
        self.assertIsNone(self.store.get_position_projection(KEY))
        self.assertEqual(self.store.load_executions_for_symbol(ACCOUNT, SYMBOL), ())
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertEqual(self.marker(self.baseline()), PRISTINE_MARKER)
        self.assertIsNone(self.store.get_position_projection(KEY))

    def test_pristine_baseline_proves_zero_exposure_and_reserves_identities(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual((proof.entry_quantity, proof.remaining_quantity, proof.position_version),
                         (D(0), D(0), 0))
        self.assertTrue(self.store.reserve_box_order_identity(
            self.plan.candidate_id, order_id=OrderId("entry-1"), role="ENTRY", slot=1))

    def test_pristine_mixed_ownership_then_market_fill_is_proven_from_virtual_zero(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        limits = tuple(
            BoxOwnedPaperLimitSpec(
                slot=slot, client_action_id=f"limit-{slot}", request_fingerprint=f"limit-fp-{slot}",
                order_id=OrderId(f"limit-order-{slot}"), order_link_id=f"limit-link-{slot}",
                side=OrderSide.BUY, price=D(price), quantity=D("2"), created_at_ms=5000 + slot,
            )
            for slot, price in ((2, "93.2"), (3, "92.4"), (4, "91.6"))
        )
        self.store.create_box_mixed_entry_ownership(
            self.plan.candidate_id, trading_account_id=ACCOUNT, symbol=SYMBOL,
            market_orders=(BoxOwnedPaperMarketSpec(1, OrderId("market-1")),),
            limit_orders=limits,
        )
        self.assertEqual(
            [(item.role, item.slot) for item in self.store.load_box_order_ownership(self.plan.candidate_id)],
            [("ENTRY", 1), ("ENTRY", 2), ("ENTRY", 3), ("ENTRY", 4)],
        )
        self.fill("market-exec-1", "market-1", "2", "93.5", "2", "93.5", 6000)
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual(proof.entry_by_slot, (D("2"), D(0), D(0), D(0)))
        self.assertEqual((proof.remaining_quantity, proof.position_version), (D("2"), 1))

    # --- fail-closed controls ---

    def test_missing_projection_with_execution_evidence_is_rejected(self):
        with self.store._transaction():
            self.store._insert_execution(Execution(
                ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("orphan")),
                OrderId("orphan-order"), SYMBOL, OrderSide.BUY, Price(D("94")), Quantity(D("1")), D(0), 10,
            ))
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertIsNone(self.baseline())

    def test_missing_projection_with_other_box_baseline_is_rejected(self):
        other = self.other_plan()
        self.assertTrue(self.store.begin_box_attempt_ownership(other.candidate_id))
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertIsNone(self.baseline())

    def test_missing_projection_with_active_paper_limit_is_rejected(self):
        self.store.create_paper_limit(
            client_action_id="manual", request_fingerprint="manual-fp",
            order_id=OrderId("manual-limit"), order_link_id="manual-link",
            trading_account_id=ACCOUNT, symbol=SYMBOL, side=OrderSide.BUY,
            price=D("90"), quantity=D("1"), created_at_ms=100,
        )
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertIsNone(self.baseline())

    def test_missing_projection_with_in_flight_command_is_rejected(self):
        with self.store._transaction():
            self.store._connection.execute(
                """INSERT INTO trading_commands (
                       command_id, order_link_id, trading_account_id, category, symbol,
                       position_idx, command_kind, side, requested_notional, normalized_price,
                       normalized_quantity, origin, controller, current_state, version,
                       exchange_order_id, created_at_ms, updated_at_ms)
                   VALUES ('cmd-inflight', 'link-inflight', 'paper', 'linear', 'BTCUSDT', 0,
                           'create_market', 'Buy', '10', NULL, '1', 'terminal_manual', 'manual',
                           'submitting', 1, NULL, 100, 100)""",
            )
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertIsNone(self.baseline())

    def test_existing_unsynced_or_non_flat_projection_is_still_rejected(self):
        for side, quantity, average, sync_state in (
            (PositionSide.FLAT, "0", None, "reconciliation_required"),
            (PositionSide.LONG, "1", "94", "synced"),
        ):
            with self.subTest(side=side, sync_state=sync_state):
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                store = SQLiteStore.open(Path(tmp.name) / "paper.sqlite3")
                self.addCleanup(store.close)
                plan, _ = store.save_box_plan_only(snapshot=plan_snapshot(), created_at_ms=3001)
                self.write_projection(side, quantity, average, sync_state, 500, store=store)
                with self.assertRaises(PersistenceError):
                    store.begin_box_attempt_ownership(plan.candidate_id)

    def test_flat_projection_at_time_zero_cannot_mimic_the_pristine_marker(self):
        self.write_projection(PositionSide.FLAT, "0", None, "synced", 0)
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(self.plan.candidate_id)
        self.assertIsNone(self.baseline())

    def test_legacy_marker_shaped_row_over_real_projection_fails_closed(self):
        # A pre-change baseline over a real FLAT v1 projection at time 0 would look
        # like the marker; read as virtual version 0 its proof can only block.
        self.write_projection(PositionSide.FLAT, "0", None, "synced", 0)
        with self.store._transaction():
            self.store._connection.execute(
                "INSERT INTO box_attempt_ownership VALUES (?, 'paper', 'BTCUSDT', 1, 1, 0, 0, ?)",
                (self.plan.candidate_id, EMPTY_JOURNAL),
            )
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)

    def test_projection_appearing_without_owned_execution_breaks_pristine_proof(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.write_projection(PositionSide.FLAT, "0", None, "synced", 700)
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)

    def test_foreign_execution_after_pristine_baseline_breaks_proof(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.fill("foreign-exec", "foreign-order", "1", "94", "1", "94", 6000)
        with self.assertRaises(BoxOwnershipError):
            self.store.prove_box_owned_position(self.plan.candidate_id)

    # --- crash / replay / idempotency ---

    def test_pristine_baseline_is_idempotent_durable_and_not_adoptable(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertFalse(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.store.close()
        self.store = SQLiteStore.open(self.path)  # restart
        self.assertFalse(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        self.assertEqual(self.marker(self.baseline()), PRISTINE_MARKER)
        other = self.other_plan()
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(other.candidate_id)
        self.assertIsNone(self.baseline(other.candidate_id))
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store._transaction():
                self.store._connection.execute(
                    "UPDATE box_attempt_ownership SET baseline_time_ms=5 WHERE candidate_id=?",
                    (self.plan.candidate_id,),
                )


if __name__ == "__main__":
    unittest.main()
