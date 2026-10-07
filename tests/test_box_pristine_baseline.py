"""Pristine PAPER symbol Box baseline: no projection row, empty journal.

The first execution on a symbol creates its projection at version 1, so a
never-traded symbol is the virtual version-0 FLAT state. These tests run on a
temporary SQLite only; no runtime, network or real PAPER DB is touched.
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


def plan_snapshot(a_time_ms=1000):
    data = snapshot()
    data["identity"]["a_time_ms"] = a_time_ms
    return data


class PristineBaselineTests(unittest.TestCase):
    def setUp(self):
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

    def other_plan(self, a_time_ms=999):
        plan, _ = self.store.save_box_plan_only(snapshot=plan_snapshot(a_time_ms), created_at_ms=3002)
        return plan

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

    # --- GREEN: pristine symbol establishes the virtual version-0 baseline ---

    def test_pristine_symbol_establishes_virtual_flat_baseline(self):
        self.assertIsNone(self.store.get_position_projection(KEY))
        self.assertEqual(self.store.load_executions_for_symbol(ACCOUNT, SYMBOL), ())

        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))

        row = self.baseline()
        self.assertEqual(
            (row["symbol"], row["baseline_position_version"], row["baseline_time_ms"],
             row["baseline_execution_count"], row["baseline_execution_hash"]),
            ("BTCUSDT", 0, 0, 0, EMPTY_JOURNAL),
        )
        # No projection row is invented to satisfy the old gate.
        self.assertIsNone(self.store.get_position_projection(KEY))

    def test_pristine_baseline_proves_zero_exposure_and_reserves_identities(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual((proof.entry_quantity, proof.remaining_quantity, proof.position_version),
                         (D(0), D(0), 0))
        self.assertTrue(self.store.reserve_box_order_identity(
            self.plan.candidate_id, order_id=OrderId("entry-1"), role="ENTRY", slot=1))

    def test_pristine_catchup_mixed_ownership_then_market_fill_is_proven(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        limits = tuple(
            BoxOwnedPaperLimitSpec(
                slot=slot, client_action_id=f"limit-{slot}", request_fingerprint=f"limit-fp-{slot}",
                order_id=OrderId(f"limit-order-{slot}"), order_link_id=f"limit-link-{slot}",
                side=OrderSide.BUY, price=D(price), quantity=D("2"), created_at_ms=5000 + slot,
            )
            for slot, price in ((2, "93.2"), (3, "92.4"), (4, "91.6"))
        )
        created = self.store.create_box_mixed_entry_ownership(
            self.plan.candidate_id, trading_account_id=ACCOUNT, symbol=SYMBOL,
            market_orders=(BoxOwnedPaperMarketSpec(1, OrderId("market-1")),),
            limit_orders=limits,
        )
        self.assertEqual([item.order_id.value for item in created],
                         ["limit-order-2", "limit-order-3", "limit-order-4"])
        self.assertEqual(
            [(item.role, item.slot) for item in self.store.load_box_order_ownership(self.plan.candidate_id)],
            [("ENTRY", 1), ("ENTRY", 2), ("ENTRY", 3), ("ENTRY", 4)],
        )

        # The crossed slot's MARKET fill creates the projection at version 1 = 0 + 1.
        self.fill("market-exec-1", "market-1", "2", "93.5", "2", "93.5", 6000)
        proof = self.store.prove_box_owned_position(self.plan.candidate_id)
        self.assertEqual(proof.entry_by_slot, (D("2"), D(0), D(0), D(0)))
        self.assertEqual((proof.remaining_quantity, proof.position_version), (D("2"), 1))

    # --- fail-closed controls ---

    def test_missing_projection_with_execution_evidence_is_rejected(self):
        execution = Execution(
            ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId("orphan")),
            OrderId("orphan-order"), SYMBOL, OrderSide.BUY, Price(D("94")), Quantity(D("1")), D(0), 10,
        )
        with self.store._transaction():
            self.store._insert_execution(execution)  # journal without projection: ambiguous
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

    def test_existing_unsynced_or_non_flat_projection_is_rejected(self):
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
                qty = D(quantity)
                with store._transaction():
                    store._write_projection(PositionProjectionUpdate(
                        KEY, side, Quantity(qty), Price(D(average)) if average else None,
                        D(0), D(0), Notional(qty * D(average or 0)), sync_state, None, 500,
                    ))
                with self.assertRaises(PersistenceError):
                    store.begin_box_attempt_ownership(plan.candidate_id)

    def test_projection_appearing_without_owned_execution_breaks_pristine_proof(self):
        self.assertTrue(self.store.begin_box_attempt_ownership(self.plan.candidate_id))
        with self.store._transaction():
            self.store._write_projection(PositionProjectionUpdate(
                KEY, PositionSide.FLAT, Quantity(D(0)), None, D(0), D(0), Notional(D(0)),
                "synced", None, 700,
            ))
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
        self.assertEqual(self.baseline()["baseline_position_version"], 0)

        other = self.other_plan()
        with self.assertRaises(PersistenceError):
            self.store.begin_box_attempt_ownership(other.candidate_id)
        self.assertIsNone(self.baseline(other.candidate_id))

        with self.assertRaises(sqlite3.DatabaseError):
            with self.store._transaction():
                self.store._connection.execute(
                    "UPDATE box_attempt_ownership SET baseline_position_version=1 WHERE candidate_id=?",
                    (self.plan.candidate_id,),
                )

    def test_schema_only_allows_version_zero_as_an_empty_journal_baseline(self):
        other = self.other_plan()
        for time_ms, count, digest in ((5, 0, EMPTY_JOURNAL), (0, 1, EMPTY_JOURNAL), (0, 0, "0" * 64)):
            with self.subTest(time_ms=time_ms, count=count):
                with self.assertRaises(sqlite3.IntegrityError):
                    with self.store._transaction():
                        self.store._connection.execute(
                            "INSERT INTO box_attempt_ownership VALUES (?, 'paper', 'BTCUSDT', 1, 0, ?, ?, ?)",
                            (other.candidate_id, time_ms, count, digest),
                        )


class PristineBaselineMigrationTests(unittest.TestCase):
    def test_v25_baseline_rows_survive_v26_migration_and_version_zero_becomes_valid(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "paper.sqlite3"
        store = SQLiteStore.open(path)
        plan, _ = store.save_box_plan_only(snapshot=plan_snapshot(), created_at_ms=3001)
        with store._transaction():
            store._write_projection(PositionProjectionUpdate(
                KEY, PositionSide.FLAT, Quantity(D(0)), None, D(0), D(0), Notional(D(0)),
                "synced", None, 500,
            ))
        self.assertTrue(store.begin_box_attempt_ownership(plan.candidate_id))
        store.reserve_box_order_identity(plan.candidate_id, order_id=OrderId("e1"), role="ENTRY", slot=1)
        store.close()

        # Rebuild the v25 table shape (version >= 1) and mark the file as v25.
        con = sqlite3.connect(path, isolation_level=None)
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("BEGIN")
        rows = con.execute("SELECT * FROM box_attempt_ownership").fetchall()
        con.execute("DROP TABLE box_attempt_ownership")
        con.execute(schema.SCHEMA_V23_MIGRATION_STATEMENTS[0])
        for statement in schema.SCHEMA_V23_MIGRATION_STATEMENTS[2:]:
            if "ON box_attempt_ownership" in statement:
                con.execute(statement)
        con.executemany("INSERT INTO box_attempt_ownership VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        con.execute("PRAGMA user_version=25")
        con.execute("COMMIT")
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO box_attempt_ownership VALUES ('x', 'paper', 'ETHUSDT', 1, 0, 0, 0, ?)",
                (EMPTY_JOURNAL,),
            )
        con.close()

        migrated = SQLiteStore.open(path)
        self.addCleanup(migrated.close)
        self.assertEqual(migrated._connection.execute("PRAGMA user_version").fetchone()[0],
                         schema.SCHEMA_VERSION)
        kept = migrated._connection.execute(
            "SELECT baseline_position_version FROM box_attempt_ownership WHERE candidate_id=?",
            (plan.candidate_id,),
        ).fetchone()
        self.assertEqual(kept[0], 1)
        self.assertEqual(len(migrated.load_box_order_ownership(plan.candidate_id)), 1)
        self.assertIsNone(migrated._connection.execute("PRAGMA foreign_key_check").fetchone())
        with self.assertRaises(sqlite3.DatabaseError):
            with migrated._transaction():
                migrated._connection.execute("DELETE FROM box_attempt_ownership")


if __name__ == "__main__":
    unittest.main()
