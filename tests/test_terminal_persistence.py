import ast
import sqlite3
import tempfile
import unittest
from unittest import mock
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import (
    Category,
    CommandId,
    Controller,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    Origin,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.persistence.schema import (
    SCHEMA_V1_STATEMENTS, SCHEMA_V2_MIGRATION_STATEMENTS,
    SCHEMA_V3_MIGRATION_STATEMENTS, SCHEMA_V4_MIGRATION_STATEMENTS,
    SCHEMA_V5_MIGRATION_STATEMENTS,
    SCHEMA_VERSION,
)
from terminal.persistence.sqlite_store import (
    CommandRecord,
    ConcurrentUpdate,
    DuplicateIdentity,
    ExecutionApplyResult,
    ImmutableExecutionConflict,
    PositionProjectionUpdate,
    ReconciliationCheckpointUpdate,
    SQLiteStore,
    PersistenceError,
    SchemaError,
)


class TerminalPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "terminal-test.sqlite3"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def open_store(self):
        return SQLiteStore.open(self.database_path, busy_timeout_ms=2500)

    def create_v1_database(self):
        connection = sqlite3.connect(self.database_path)
        for statement in SCHEMA_V1_STATEMENTS:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 1")
        connection.execute(
            """
            INSERT INTO trading_commands VALUES (
                'command-1', 'link-1', 'account-1', 'linear', 'BTCUSDT', 0,
                'create_market', 'Buy', '123.45', '65000.125', '0.001',
                'terminal_manual', 'manual', 'admitted', 1, NULL, 1000, 1000
            )
            """
        )
        connection.execute(
            """
            INSERT INTO command_state_history
                (command_id, previous_state, next_state, reason, occurred_at_ms)
            VALUES ('command-1', NULL, 'admitted', 'v1 seed', 1000)
            """
        )
        connection.execute(
            """
            INSERT INTO executions VALUES (
                'account-1', 'linear', 'exec-1', 'order-account-1', 'BTCUSDT',
                'Buy', '65000.125', '0.001', '-0.00005', 2000
            )
            """
        )
        connection.execute(
            """
            INSERT INTO position_projections VALUES (
                'account-1', 'linear', 'BTCUSDT', 0, 'Long', '0.001',
                '65000.125', '0.1', '-0.00005', '65.000125',
                'reconciliation_required', 1, 2000
            )
            """
        )
        connection.commit()
        connection.close()

    def create_v2_database(self):
        connection = sqlite3.connect(self.database_path)
        for statement in SCHEMA_V1_STATEMENTS + SCHEMA_V2_MIGRATION_STATEMENTS:
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 2")
        connection.commit()
        connection.close()

    def create_v3_database(self):
        connection = sqlite3.connect(self.database_path)
        for statement in (
            SCHEMA_V1_STATEMENTS
            + SCHEMA_V2_MIGRATION_STATEMENTS
            + SCHEMA_V3_MIGRATION_STATEMENTS
        ):
            connection.execute(statement)
        connection.execute("PRAGMA user_version = 3")
        connection.commit()
        connection.close()

    def create_v5_database(self):
        connection = sqlite3.connect(self.database_path)
        for statement in (
            SCHEMA_V1_STATEMENTS
            + SCHEMA_V2_MIGRATION_STATEMENTS
            + SCHEMA_V3_MIGRATION_STATEMENTS
            + SCHEMA_V4_MIGRATION_STATEMENTS
            + SCHEMA_V5_MIGRATION_STATEMENTS
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO paper_limit_orders VALUES (?, ?, ?, ?, ?, ?, ?, 'GTC', 'open', ?, ?)",
            ("order-1", "link-paper-1", "paper", "BTCUSDT", "Buy", "64000", "0.005", 1000, 1000),
        )
        connection.execute(
            "INSERT INTO paper_limit_actions VALUES (?, 'create', ?, ?, ?)",
            ("create-1", "fingerprint-1", "order-1", 1000),
        )
        connection.execute("PRAGMA user_version = 5")
        connection.commit()
        connection.close()

    def command(
        self,
        *,
        command_id="command-1",
        order_link_id="link-1",
        account="account-1",
        state=CommandState.ADMITTED,
    ):
        return CommandRecord(
            command_id=CommandId(command_id),
            order_link_id=order_link_id,
            trading_account_id=TradingAccountId(account),
            category=Category.LINEAR,
            symbol=Symbol("BTCUSDT"),
            position_idx=0,
            command_kind="create_market",
            side=OrderSide.BUY,
            requested_notional=Notional(Decimal("123.450000000000000001")),
            normalized_price=Price(Decimal("65000.125000000000000001")),
            normalized_quantity=Quantity(Decimal("0.001234567890123456")),
            origin=Origin.TERMINAL_MANUAL,
            controller=Controller.MANUAL,
            current_state=state,
            version=1,
            exchange_order_id=None,
            created_at_ms=1000,
            updated_at_ms=1000,
        )

    def execution(self, *, exec_id="exec-1", account="account-1", fee="-0.00005"):
        return Execution(
            dedup_key=ExecutionDedupKey(
                TradingAccountId(account), Category.LINEAR, ExecutionId(exec_id)
            ),
            order_id=OrderId(f"order-{account}"),
            symbol=Symbol("BTCUSDT"),
            side=OrderSide.BUY,
            price=Price(Decimal("65000.125000000000000001")),
            quantity=Quantity(Decimal("0.001234567890123456")),
            fee=Decimal(fee),
            exchange_timestamp_ms=2000,
        )

    def projection(self, *, account="account-1", expected_version=None, quantity="0.001"):
        value = Decimal(quantity)
        return PositionProjectionUpdate(
            position_key=PositionKey(
                TradingAccountId(account), Category.LINEAR, Symbol("BTCUSDT"), 0
            ),
            side=PositionSide.LONG if value else PositionSide.FLAT,
            quantity=Quantity(value),
            average_entry=Price(Decimal("65000.125000000000000001")) if value else None,
            realized_pnl=Decimal("0.000000000000000001"),
            accumulated_fee=Decimal("-0.00005"),
            engaged_notional=Notional(Decimal("80.246913573024683912")),
            sync_state="reconciliation_required",
            expected_version=expected_version,
            updated_at_ms=2000,
        )

    def checkpoint_update(
        self,
        *,
        generation=1,
        outcome="converged",
        expected_version=1,
        started_at_ms=1900,
        exchange_snapshot_at_ms=2100,
        completed_at_ms=2200,
        updated_at_ms=2200,
    ):
        return ReconciliationCheckpointUpdate(
            position_key=self.projection().position_key,
            generation=generation,
            outcome=outcome,
            exchange_snapshot_at_ms=exchange_snapshot_at_ms,
            exchange_sequence=77,
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            expected_version=expected_version,
            updated_at_ms=updated_at_ms,
        )

    def test_fresh_database_initializes_versioned_wal_schema(self):
        self.assertFalse(self.database_path.exists())
        with self.open_store() as store:
            settings = store.settings()
            self.assertEqual(settings.schema_version, SCHEMA_VERSION)
            self.assertEqual(settings.journal_mode, "wal")
            self.assertTrue(settings.foreign_keys)
            self.assertEqual(settings.busy_timeout_ms, 2500)
            self.assertEqual(settings.synchronous, 2)  # SQLite FULL
        self.assertTrue(self.database_path.exists())

    def test_paper_account_initialization_is_durable_and_idempotent(self):
        account_id = TradingAccountId("paper")

        with self.open_store() as store:
            created = store.initialize_paper_account(
                account_id,
                Decimal("5000"),
                updated_at_ms=1234,
            )
            self.assertEqual(created.initial_deposit_usdt, Decimal("5000"))
            self.assertEqual(created.equity_usdt, Decimal("5000"))
            self.assertEqual(created.version, 1)

            repeated = store.initialize_paper_account(
                account_id,
                Decimal("5000"),
                updated_at_ms=9999,
            )
            self.assertEqual(repeated, created)

        with self.open_store() as reopened:
            persisted = reopened.get_paper_account(account_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.initial_deposit_usdt, Decimal("5000"))
            self.assertEqual(persisted.equity_usdt, Decimal("5000"))
            self.assertEqual(persisted.updated_at_ms, 1234)

    def test_paper_account_initialization_rejects_deposit_mismatch(self):
        account_id = TradingAccountId("paper")

        with self.open_store() as store:
            store.initialize_paper_account(
                account_id,
                Decimal("5000"),
                updated_at_ms=1234,
            )
            with self.assertRaises(PersistenceError):
                store.initialize_paper_account(
                    account_id,
                    Decimal("6000"),
                    updated_at_ms=2000,
                )

            persisted = store.get_paper_account(account_id)
            self.assertEqual(persisted.initial_deposit_usdt, Decimal("5000"))
            self.assertEqual(persisted.equity_usdt, Decimal("5000"))

    def test_v1_migration_preserves_commands_executions_and_projection(self):
        self.create_v1_database()

        with self.open_store() as store:
            self.assertEqual(store.settings().schema_version, SCHEMA_VERSION)
            self.assertEqual(store.get_command(CommandId("command-1")).order_link_id, "link-1")
            self.assertEqual(
                store.get_execution(
                    ExecutionDedupKey(
                        TradingAccountId("account-1"),
                        Category.LINEAR,
                        ExecutionId("exec-1"),
                    )
                ).fee,
                Decimal("-0.00005"),
            )
            projection = store.get_position_projection(self.projection().position_key)
            self.assertEqual(projection.quantity.value, Decimal("0.001"))
            self.assertIsNone(store.get_reconciliation_checkpoint(self.projection().position_key))

    def test_v1_migration_failure_rolls_back_schema_and_preserves_data(self):
        self.create_v1_database()
        invalid_migration = (
            "CREATE TABLE reconciliation_checkpoints(temp_value TEXT)",
            "NOT VALID SQLITE",
        )

        with mock.patch(
            "terminal.persistence.sqlite_store.SCHEMA_V2_MIGRATION_STATEMENTS",
            invalid_migration,
        ):
            with self.assertRaisesRegex(SchemaError, "unavailable or corrupt"):
                self.open_store()

        connection = sqlite3.connect(self.database_path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 1)
        self.assertEqual(
            connection.execute("SELECT order_link_id FROM trading_commands").fetchone()[0],
            "link-1",
        )
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM executions").fetchone()[0], 1)
        self.assertEqual(
            connection.execute("SELECT quantity FROM position_projections").fetchone()[0],
            "0.001",
        )
        self.assertIsNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='reconciliation_checkpoints'"
            ).fetchone()
        )
        connection.close()

    def test_v2_to_v3_migration_is_transactional_and_creates_stage6_tables(self):
        self.create_v2_database()
        with self.open_store() as store:
            self.assertEqual(store.settings().schema_version, SCHEMA_VERSION)
        connection = sqlite3.connect(self.database_path)
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        connection.close()
        self.assertTrue({
            "cleanup_runs", "cleanup_items", "protection_intents",
            "protection_projections",
        }.issubset(tables))

    def test_v2_to_v3_migration_failure_rolls_back_all_new_tables(self):
        self.create_v2_database()
        invalid = (SCHEMA_V3_MIGRATION_STATEMENTS[0], "NOT VALID SQLITE")
        with mock.patch(
            "terminal.persistence.sqlite_store.SCHEMA_V3_MIGRATION_STATEMENTS", invalid,
        ):
            with self.assertRaises(SchemaError):
                self.open_store()
        connection = sqlite3.connect(self.database_path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertIsNone(connection.execute(
            "SELECT name FROM sqlite_master WHERE name='cleanup_runs'"
        ).fetchone())
        connection.close()

    def test_v3_to_v4_migration_creates_paper_accounts(self):
        self.create_v3_database()

        with self.open_store() as store:
            self.assertEqual(store.settings().schema_version, SCHEMA_VERSION)

        connection = sqlite3.connect(self.database_path)
        self.assertIsNotNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='paper_accounts'"
            ).fetchone()
        )
        connection.close()

    def test_v3_to_v4_migration_failure_rolls_back_paper_accounts(self):
        self.create_v3_database()
        invalid = (SCHEMA_V4_MIGRATION_STATEMENTS[0], "NOT VALID SQLITE")

        with mock.patch(
            "terminal.persistence.sqlite_store.SCHEMA_V4_MIGRATION_STATEMENTS",
            invalid,
        ):
            with self.assertRaises(SchemaError):
                self.open_store()

        connection = sqlite3.connect(self.database_path)
        self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 3)
        self.assertIsNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='paper_accounts'"
            ).fetchone()
        )
        connection.close()

    def test_v5_to_v6_migration_preserves_limits_and_allows_amend_actions(self):
        self.create_v5_database()

        with self.open_store() as store:
            self.assertEqual(store.settings().schema_version, SCHEMA_VERSION)
            order = store.get_paper_limit("order-1")
            self.assertIsNotNone(order)
            amended, changed = store.amend_paper_limit(
                client_action_id="amend-1",
                request_fingerprint="fingerprint-amend-1",
                order_id=OrderId("order-1"),
                price=Decimal("64100"),
                updated_at_ms=2000,
            )
            self.assertTrue(changed)
            self.assertEqual(amended.price, Decimal("64100"))

    def test_incompatible_schema_fails_closed_without_recreate(self):
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE retained_marker(value TEXT)")
        connection.execute("PRAGMA user_version = 99")
        connection.commit()
        connection.close()

        with self.assertRaisesRegex(SchemaError, "unsupported"):
            self.open_store()

        connection = sqlite3.connect(self.database_path)
        self.assertIsNotNone(
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name='retained_marker'"
            ).fetchone()
        )
        connection.close()

    def test_corrupt_database_fails_closed(self):
        self.database_path.write_bytes(b"not a sqlite database")
        with self.assertRaisesRegex(SchemaError, "unavailable or corrupt"):
            self.open_store()
        self.assertEqual(self.database_path.read_bytes(), b"not a sqlite database")

    def test_submit_eligibility_is_returned_only_after_durable_command_commit(self):
        command = self.command()
        with self.open_store() as store:
            eligibility = store.persist_command_before_submit(command)
            self.assertEqual(eligibility.command_id, command.command_id)
            self.assertEqual(eligibility.order_link_id, command.order_link_id)

        with self.open_store() as reopened:
            self.assertEqual(reopened.get_command(command.command_id), command)

    def test_duplicate_command_and_order_link_id_are_rejected(self):
        with self.open_store() as store:
            store.persist_command_before_submit(self.command())
            with self.assertRaises(DuplicateIdentity):
                store.persist_command_before_submit(self.command(order_link_id="link-2"))
            with self.assertRaises(DuplicateIdentity):
                store.persist_command_before_submit(
                    self.command(command_id="command-2", order_link_id="link-1")
                )

    def test_unfinished_and_unknown_command_survive_restart_without_resubmit(self):
        with self.open_store() as store:
            store.persist_command_before_submit(self.command())
            submitting = store.transition_command_state(
                CommandId("command-1"),
                CommandState.ADMITTED,
                CommandState.SUBMITTING,
                expected_version=1,
                reason="network attempt began",
                occurred_at_ms=1100,
            )
            store.transition_command_state(
                CommandId("command-1"),
                CommandState.SUBMITTING,
                CommandState.UNKNOWN,
                expected_version=submitting.version,
                reason="transport outcome unknown",
                occurred_at_ms=1200,
            )

        with self.open_store() as reopened:
            unfinished = reopened.load_unfinished_commands()
            self.assertEqual(len(unfinished), 1)
            self.assertIs(unfinished[0].current_state, CommandState.UNKNOWN)
            self.assertEqual(unfinished[0].order_link_id, "link-1")
            history = reopened.load_command_history(CommandId("command-1"))
            self.assertEqual(
                tuple(item.next_state for item in history),
                (
                    CommandState.ADMITTED,
                    CommandState.SUBMITTING,
                    CommandState.UNKNOWN,
                ),
            )
            self.assertIsNone(history[0].previous_state)
            self.assertFalse(hasattr(reopened, "submit"))
            self.assertFalse(hasattr(reopened, "resubmit"))

    def test_restart_excludes_amended_and_existing_final_states_only(self):
        def persist_path(store, suffix, states):
            command = self.command(
                command_id=f"command-{suffix}",
                order_link_id=f"link-{suffix}",
            )
            store.persist_command_before_submit(command)
            current = command
            for next_state in states:
                current = store.transition_command_state(
                    current.command_id,
                    current.current_state,
                    next_state,
                    expected_version=current.version,
                    reason=f"test transition to {next_state.value}",
                    occurred_at_ms=current.updated_at_ms + 1,
                )

        with self.open_store() as store:
            persist_path(
                store,
                "amended",
                (CommandState.SUBMITTING, CommandState.ACKNOWLEDGED, CommandState.AMENDED),
            )
            persist_path(
                store,
                "filled",
                (CommandState.SUBMITTING, CommandState.ACKNOWLEDGED, CommandState.FILLED),
            )
            persist_path(
                store,
                "cancelled",
                (
                    CommandState.SUBMITTING,
                    CommandState.ACKNOWLEDGED,
                    CommandState.CANCEL_PENDING,
                    CommandState.CANCELLED,
                ),
            )
            persist_path(store, "rejected", (CommandState.SUBMITTING, CommandState.REJECTED))
            persist_path(store, "failed", (CommandState.FAILED,))
            persist_path(store, "unknown", (CommandState.SUBMITTING, CommandState.UNKNOWN))
            persist_path(
                store,
                "reconciling",
                (CommandState.SUBMITTING, CommandState.UNKNOWN, CommandState.RECONCILING),
            )

        with self.open_store() as reopened:
            unfinished = reopened.load_unfinished_commands()
            self.assertEqual(
                {record.current_state for record in unfinished},
                {CommandState.UNKNOWN, CommandState.RECONCILING},
            )
            self.assertNotIn(
                CommandState.AMENDED,
                {record.current_state for record in unfinished},
            )

    def test_execution_is_applied_once_across_ws_rest_and_restart(self):
        execution = self.execution()
        with self.open_store() as store:
            self.assertIs(
                store.apply_execution_once(execution, self.projection()),
                ExecutionApplyResult.APPLIED,
            )
            projection = store.get_position_projection(self.projection().position_key)
            self.assertEqual(projection.version, 1)
            self.assertIs(
                store.apply_execution_once(
                    execution,
                    self.projection(expected_version=1, quantity="9"),
                ),
                ExecutionApplyResult.DUPLICATE,
            )
            self.assertEqual(
                store.get_position_projection(self.projection().position_key).quantity.value,
                Decimal("0.001"),
            )

        with self.open_store() as reopened:
            self.assertIs(
                reopened.apply_execution_once(
                    execution,
                    self.projection(expected_version=1, quantity="7"),
                ),
                ExecutionApplyResult.DUPLICATE,
            )
            self.assertEqual(
                reopened.get_position_projection(self.projection().position_key).version, 1
            )
            self.assertEqual(reopened.load_executions(), (execution,))

    def test_duplicate_execution_can_complete_correlation_without_economic_reapply(self):
        command = self.command()
        execution = self.execution()
        with self.open_store() as store:
            store.persist_command_before_submit(command)
            store.apply_execution_once(execution, self.projection())
            self.assertIsNone(store.get_command(command.command_id).exchange_order_id)
            self.assertIs(
                store.apply_execution_once(
                    execution,
                    self.projection(expected_version=1, quantity="9"),
                    command_id=command.command_id,
                ),
                ExecutionApplyResult.DUPLICATE,
            )
            self.assertEqual(
                store.get_command(command.command_id).exchange_order_id,
                execution.order_id,
            )
            self.assertEqual(
                store.get_position_projection(self.projection().position_key).quantity.value,
                Decimal("0.001"),
            )

    def test_same_exec_id_is_isolated_by_account_and_category_key(self):
        first = self.execution(exec_id="shared", account="account-1")
        second = self.execution(exec_id="shared", account="account-2")
        with self.open_store() as store:
            self.assertIs(
                store.apply_execution_once(first, self.projection(account="account-1")),
                ExecutionApplyResult.APPLIED,
            )
            self.assertIs(
                store.apply_execution_once(second, self.projection(account="account-2")),
                ExecutionApplyResult.APPLIED,
            )
            self.assertIsNotNone(store.get_execution(first.dedup_key))
            self.assertIsNotNone(store.get_execution(second.dedup_key))

        connection = sqlite3.connect(self.database_path)
        primary_key_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(executions)")
            if row[5] > 0
        }
        connection.close()
        self.assertEqual(
            primary_key_columns, {"trading_account_id", "category", "exec_id"}
        )

    def test_transaction_failure_rolls_back_execution_and_projection(self):
        command = self.command()
        execution = self.execution()
        with self.open_store() as store:
            store.persist_command_before_submit(command)
            with self.assertRaises(ConcurrentUpdate):
                store.apply_execution_once(
                    execution,
                    self.projection(expected_version=99),
                    command_id=command.command_id,
                )
            self.assertIsNone(store.get_execution(execution.dedup_key))
            self.assertIsNone(store.get_position_projection(self.projection().position_key))
            self.assertIsNone(store.get_command(command.command_id).exchange_order_id)

    def test_immutable_execution_conflict_does_not_change_projection(self):
        original = self.execution()
        conflict = self.execution(fee="0.9")
        with self.open_store() as store:
            store.apply_execution_once(original, self.projection())
            with self.assertRaises(ImmutableExecutionConflict):
                store.apply_execution_once(
                    conflict,
                    self.projection(expected_version=1, quantity="2"),
                )
            self.assertEqual(store.get_execution(original.dedup_key), original)
            self.assertEqual(
                store.get_position_projection(self.projection().position_key).quantity.value,
                Decimal("0.001"),
            )

    def test_decimal_fields_roundtrip_without_float_conversion(self):
        command = self.command()
        execution = self.execution()
        projection = self.projection()
        with self.open_store() as store:
            store.persist_command_before_submit(command)
            store.apply_execution_once(execution, projection, command_id=command.command_id)
            loaded_command = store.get_command(command.command_id)
            loaded_execution = store.get_execution(execution.dedup_key)
            loaded_projection = store.get_position_projection(projection.position_key)
            self.assertEqual(loaded_command.requested_notional, command.requested_notional)
            self.assertEqual(loaded_command.normalized_price, command.normalized_price)
            self.assertEqual(loaded_command.normalized_quantity, command.normalized_quantity)
            self.assertEqual(loaded_execution.price, execution.price)
            self.assertEqual(loaded_execution.quantity, execution.quantity)
            self.assertEqual(loaded_execution.fee, execution.fee)
            self.assertEqual(loaded_projection.realized_pnl, projection.realized_pnl)
            self.assertEqual(loaded_projection.accumulated_fee, projection.accumulated_fee)
            self.assertEqual(loaded_projection.engaged_notional, projection.engaged_notional)

    def test_authoritative_snapshot_and_checkpoint_commit_without_execution(self):
        key = self.projection().position_key
        with self.open_store() as store:
            self.assertIsNone(store.get_reconciliation_checkpoint(key))
            started = store.begin_reconciliation(
                key,
                generation=1,
                exchange_snapshot_at_ms=1900,
                exchange_sequence=70,
                started_at_ms=1900,
                expected_version=None,
                updated_at_ms=1900,
            )
            self.assertEqual(started.outcome, "in_progress")
            self.assertIsNone(started.completed_at_ms)
            self.assertIsNone(store.get_position_projection(key))
            self.assertEqual(store.load_executions(), ())

        with self.open_store() as reopened:
            unfinished = reopened.get_reconciliation_checkpoint(key)
            self.assertEqual(unfinished, started)
            projection, checkpoint = reopened.commit_authoritative_position_snapshot(
                self.projection(),
                self.checkpoint_update(),
            )
            self.assertEqual(projection.quantity.value, Decimal("0.001"))
            self.assertEqual(checkpoint.outcome, "converged")
            self.assertEqual(checkpoint.version, 2)
            self.assertEqual(reopened.load_executions(), ())

        with self.open_store() as recovered:
            self.assertEqual(
                recovered.get_reconciliation_checkpoint(key).outcome,
                "converged",
            )
            self.assertFalse(hasattr(recovered, "online"))
            self.assertFalse(hasattr(recovered, "submit_eligibility"))

    def test_external_snapshot_can_correct_stale_projection_and_then_flat(self):
        key = self.projection().position_key
        with self.open_store() as store:
            first = store.begin_reconciliation(
                key,
                generation=1,
                exchange_snapshot_at_ms=1900,
                exchange_sequence=None,
                started_at_ms=1900,
                expected_version=None,
                updated_at_ms=1900,
            )
            store.commit_authoritative_position_snapshot(
                self.projection(quantity="9.123456789012345678"),
                self.checkpoint_update(),
            )

            second = store.begin_reconciliation(
                key,
                generation=2,
                exchange_snapshot_at_ms=3000,
                exchange_sequence=80,
                started_at_ms=3000,
                expected_version=first.version + 1,
                updated_at_ms=3000,
            )
            corrected, _ = store.commit_authoritative_position_snapshot(
                self.projection(expected_version=1, quantity="0.25"),
                self.checkpoint_update(
                    generation=2,
                    expected_version=second.version,
                    started_at_ms=3000,
                    exchange_snapshot_at_ms=3100,
                    completed_at_ms=3200,
                    updated_at_ms=3200,
                ),
            )
            self.assertEqual(corrected.quantity.value, Decimal("0.25"))

            third = store.begin_reconciliation(
                key,
                generation=3,
                exchange_snapshot_at_ms=4000,
                exchange_sequence=90,
                started_at_ms=4000,
                expected_version=second.version + 1,
                updated_at_ms=4000,
            )
            flat, checkpoint = store.commit_authoritative_position_snapshot(
                self.projection(expected_version=2, quantity="0"),
                self.checkpoint_update(
                    generation=3,
                    expected_version=third.version,
                    started_at_ms=4000,
                    exchange_snapshot_at_ms=4100,
                    completed_at_ms=4200,
                    updated_at_ms=4200,
                ),
            )
            self.assertIs(flat.side, PositionSide.FLAT)
            self.assertEqual(flat.quantity.value, Decimal("0"))
            self.assertEqual(checkpoint.generation, 3)
            self.assertEqual(store.load_executions(), ())

    def test_snapshot_checkpoint_transaction_rolls_back_on_checkpoint_conflict(self):
        key = self.projection().position_key
        with self.open_store() as store:
            started = store.begin_reconciliation(
                key,
                generation=1,
                exchange_snapshot_at_ms=1900,
                exchange_sequence=70,
                started_at_ms=1900,
                expected_version=None,
                updated_at_ms=1900,
            )
            with self.assertRaises(ConcurrentUpdate):
                store.commit_authoritative_position_snapshot(
                    self.projection(),
                    self.checkpoint_update(expected_version=99),
                )
            self.assertIsNone(store.get_position_projection(key))
            self.assertEqual(store.get_reconciliation_checkpoint(key), started)

    def test_non_converged_checkpoint_survives_restart_as_recovery_evidence_only(self):
        key = self.projection().position_key
        with self.open_store() as store:
            store.begin_reconciliation(
                key,
                generation=1,
                exchange_snapshot_at_ms=1900,
                exchange_sequence=None,
                started_at_ms=1900,
                expected_version=None,
                updated_at_ms=1900,
            )
            store.commit_authoritative_position_snapshot(
                self.projection(),
                self.checkpoint_update(outcome="failed_inconsistent"),
            )

        with self.open_store() as reopened:
            checkpoint = reopened.get_reconciliation_checkpoint(key)
            self.assertEqual(checkpoint.outcome, "failed_inconsistent")
            self.assertFalse(hasattr(checkpoint, "trading_allowed"))
            self.assertFalse(hasattr(checkpoint, "online"))

    def test_reconciliation_generation_and_optimistic_versions_reject_stale_writers(self):
        key = self.projection().position_key
        with self.open_store() as store:
            first = store.begin_reconciliation(
                key,
                generation=1,
                exchange_snapshot_at_ms=1000,
                exchange_sequence=None,
                started_at_ms=1000,
                expected_version=None,
                updated_at_ms=1000,
            )
            with self.assertRaises(ConcurrentUpdate):
                store.begin_reconciliation(
                    key,
                    generation=1,
                    exchange_snapshot_at_ms=1100,
                    exchange_sequence=None,
                    started_at_ms=1100,
                    expected_version=first.version,
                    updated_at_ms=1100,
                )
            with self.assertRaises(ConcurrentUpdate):
                store.begin_reconciliation(
                    key,
                    generation=2,
                    exchange_snapshot_at_ms=1100,
                    exchange_sequence=None,
                    started_at_ms=1100,
                    expected_version=99,
                    updated_at_ms=1100,
                )
            self.assertEqual(store.get_reconciliation_checkpoint(key), first)

    def test_checkpoint_scope_must_match_projection(self):
        with self.open_store() as store:
            other_projection = self.projection(account="account-2")
            with self.assertRaisesRegex(ValueError, "scopes differ"):
                store.commit_authoritative_position_snapshot(
                    other_projection,
                    self.checkpoint_update(),
                )
            self.assertEqual(store.load_reconciliation_checkpoints(), ())


class TerminalPersistenceBoundaryTests(unittest.TestCase):
    def test_runtime_database_directory_is_ignored(self):
        root = Path(__file__).parents[1]
        ignore_lines = {
            line.strip()
            for line in (root / ".gitignore").read_text(encoding="utf-8").splitlines()
        }
        self.assertIn("runtime/terminal/", ignore_lines)
        self.assertFalse((root / "runtime" / "terminal" / "terminal.sqlite3").exists())

    def test_persistence_has_no_network_frontend_scanner_or_secret_imports(self):
        root = Path(__file__).parents[1] / "terminal" / "persistence"
        forbidden = {
            "pybit",
            "requests",
            "websocket",
            "fastapi",
            "flask",
            "config",
            "main",
            "scanner",
            "analyzer",
            "bybit_api",
            "notification",
            "telegram_bot",
        }
        imported = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)

    def test_import_does_not_create_runtime_database(self):
        runtime_database = (
            Path(__file__).parents[1] / "runtime" / "terminal" / "terminal.sqlite3"
        )
        self.assertFalse(runtime_database.exists())


if __name__ == "__main__":
    unittest.main()
