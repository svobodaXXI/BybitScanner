import ast
import sqlite3
import tempfile
import unittest
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
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    CommandRecord,
    ConcurrentUpdate,
    DuplicateIdentity,
    ExecutionApplyResult,
    ImmutableExecutionConflict,
    PositionProjectionUpdate,
    SQLiteStore,
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
