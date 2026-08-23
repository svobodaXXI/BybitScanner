"""Controlled single-writer SQLite/WAL persistence for Terminal state."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Iterator

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
from terminal.domain.states import CommandState, transition_command

from .schema import (
    SCHEMA_STATEMENTS,
    SCHEMA_V2_MIGRATION_STATEMENTS,
    SCHEMA_V3_MIGRATION_STATEMENTS,
    SCHEMA_V4_MIGRATION_STATEMENTS,
    SCHEMA_VERSION,
)


class PersistenceError(RuntimeError):
    """Base class for fail-closed persistence failures."""


class SchemaError(PersistenceError):
    """Raised for corrupt, unknown or incompatible schema state."""


class DuplicateIdentity(PersistenceError):
    """Raised when a command or correlation identity already exists."""


class ConcurrentUpdate(PersistenceError):
    """Raised when optimistic state no longer matches supplied evidence."""


class ImmutableExecutionConflict(PersistenceError):
    """Raised when one execution identity is reused with different evidence."""


class ExecutionApplyResult(str, Enum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"


@dataclass(frozen=True, slots=True)
class CommandRecord:
    command_id: CommandId
    order_link_id: str
    trading_account_id: TradingAccountId
    category: Category
    symbol: Symbol
    position_idx: int
    command_kind: str
    side: OrderSide
    requested_notional: Notional
    normalized_price: Price | None
    normalized_quantity: Quantity | None
    origin: Origin
    controller: Controller
    current_state: CommandState
    version: int
    exchange_order_id: OrderId | None
    created_at_ms: int
    updated_at_ms: int

    def __post_init__(self) -> None:
        if not isinstance(self.order_link_id, str) or not self.order_link_id.strip():
            raise ValueError("order_link_id must be a non-empty string")
        if not isinstance(self.command_kind, str) or not self.command_kind.strip():
            raise ValueError("command_kind must be a non-empty string")
        if self.category is not Category.LINEAR or self.position_idx != 0:
            raise ValueError("Manual v1 command requires linear One-Way position_idx=0")
        if self.version < 1:
            raise ValueError("command version must be positive")
        if self.created_at_ms < 0 or self.updated_at_ms < self.created_at_ms:
            raise ValueError("command timestamps are invalid")


@dataclass(frozen=True, slots=True)
class SubmitEligibility:
    """Proof returned only after command identity has durably committed."""

    command_id: CommandId
    order_link_id: str
    committed_version: int


@dataclass(frozen=True, slots=True)
class PositionProjectionUpdate:
    """Engine-supplied operational projection; never exchange authority."""

    position_key: PositionKey
    side: PositionSide
    quantity: Quantity
    average_entry: Price | None
    realized_pnl: Decimal
    accumulated_fee: Decimal
    engaged_notional: Notional
    sync_state: str
    expected_version: int | None
    updated_at_ms: int

    def __post_init__(self) -> None:
        _decimal_text(self.realized_pnl)
        _decimal_text(self.accumulated_fee)
        if not isinstance(self.sync_state, str) or not self.sync_state.strip():
            raise ValueError("sync_state must be a non-empty string")
        if self.expected_version is not None and self.expected_version < 1:
            raise ValueError("expected projection version must be positive")
        if self.updated_at_ms < 0:
            raise ValueError("projection timestamp must not be negative")
        if self.side is PositionSide.FLAT and self.quantity.value != 0:
            raise ValueError("flat projection must have zero quantity")
        if self.side is not PositionSide.FLAT and self.quantity.value <= 0:
            raise ValueError("open projection must have positive quantity")


@dataclass(frozen=True, slots=True)
class PositionProjectionRecord:
    position_key: PositionKey
    side: PositionSide
    quantity: Quantity
    average_entry: Price | None
    realized_pnl: Decimal
    accumulated_fee: Decimal
    engaged_notional: Notional
    sync_state: str
    version: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class ReconciliationCheckpointUpdate:
    """Application-supplied reconciliation result; persistence adds no semantics."""

    position_key: PositionKey
    generation: int
    outcome: str
    exchange_snapshot_at_ms: int
    exchange_sequence: int | None
    started_at_ms: int
    completed_at_ms: int | None
    expected_version: int
    updated_at_ms: int

    def __post_init__(self) -> None:
        if self.generation < 1:
            raise ValueError("reconciliation generation must be positive")
        if not isinstance(self.outcome, str) or not self.outcome.strip():
            raise ValueError("reconciliation outcome must be non-empty")
        if self.exchange_snapshot_at_ms < 0:
            raise ValueError("exchange snapshot timestamp must not be negative")
        if self.exchange_sequence is not None and self.exchange_sequence < 0:
            raise ValueError("exchange sequence must not be negative")
        if self.started_at_ms < 0:
            raise ValueError("reconciliation start timestamp must not be negative")
        if self.completed_at_ms is not None and self.completed_at_ms < self.started_at_ms:
            raise ValueError("reconciliation completion precedes its start")
        if self.expected_version < 1:
            raise ValueError("checkpoint expected version must be positive")
        if self.updated_at_ms < self.started_at_ms:
            raise ValueError("checkpoint update precedes reconciliation start")
        if self.completed_at_ms is not None and self.updated_at_ms < self.completed_at_ms:
            raise ValueError("checkpoint update precedes reconciliation completion")


@dataclass(frozen=True, slots=True)
class ReconciliationCheckpointRecord:
    position_key: PositionKey
    generation: int
    outcome: str
    exchange_snapshot_at_ms: int
    exchange_sequence: int | None
    started_at_ms: int
    completed_at_ms: int | None
    version: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class CommandStateHistoryRecord:
    command_id: CommandId
    previous_state: CommandState | None
    next_state: CommandState
    reason: str
    occurred_at_ms: int


@dataclass(frozen=True, slots=True)
class StoreSettings:
    schema_version: int
    journal_mode: str
    foreign_keys: bool
    busy_timeout_ms: int
    synchronous: int


@dataclass(frozen=True, slots=True)
class PaperAccountRecord:
    trading_account_id: TradingAccountId
    initial_deposit_usdt: Decimal
    equity_usdt: Decimal
    version: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class CleanupRunRecord:
    cleanup_id: str
    position_key: PositionKey
    cause: str
    reconciliation_generation: int
    confirmed_at_ms: int
    status: str
    version: int
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class CleanupItemRecord:
    cleanup_id: str
    order_id: OrderId
    order_link_id: str | None
    cancel_command_id: CommandId
    cancel_order_link_id: str
    status: str
    version: int
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class ProtectionIntentRecord:
    command_id: CommandId
    position_key: PositionKey
    take_profit: Decimal | None
    stop_loss: Decimal | None
    tp_trigger_by: str
    sl_trigger_by: str
    status: str
    created_at_ms: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class ProtectionProjectionRecord:
    position_key: PositionKey
    status: str
    take_profit: Decimal | None
    stop_loss: Decimal | None
    trailing_stop: Decimal | None
    pending_command_id: CommandId | None
    version: int
    evidence_at_ms: int
    updated_at_ms: int


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        raise TypeError("persistent decimal values must be Decimal")
    if not value.is_finite():
        raise ValueError("persistent decimal values must be finite")
    return str(value)


def _load_decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise SchemaError("invalid persisted Decimal value") from exc
    if not result.is_finite():
        raise SchemaError("persisted Decimal value must be finite")
    return result


class SQLiteStore:
    """Synchronous store owned by one backend thread and writer."""

    def __init__(self, connection: sqlite3.Connection, path: Path, busy_timeout_ms: int):
        self._connection = connection
        self.path = path
        self._busy_timeout_ms = busy_timeout_ms
        self._owner_thread = threading.get_ident()

    @classmethod
    def open(cls, path: str | Path, *, busy_timeout_ms: int = 5000) -> "SQLiteStore":
        database_path = Path(path)
        if not str(database_path):
            raise ValueError("an explicit database path is required")
        if busy_timeout_ms <= 0:
            raise ValueError("busy_timeout_ms must be positive")

        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                database_path,
                timeout=busy_timeout_ms / 1000,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            connection.execute("PRAGMA synchronous = FULL")
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                raise SchemaError("database did not enter WAL mode")
            cls._initialize_or_validate_schema(connection)
            return cls(connection, database_path, busy_timeout_ms)
        except (sqlite3.DatabaseError, OSError) as exc:
            if connection is not None:
                connection.close()
            raise SchemaError("Terminal database is unavailable or corrupt") from exc
        except Exception:
            if connection is not None:
                connection.close()
            raise

    @staticmethod
    def _initialize_or_validate_schema(connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == SCHEMA_VERSION:
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 1:
            SQLiteStore._validate_required_tables(connection, version=1)
            SQLiteStore._migrate_v1_to_v2(connection)
            SQLiteStore._migrate_v2_to_v3(connection)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 2:
            SQLiteStore._validate_required_tables(connection, version=2)
            SQLiteStore._migrate_v2_to_v3(connection)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 3:
            SQLiteStore._validate_required_tables(connection, version=3)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version != 0:
            raise SchemaError(f"unsupported Terminal schema version: {version}")

        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if existing:
            raise SchemaError("unversioned database contains unknown tables")

        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v2_to_v3(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V3_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 3")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        SQLiteStore._validate_required_tables(connection, version=3)

    @staticmethod
    def _migrate_v3_to_v4(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V4_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 4")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v1_to_v2(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V2_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 2")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _validate_required_tables(connection: sqlite3.Connection, *, version: int) -> None:
        required = {
            "trading_commands",
            "command_state_history",
            "executions",
            "position_projections",
        }
        if version >= 2:
            required.add("reconciliation_checkpoints")
        if version >= 3:
            required.update({
                "cleanup_runs", "cleanup_items",
                "protection_intents", "protection_projections",
            })
        if version >= 4:
            required.add("paper_accounts")
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        if not required.issubset(actual):
            raise SchemaError("Terminal schema is incomplete")

    def close(self) -> None:
        self._assert_owner()
        self._connection.close()

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _assert_owner(self) -> None:
        if threading.get_ident() != self._owner_thread:
            raise PersistenceError("SQLiteStore must be used by its owning writer thread")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        self._assert_owner()
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        else:
            try:
                self._connection.execute("COMMIT")
            except Exception:
                if self._connection.in_transaction:
                    self._connection.execute("ROLLBACK")
                raise

    def settings(self) -> StoreSettings:
        self._assert_owner()
        return StoreSettings(
            schema_version=int(self._connection.execute("PRAGMA user_version").fetchone()[0]),
            journal_mode=str(self._connection.execute("PRAGMA journal_mode").fetchone()[0]).lower(),
            foreign_keys=bool(self._connection.execute("PRAGMA foreign_keys").fetchone()[0]),
            busy_timeout_ms=int(self._connection.execute("PRAGMA busy_timeout").fetchone()[0]),
            synchronous=int(self._connection.execute("PRAGMA synchronous").fetchone()[0]),
        )

    def get_paper_account(
        self,
        trading_account_id: TradingAccountId,
    ) -> PaperAccountRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """
            SELECT trading_account_id, initial_deposit_usdt, equity_usdt,
                   version, updated_at_ms
            FROM paper_accounts
            WHERE trading_account_id = ?
            """,
            (trading_account_id.value,),
        ).fetchone()
        if row is None:
            return None
        return PaperAccountRecord(
            trading_account_id=TradingAccountId(row[0]),
            initial_deposit_usdt=Decimal(row[1]),
            equity_usdt=Decimal(row[2]),
            version=int(row[3]),
            updated_at_ms=int(row[4]),
        )

    def initialize_paper_account(
        self,
        trading_account_id: TradingAccountId,
        initial_deposit_usdt: Decimal,
        *,
        updated_at_ms: int,
    ) -> PaperAccountRecord:
        deposit_text = _decimal_text(initial_deposit_usdt)
        if initial_deposit_usdt <= 0:
            raise ValueError("paper initial deposit must be positive")
        if updated_at_ms < 0:
            raise ValueError("paper account timestamp must not be negative")

        existing = self.get_paper_account(trading_account_id)
        if existing is not None:
            if existing.initial_deposit_usdt != initial_deposit_usdt:
                raise PersistenceError(
                    "paper account already exists with a different initial deposit"
                )
            return existing

        with self._transaction():
            self._connection.execute(
                """
                INSERT INTO paper_accounts (
                    trading_account_id, initial_deposit_usdt, equity_usdt,
                    version, updated_at_ms
                ) VALUES (?, ?, ?, 1, ?)
                """,
                (
                    trading_account_id.value,
                    deposit_text,
                    deposit_text,
                    updated_at_ms,
                ),
            )

        return PaperAccountRecord(
            trading_account_id=trading_account_id,
            initial_deposit_usdt=initial_deposit_usdt,
            equity_usdt=initial_deposit_usdt,
            version=1,
            updated_at_ms=updated_at_ms,
        )

    def persist_command_before_submit(
        self,
        record: CommandRecord,
        *,
        reason: str = "admitted before exchange submission",
    ) -> SubmitEligibility:
        if record.current_state is not CommandState.ADMITTED:
            raise ValueError("submit eligibility requires an ADMITTED command")
        if not reason.strip():
            raise ValueError("command history reason must be non-empty")

        try:
            with self._transaction():
                self._connection.execute(
                    """
                    INSERT INTO trading_commands (
                        command_id, order_link_id, trading_account_id, category, symbol,
                        position_idx, command_kind, side, requested_notional,
                        normalized_price, normalized_quantity, origin, controller,
                        current_state, version, exchange_order_id, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.command_id.value,
                        record.order_link_id,
                        record.trading_account_id.value,
                        record.category.value,
                        record.symbol.value,
                        record.position_idx,
                        record.command_kind,
                        record.side.value,
                        _decimal_text(record.requested_notional.value),
                        _optional_decimal(record.normalized_price),
                        _optional_decimal(record.normalized_quantity),
                        record.origin.value,
                        record.controller.value,
                        record.current_state.value,
                        record.version,
                        record.exchange_order_id.value if record.exchange_order_id else None,
                        record.created_at_ms,
                        record.updated_at_ms,
                    ),
                )
                self._connection.execute(
                    """
                    INSERT INTO command_state_history (
                        command_id, previous_state, next_state, reason, occurred_at_ms
                    ) VALUES (?, NULL, ?, ?, ?)
                    """,
                    (record.command_id.value, record.current_state.value, reason, record.updated_at_ms),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateIdentity("command_id or order_link_id already exists") from exc

        return SubmitEligibility(record.command_id, record.order_link_id, record.version)

    def transition_command_state(
        self,
        command_id: CommandId,
        expected_state: CommandState,
        next_state: CommandState,
        *,
        expected_version: int,
        reason: str,
        occurred_at_ms: int,
        exchange_order_id: OrderId | None = None,
    ) -> CommandRecord:
        transition_command(expected_state, next_state)
        if not reason.strip():
            raise ValueError("transition reason must be non-empty")

        with self._transaction():
            values: list[object] = [
                next_state.value,
                expected_version + 1,
                occurred_at_ms,
            ]
            order_sql = ""
            if exchange_order_id is not None:
                order_sql = ", exchange_order_id = ?"
                values.append(exchange_order_id.value)
            values.extend([command_id.value, expected_state.value, expected_version])
            cursor = self._connection.execute(
                f"""
                UPDATE trading_commands
                SET current_state = ?, version = ?, updated_at_ms = ?{order_sql}
                WHERE command_id = ? AND current_state = ? AND version = ?
                """,
                values,
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("command state/version no longer matches")
            self._connection.execute(
                """
                INSERT INTO command_state_history (
                    command_id, previous_state, next_state, reason, occurred_at_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    command_id.value,
                    expected_state.value,
                    next_state.value,
                    reason,
                    occurred_at_ms,
                ),
            )
        record = self.get_command(command_id)
        if record is None:
            raise PersistenceError("committed command disappeared")
        return record

    def get_command(self, command_id: CommandId) -> CommandRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM trading_commands WHERE command_id = ?",
            (command_id.value,),
        ).fetchone()
        return _command_from_row(row) if row is not None else None

    def load_unfinished_commands(self) -> tuple[CommandRecord, ...]:
        self._assert_owner()
        final_states = (
            CommandState.FILLED.value,
            CommandState.CANCELLED.value,
            CommandState.AMENDED.value,
            CommandState.REJECTED.value,
            CommandState.FAILED.value,
        )
        rows = self._connection.execute(
            """
            SELECT * FROM trading_commands
            WHERE current_state NOT IN (?, ?, ?, ?, ?)
            ORDER BY created_at_ms, command_id
            """,
            final_states,
        )
        return tuple(_command_from_row(row) for row in rows)

    def load_command_history(
        self, command_id: CommandId
    ) -> tuple[CommandStateHistoryRecord, ...]:
        self._assert_owner()
        rows = self._connection.execute(
            """
            SELECT command_id, previous_state, next_state, reason, occurred_at_ms
            FROM command_state_history
            WHERE command_id = ?
            ORDER BY history_id
            """,
            (command_id.value,),
        )
        return tuple(
            CommandStateHistoryRecord(
                command_id=CommandId(row["command_id"]),
                previous_state=(
                    CommandState(row["previous_state"])
                    if row["previous_state"] is not None
                    else None
                ),
                next_state=CommandState(row["next_state"]),
                reason=row["reason"],
                occurred_at_ms=int(row["occurred_at_ms"]),
            )
            for row in rows
        )

    def apply_execution_once(
        self,
        execution: Execution,
        projection: PositionProjectionUpdate,
        *,
        command_id: CommandId | None = None,
    ) -> ExecutionApplyResult:
        if execution.dedup_key.trading_account_id != projection.position_key.trading_account_id:
            raise ValueError("execution and projection account differ")
        if execution.dedup_key.category is not projection.position_key.category:
            raise ValueError("execution and projection category differ")
        if execution.symbol != projection.position_key.symbol:
            raise ValueError("execution and projection symbol differ")

        with self._transaction():
            existing = self._execution_row(execution.dedup_key)
            if existing is not None:
                if _execution_from_row(existing) != execution:
                    raise ImmutableExecutionConflict(
                        "execution identity already exists with different immutable evidence"
                    )
                if command_id is not None:
                    self._correlate_command_order(command_id, execution.order_id)
                return ExecutionApplyResult.DUPLICATE

            self._insert_execution(execution)
            self._write_projection(projection)
            if command_id is not None:
                self._correlate_command_order(command_id, execution.order_id)
        return ExecutionApplyResult.APPLIED

    def _correlate_command_order(self, command_id: CommandId, order_id: OrderId) -> None:
        cursor = self._connection.execute(
            """
            UPDATE trading_commands
            SET exchange_order_id = COALESCE(exchange_order_id, ?)
            WHERE command_id = ?
              AND (exchange_order_id IS NULL OR exchange_order_id = ?)
            """,
            (order_id.value, command_id.value, order_id.value),
        )
        if cursor.rowcount != 1:
            raise ConcurrentUpdate("command/order correlation is missing or contradictory")

    def _insert_execution(self, execution: Execution) -> None:
        self._connection.execute(
            """
            INSERT INTO executions (
                trading_account_id, category, exec_id, order_id, symbol,
                side, price, quantity, fee, exchange_timestamp_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution.dedup_key.trading_account_id.value,
                execution.dedup_key.category.value,
                execution.dedup_key.exec_id.value,
                execution.order_id.value,
                execution.symbol.value,
                execution.side.value,
                _decimal_text(execution.price.value),
                _decimal_text(execution.quantity.value),
                _decimal_text(execution.fee),
                execution.exchange_timestamp_ms,
            ),
        )

    def _write_projection(self, update: PositionProjectionUpdate) -> None:
        key = update.position_key
        existing = self._connection.execute(
            """
            SELECT version FROM position_projections
            WHERE trading_account_id = ? AND category = ? AND symbol = ? AND position_idx = ?
            """,
            (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
        ).fetchone()

        if existing is None:
            if update.expected_version is not None:
                raise ConcurrentUpdate("projection expected to exist")
            new_version = 1
            self._connection.execute(
                """
                INSERT INTO position_projections (
                    trading_account_id, category, symbol, position_idx, side, quantity,
                    average_entry, realized_pnl, accumulated_fee, engaged_notional,
                    sync_state, version, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _projection_values(update, new_version),
            )
            return

        current_version = int(existing["version"])
        if update.expected_version != current_version:
            raise ConcurrentUpdate("projection version no longer matches")
        new_version = current_version + 1
        cursor = self._connection.execute(
            """
            UPDATE position_projections
            SET side = ?, quantity = ?, average_entry = ?, realized_pnl = ?,
                accumulated_fee = ?, engaged_notional = ?, sync_state = ?,
                version = ?, updated_at_ms = ?
            WHERE trading_account_id = ? AND category = ? AND symbol = ?
              AND position_idx = ? AND version = ?
            """,
            (
                update.side.value,
                _decimal_text(update.quantity.value),
                _optional_decimal(update.average_entry),
                _decimal_text(update.realized_pnl),
                _decimal_text(update.accumulated_fee),
                _decimal_text(update.engaged_notional.value),
                update.sync_state,
                new_version,
                update.updated_at_ms,
                key.trading_account_id.value,
                key.category.value,
                key.symbol.value,
                key.position_idx,
                current_version,
            ),
        )
        if cursor.rowcount != 1:
            raise ConcurrentUpdate("projection changed concurrently")

    def _execution_row(self, key: ExecutionDedupKey) -> sqlite3.Row | None:
        return self._connection.execute(
            """
            SELECT * FROM executions
            WHERE trading_account_id = ? AND category = ? AND exec_id = ?
            """,
            (key.trading_account_id.value, key.category.value, key.exec_id.value),
        ).fetchone()

    def get_execution(self, key: ExecutionDedupKey) -> Execution | None:
        self._assert_owner()
        row = self._execution_row(key)
        return _execution_from_row(row) if row is not None else None

    def load_executions(self) -> tuple[Execution, ...]:
        self._assert_owner()
        rows = self._connection.execute(
            """
            SELECT * FROM executions
            ORDER BY exchange_timestamp_ms, trading_account_id, category, exec_id
            """
        )
        return tuple(_execution_from_row(row) for row in rows)

    def get_position_projection(
        self, key: PositionKey
    ) -> PositionProjectionRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """
            SELECT * FROM position_projections
            WHERE trading_account_id = ? AND category = ? AND symbol = ? AND position_idx = ?
            """,
            (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
        ).fetchone()
        return _projection_from_row(row) if row is not None else None

    def begin_reconciliation(
        self,
        position_key: PositionKey,
        *,
        generation: int,
        exchange_snapshot_at_ms: int,
        exchange_sequence: int | None,
        started_at_ms: int,
        expected_version: int | None,
        updated_at_ms: int,
    ) -> ReconciliationCheckpointRecord:
        """Durably mark a supplied scope/generation as unfinished recovery work."""

        if generation < 1:
            raise ValueError("reconciliation generation must be positive")
        if exchange_snapshot_at_ms < 0:
            raise ValueError("exchange snapshot timestamp must not be negative")
        if exchange_sequence is not None and exchange_sequence < 0:
            raise ValueError("exchange sequence must not be negative")
        if started_at_ms < 0 or updated_at_ms < started_at_ms:
            raise ValueError("reconciliation timestamps are invalid")
        if expected_version is not None and expected_version < 1:
            raise ValueError("checkpoint expected version must be positive")

        key = position_key
        with self._transaction():
            existing = self._connection.execute(
                """
                SELECT generation, version FROM reconciliation_checkpoints
                WHERE trading_account_id = ? AND category = ? AND symbol = ?
                  AND position_idx = ?
                """,
                (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
            ).fetchone()
            if existing is None:
                if expected_version is not None:
                    raise ConcurrentUpdate("checkpoint expected to exist")
                self._connection.execute(
                    """
                    INSERT INTO reconciliation_checkpoints (
                        trading_account_id, category, symbol, position_idx,
                        generation, outcome, exchange_snapshot_at_ms, exchange_sequence,
                        started_at_ms, completed_at_ms, version, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, 'in_progress', ?, ?, ?, NULL, 1, ?)
                    """,
                    (
                        key.trading_account_id.value,
                        key.category.value,
                        key.symbol.value,
                        key.position_idx,
                        generation,
                        exchange_snapshot_at_ms,
                        exchange_sequence,
                        started_at_ms,
                        updated_at_ms,
                    ),
                )
            else:
                current_generation = int(existing["generation"])
                current_version = int(existing["version"])
                if expected_version != current_version:
                    raise ConcurrentUpdate("checkpoint version no longer matches")
                if generation <= current_generation:
                    raise ConcurrentUpdate("reconciliation generation is stale")
                cursor = self._connection.execute(
                    """
                    UPDATE reconciliation_checkpoints
                    SET generation = ?, outcome = 'in_progress',
                        exchange_snapshot_at_ms = ?, exchange_sequence = ?,
                        started_at_ms = ?, completed_at_ms = NULL,
                        version = ?, updated_at_ms = ?
                    WHERE trading_account_id = ? AND category = ? AND symbol = ?
                      AND position_idx = ? AND generation = ? AND version = ?
                    """,
                    (
                        generation,
                        exchange_snapshot_at_ms,
                        exchange_sequence,
                        started_at_ms,
                        current_version + 1,
                        updated_at_ms,
                        key.trading_account_id.value,
                        key.category.value,
                        key.symbol.value,
                        key.position_idx,
                        current_generation,
                        current_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConcurrentUpdate("checkpoint changed concurrently")

        record = self.get_reconciliation_checkpoint(position_key)
        if record is None:
            raise PersistenceError("committed checkpoint disappeared")
        return record

    def commit_authoritative_position_snapshot(
        self,
        projection: PositionProjectionUpdate,
        checkpoint: ReconciliationCheckpointUpdate,
    ) -> tuple[PositionProjectionRecord, ReconciliationCheckpointRecord]:
        """Atomically persist an application-supplied snapshot and recovery outcome."""

        if projection.position_key != checkpoint.position_key:
            raise ValueError("projection and reconciliation checkpoint scopes differ")
        if checkpoint.completed_at_ms is None:
            raise ValueError("snapshot commit requires a completed reconciliation outcome")

        key = projection.position_key
        with self._transaction():
            self._write_projection(projection)
            cursor = self._connection.execute(
                """
                UPDATE reconciliation_checkpoints
                SET outcome = ?, exchange_snapshot_at_ms = ?, exchange_sequence = ?,
                    completed_at_ms = ?, version = ?, updated_at_ms = ?
                WHERE trading_account_id = ? AND category = ? AND symbol = ?
                  AND position_idx = ? AND generation = ? AND version = ?
                  AND started_at_ms = ?
                """,
                (
                    checkpoint.outcome.strip(),
                    checkpoint.exchange_snapshot_at_ms,
                    checkpoint.exchange_sequence,
                    checkpoint.completed_at_ms,
                    checkpoint.expected_version + 1,
                    checkpoint.updated_at_ms,
                    key.trading_account_id.value,
                    key.category.value,
                    key.symbol.value,
                    key.position_idx,
                    checkpoint.generation,
                    checkpoint.expected_version,
                    checkpoint.started_at_ms,
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("checkpoint generation/version no longer matches")

        projection_record = self.get_position_projection(key)
        checkpoint_record = self.get_reconciliation_checkpoint(key)
        if projection_record is None or checkpoint_record is None:
            raise PersistenceError("committed reconciliation state disappeared")
        return projection_record, checkpoint_record

    def get_reconciliation_checkpoint(
        self, key: PositionKey
    ) -> ReconciliationCheckpointRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """
            SELECT * FROM reconciliation_checkpoints
            WHERE trading_account_id = ? AND category = ? AND symbol = ? AND position_idx = ?
            """,
            (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
        ).fetchone()
        return _checkpoint_from_row(row) if row is not None else None

    def load_reconciliation_checkpoints(self) -> tuple[ReconciliationCheckpointRecord, ...]:
        self._assert_owner()
        rows = self._connection.execute(
            """
            SELECT * FROM reconciliation_checkpoints
            ORDER BY trading_account_id, category, symbol, position_idx
            """
        )
        return tuple(_checkpoint_from_row(row) for row in rows)

    def create_cleanup_run(self, record: CleanupRunRecord) -> CleanupRunRecord:
        key = record.position_key
        try:
            with self._transaction():
                self._connection.execute(
                    """
                    INSERT INTO cleanup_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.cleanup_id, key.trading_account_id.value, key.category.value,
                        key.symbol.value, key.position_idx, record.cause,
                        record.reconciliation_generation, record.confirmed_at_ms,
                        record.status, record.version, record.created_at_ms, record.updated_at_ms,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self.get_cleanup_run(record.cleanup_id)
            if existing == record:
                return existing
            raise DuplicateIdentity("cleanup identity already exists") from exc
        return self.get_cleanup_run(record.cleanup_id) or record

    def get_cleanup_run(self, cleanup_id: str) -> CleanupRunRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM cleanup_runs WHERE cleanup_id = ?", (cleanup_id,)
        ).fetchone()
        return _cleanup_run_from_row(row) if row else None

    def update_cleanup_run(
        self, cleanup_id: str, *, expected_version: int, status: str, updated_at_ms: int,
    ) -> CleanupRunRecord:
        with self._transaction():
            cursor = self._connection.execute(
                """UPDATE cleanup_runs SET status=?, version=?, updated_at_ms=?
                   WHERE cleanup_id=? AND version=?""",
                (status, expected_version + 1, updated_at_ms, cleanup_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("cleanup run version no longer matches")
        result = self.get_cleanup_run(cleanup_id)
        if result is None:
            raise PersistenceError("cleanup run disappeared")
        return result

    def add_cleanup_item(self, record: CleanupItemRecord) -> CleanupItemRecord:
        try:
            with self._transaction():
                self._connection.execute(
                    "INSERT INTO cleanup_items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        record.cleanup_id, record.order_id.value, record.order_link_id,
                        record.cancel_command_id.value, record.cancel_order_link_id,
                        record.status, record.version,
                        record.created_at_ms, record.updated_at_ms,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self.get_cleanup_item(record.cleanup_id, record.order_id)
            if existing == record:
                return existing
            raise DuplicateIdentity("cleanup item already exists") from exc
        return self.get_cleanup_item(record.cleanup_id, record.order_id) or record

    def get_cleanup_item(
        self, cleanup_id: str, order_id: OrderId,
    ) -> CleanupItemRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM cleanup_items WHERE cleanup_id=? AND order_id=?",
            (cleanup_id, order_id.value),
        ).fetchone()
        return _cleanup_item_from_row(row) if row else None

    def load_cleanup_items(self, cleanup_id: str) -> tuple[CleanupItemRecord, ...]:
        self._assert_owner()
        rows = self._connection.execute(
            "SELECT * FROM cleanup_items WHERE cleanup_id=? ORDER BY order_id", (cleanup_id,)
        )
        return tuple(_cleanup_item_from_row(row) for row in rows)

    def update_cleanup_item(
        self, cleanup_id: str, order_id: OrderId, *, expected_version: int,
        status: str, updated_at_ms: int,
    ) -> CleanupItemRecord:
        with self._transaction():
            cursor = self._connection.execute(
                """UPDATE cleanup_items SET status=?, version=?, updated_at_ms=?
                   WHERE cleanup_id=? AND order_id=? AND version=?""",
                (status, expected_version + 1, updated_at_ms, cleanup_id,
                 order_id.value, expected_version),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("cleanup item version no longer matches")
        result = self.get_cleanup_item(cleanup_id, order_id)
        if result is None:
            raise PersistenceError("cleanup item disappeared")
        return result

    def persist_protection_intent(self, record: ProtectionIntentRecord) -> None:
        key = record.position_key
        with self._transaction():
            self._connection.execute(
                "INSERT INTO protection_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.command_id.value, key.trading_account_id.value, key.category.value,
                    key.symbol.value, key.position_idx, _optional_raw_decimal(record.take_profit),
                    _optional_raw_decimal(record.stop_loss), record.tp_trigger_by,
                    record.sl_trigger_by, record.status, record.created_at_ms, record.updated_at_ms,
                ),
            )

    def get_protection_intent(
        self, command_id: CommandId,
    ) -> ProtectionIntentRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM protection_intents WHERE command_id=?", (command_id.value,)
        ).fetchone()
        return _protection_intent_from_row(row) if row else None

    def update_protection_intent_status(
        self, command_id: CommandId, *, status: str, updated_at_ms: int,
    ) -> ProtectionIntentRecord:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE protection_intents SET status=?, updated_at_ms=? WHERE command_id=?",
                (status, updated_at_ms, command_id.value),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("protection intent does not exist")
        return self.get_protection_intent(command_id)  # type: ignore[return-value]

    def upsert_protection_projection(
        self, record: ProtectionProjectionRecord, *, expected_version: int | None,
    ) -> ProtectionProjectionRecord:
        key = record.position_key
        with self._transaction():
            existing = self._connection.execute(
                """SELECT version FROM protection_projections WHERE trading_account_id=?
                   AND category=? AND symbol=? AND position_idx=?""",
                (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
            ).fetchone()
            if existing is None:
                if expected_version is not None:
                    raise ConcurrentUpdate("protection projection expected to exist")
                self._connection.execute(
                    "INSERT INTO protection_projections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                    (
                        key.trading_account_id.value, key.category.value, key.symbol.value,
                        key.position_idx, record.status, _optional_raw_decimal(record.take_profit),
                        _optional_raw_decimal(record.stop_loss),
                        _optional_raw_decimal(record.trailing_stop),
                        record.pending_command_id.value if record.pending_command_id else None,
                        record.evidence_at_ms, record.updated_at_ms,
                    ),
                )
            else:
                version = int(existing["version"])
                if expected_version != version:
                    raise ConcurrentUpdate("protection projection version no longer matches")
                self._connection.execute(
                    """UPDATE protection_projections SET status=?, take_profit=?, stop_loss=?,
                       trailing_stop=?, pending_command_id=?, version=?, evidence_at_ms=?, updated_at_ms=?
                       WHERE trading_account_id=? AND category=? AND symbol=? AND position_idx=? AND version=?""",
                    (
                        record.status, _optional_raw_decimal(record.take_profit),
                        _optional_raw_decimal(record.stop_loss),
                        _optional_raw_decimal(record.trailing_stop),
                        record.pending_command_id.value if record.pending_command_id else None,
                        version + 1, record.evidence_at_ms, record.updated_at_ms,
                        key.trading_account_id.value, key.category.value, key.symbol.value,
                        key.position_idx, version,
                    ),
                )
        result = self.get_protection_projection(key)
        if result is None:
            raise PersistenceError("protection projection disappeared")
        return result

    def get_protection_projection(
        self, key: PositionKey,
    ) -> ProtectionProjectionRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """SELECT * FROM protection_projections WHERE trading_account_id=?
               AND category=? AND symbol=? AND position_idx=?""",
            (key.trading_account_id.value, key.category.value, key.symbol.value, key.position_idx),
        ).fetchone()
        return _protection_projection_from_row(row) if row else None


def _optional_decimal(value: Price | Quantity | None) -> str | None:
    return None if value is None else _decimal_text(value.value)


def _optional_raw_decimal(value: Decimal | None) -> str | None:
    return None if value is None else _decimal_text(value)


def _position_key_from_row(row: sqlite3.Row) -> PositionKey:
    return PositionKey(
        TradingAccountId(row["trading_account_id"]), Category(row["category"]),
        Symbol(row["symbol"]), int(row["position_idx"]),
    )


def _cleanup_run_from_row(row: sqlite3.Row) -> CleanupRunRecord:
    return CleanupRunRecord(
        row["cleanup_id"], _position_key_from_row(row), row["cause"],
        int(row["reconciliation_generation"]), int(row["confirmed_at_ms"]),
        row["status"], int(row["version"]), int(row["created_at_ms"]),
        int(row["updated_at_ms"]),
    )


def _cleanup_item_from_row(row: sqlite3.Row) -> CleanupItemRecord:
    return CleanupItemRecord(
        row["cleanup_id"], OrderId(row["order_id"]), row["order_link_id"],
        CommandId(row["cancel_command_id"]), row["cancel_order_link_id"],
        row["status"], int(row["version"]),
        int(row["created_at_ms"]), int(row["updated_at_ms"]),
    )


def _protection_intent_from_row(row: sqlite3.Row) -> ProtectionIntentRecord:
    return ProtectionIntentRecord(
        CommandId(row["command_id"]), _position_key_from_row(row),
        _load_decimal(row["take_profit"]) if row["take_profit"] is not None else None,
        _load_decimal(row["stop_loss"]) if row["stop_loss"] is not None else None,
        row["tp_trigger_by"], row["sl_trigger_by"], row["status"],
        int(row["created_at_ms"]), int(row["updated_at_ms"]),
    )


def _protection_projection_from_row(row: sqlite3.Row) -> ProtectionProjectionRecord:
    return ProtectionProjectionRecord(
        _position_key_from_row(row), row["status"],
        _load_decimal(row["take_profit"]) if row["take_profit"] is not None else None,
        _load_decimal(row["stop_loss"]) if row["stop_loss"] is not None else None,
        _load_decimal(row["trailing_stop"]) if row["trailing_stop"] is not None else None,
        CommandId(row["pending_command_id"]) if row["pending_command_id"] else None,
        int(row["version"]), int(row["evidence_at_ms"]), int(row["updated_at_ms"]),
    )


def _command_from_row(row: sqlite3.Row) -> CommandRecord:
    return CommandRecord(
        command_id=CommandId(row["command_id"]),
        order_link_id=row["order_link_id"],
        trading_account_id=TradingAccountId(row["trading_account_id"]),
        category=Category(row["category"]),
        symbol=Symbol(row["symbol"]),
        position_idx=int(row["position_idx"]),
        command_kind=row["command_kind"],
        side=OrderSide(row["side"]),
        requested_notional=Notional(_load_decimal(row["requested_notional"])),
        normalized_price=(
            Price(_load_decimal(row["normalized_price"]))
            if row["normalized_price"] is not None
            else None
        ),
        normalized_quantity=(
            Quantity(_load_decimal(row["normalized_quantity"]))
            if row["normalized_quantity"] is not None
            else None
        ),
        origin=Origin(row["origin"]),
        controller=Controller(row["controller"]),
        current_state=CommandState(row["current_state"]),
        version=int(row["version"]),
        exchange_order_id=OrderId(row["exchange_order_id"]) if row["exchange_order_id"] else None,
        created_at_ms=int(row["created_at_ms"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _execution_from_row(row: sqlite3.Row) -> Execution:
    return Execution(
        dedup_key=ExecutionDedupKey(
            TradingAccountId(row["trading_account_id"]),
            Category(row["category"]),
            ExecutionId(row["exec_id"]),
        ),
        order_id=OrderId(row["order_id"]),
        symbol=Symbol(row["symbol"]),
        side=OrderSide(row["side"]),
        price=Price(_load_decimal(row["price"])),
        quantity=Quantity(_load_decimal(row["quantity"])),
        fee=_load_decimal(row["fee"]),
        exchange_timestamp_ms=int(row["exchange_timestamp_ms"]),
    )


def _projection_values(update: PositionProjectionUpdate, version: int) -> tuple[object, ...]:
    key = update.position_key
    return (
        key.trading_account_id.value,
        key.category.value,
        key.symbol.value,
        key.position_idx,
        update.side.value,
        _decimal_text(update.quantity.value),
        _optional_decimal(update.average_entry),
        _decimal_text(update.realized_pnl),
        _decimal_text(update.accumulated_fee),
        _decimal_text(update.engaged_notional.value),
        update.sync_state,
        version,
        update.updated_at_ms,
    )


def _projection_from_row(row: sqlite3.Row) -> PositionProjectionRecord:
    return PositionProjectionRecord(
        position_key=PositionKey(
            TradingAccountId(row["trading_account_id"]),
            Category(row["category"]),
            Symbol(row["symbol"]),
            int(row["position_idx"]),
        ),
        side=PositionSide(row["side"]),
        quantity=Quantity(_load_decimal(row["quantity"])),
        average_entry=(
            Price(_load_decimal(row["average_entry"]))
            if row["average_entry"] is not None
            else None
        ),
        realized_pnl=_load_decimal(row["realized_pnl"]),
        accumulated_fee=_load_decimal(row["accumulated_fee"]),
        engaged_notional=Notional(_load_decimal(row["engaged_notional"])),
        sync_state=row["sync_state"],
        version=int(row["version"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _checkpoint_from_row(row: sqlite3.Row) -> ReconciliationCheckpointRecord:
    return ReconciliationCheckpointRecord(
        position_key=PositionKey(
            TradingAccountId(row["trading_account_id"]),
            Category(row["category"]),
            Symbol(row["symbol"]),
            int(row["position_idx"]),
        ),
        generation=int(row["generation"]),
        outcome=row["outcome"],
        exchange_snapshot_at_ms=int(row["exchange_snapshot_at_ms"]),
        exchange_sequence=(
            int(row["exchange_sequence"])
            if row["exchange_sequence"] is not None
            else None
        ),
        started_at_ms=int(row["started_at_ms"]),
        completed_at_ms=(
            int(row["completed_at_ms"])
            if row["completed_at_ms"] is not None
            else None
        ),
        version=int(row["version"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )
