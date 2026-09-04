"""Controlled single-writer SQLite/WAL persistence for Terminal state."""

from __future__ import annotations

import hashlib
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
    SCHEMA_V5_MIGRATION_STATEMENTS,
    SCHEMA_V6_MIGRATION_STATEMENTS,
    SCHEMA_V7_MIGRATION_STATEMENTS,
    SCHEMA_V8_MIGRATION_STATEMENTS,
    SCHEMA_V9_MIGRATION_STATEMENTS,
    SCHEMA_V10_MIGRATION_STATEMENTS,
    SCHEMA_V11_MIGRATION_STATEMENTS,
    SCHEMA_V12_MIGRATION_STATEMENTS,
    SCHEMA_V13_MIGRATION_STATEMENTS,
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
class LiveMarketActionRecord:
    trading_account_id: TradingAccountId
    session_generation: int
    client_action_id: str
    request_fingerprint: str
    command_id: CommandId
    order_link_id: str
    dispatch_started: bool
    created_at_ms: int


class LiveLimitAcceptanceState(str, Enum):
    ARMED = "ARMED"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class LiveLimitAcceptanceSessionRecord:
    acceptance_session_id: str
    trading_account_id: TradingAccountId
    environment: str
    symbol: Symbol
    capability: str
    state: LiveLimitAcceptanceState
    max_create_count: int
    aggregate_notional_ceiling: Decimal
    per_order_ceiling: Decimal
    reserved_count: int
    reserved_notional: Decimal
    opened_at_ms: int
    expires_at_ms: int
    authorized_build_sha: str
    database_identity: str
    operator_authorization_reference: str
    authorized_session_generation: int
    updated_at_ms: int


@dataclass(frozen=True, slots=True)
class LiveLimitRuntimeAttribution:
    build_sha: str
    process_instance_id: str
    process_started_at_ms: int
    process_id: int
    database_path: str
    database_identity: str
    schema_version: int
    host_identity: str


@dataclass(frozen=True, slots=True)
class LiveLimitActionRecord:
    acceptance_session_id: str
    trading_account_id: TradingAccountId
    environment: str
    capability: str
    session_generation: int
    symbol: Symbol
    operation: str
    client_action_id: str
    request_fingerprint: str
    command_id: CommandId
    order_link_id: str
    exchange_order_id: OrderId | None
    dispatch_state: str
    reconciliation_state: str
    reserved_count: int
    reserved_notional: Decimal
    runtime: LiveLimitRuntimeAttribution
    created_at_ms: int
    updated_at_ms: int
    outcome_disposition: str | None
    outcome_reason: str | None
    outcome_at_ms: int | None
    outcome_code: int | None


@dataclass(frozen=True, slots=True)
class LiveLimitAdmissionResult:
    action: LiveLimitActionRecord
    created: bool


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
class PaperLimitOrderRecord:
    order_id: OrderId
    order_link_id: str
    trading_account_id: TradingAccountId
    symbol: Symbol
    side: OrderSide
    price: Decimal
    quantity: Decimal
    filled_quantity: Decimal
    time_in_force: str
    status: str
    created_at_ms: int
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


def _paper_limit_from_row(row: sqlite3.Row) -> PaperLimitOrderRecord:
    return PaperLimitOrderRecord(
        order_id=OrderId(row["order_id"]),
        order_link_id=row["order_link_id"],
        trading_account_id=TradingAccountId(row["trading_account_id"]),
        symbol=Symbol(row["symbol"]),
        side=OrderSide(row["side"]),
        price=_load_decimal(row["price"]),
        quantity=_load_decimal(row["quantity"]),
        filled_quantity=_load_decimal(row["filled_quantity"]),
        time_in_force=row["time_in_force"],
        status=row["status"],
        created_at_ms=int(row["created_at_ms"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _live_limit_session_from_row(row: sqlite3.Row) -> LiveLimitAcceptanceSessionRecord:
    return LiveLimitAcceptanceSessionRecord(
        acceptance_session_id=row["acceptance_session_id"],
        trading_account_id=TradingAccountId(row["trading_account_id"]),
        environment=row["environment"],
        symbol=Symbol(row["symbol"]),
        capability=row["capability"],
        state=LiveLimitAcceptanceState(row["state"]),
        max_create_count=int(row["max_create_count"]),
        aggregate_notional_ceiling=_load_decimal(row["aggregate_notional_ceiling"]),
        per_order_ceiling=_load_decimal(row["per_order_ceiling"]),
        reserved_count=int(row["reserved_count"]),
        reserved_notional=_load_decimal(row["reserved_notional"]),
        opened_at_ms=int(row["opened_at_ms"]),
        expires_at_ms=int(row["expires_at_ms"]),
        authorized_build_sha=row["authorized_build_sha"],
        database_identity=row["database_identity"],
        operator_authorization_reference=row["operator_authorization_reference"],
        authorized_session_generation=int(row["authorized_session_generation"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _live_limit_action_from_row(row: sqlite3.Row) -> LiveLimitActionRecord:
    runtime = LiveLimitRuntimeAttribution(
        build_sha=row["build_sha"],
        process_instance_id=row["process_instance_id"],
        process_started_at_ms=int(row["process_started_at_ms"]),
        process_id=int(row["process_id"]),
        database_path=row["database_path"],
        database_identity=row["database_identity"],
        schema_version=int(row["schema_version"]),
        host_identity=row["host_identity"],
    )
    return LiveLimitActionRecord(
        acceptance_session_id=row["acceptance_session_id"],
        trading_account_id=TradingAccountId(row["trading_account_id"]),
        environment=row["environment"],
        capability=row["capability"],
        session_generation=int(row["session_generation"]),
        symbol=Symbol(row["symbol"]),
        operation=row["operation"],
        client_action_id=row["client_action_id"],
        request_fingerprint=row["request_fingerprint"],
        command_id=CommandId(row["command_id"]),
        order_link_id=row["order_link_id"],
        exchange_order_id=(OrderId(row["exchange_order_id"])
                           if row["exchange_order_id"] is not None else None),
        dispatch_state=row["dispatch_state"],
        reconciliation_state=row["reconciliation_state"],
        reserved_count=int(row["reserved_count"]),
        reserved_notional=_load_decimal(row["reserved_notional"]),
        runtime=runtime,
        created_at_ms=int(row["created_at_ms"]),
        updated_at_ms=int(row["updated_at_ms"]),
        outcome_disposition=row["outcome_disposition"],
        outcome_reason=row["outcome_reason"],
        outcome_at_ms=(int(row["outcome_at_ms"])
                       if row["outcome_at_ms"] is not None else None),
        outcome_code=(int(row["outcome_code"])
                      if row["outcome_code"] is not None else None),
    )


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
        if version == 12:
            SQLiteStore._validate_required_tables(connection, version=12)
            SQLiteStore._migrate_v12_to_v13(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 11:
            SQLiteStore._validate_required_tables(connection, version=11)
            SQLiteStore._migrate_v11_to_v12(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 10:
            SQLiteStore._validate_required_tables(connection, version=10)
            SQLiteStore._migrate_v10_to_v11(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 9:
            SQLiteStore._validate_required_tables(connection, version=9)
            SQLiteStore._migrate_v9_to_v10(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 1:
            SQLiteStore._validate_required_tables(connection, version=1)
            SQLiteStore._migrate_v1_to_v2(connection)
            SQLiteStore._migrate_v2_to_v3(connection)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._migrate_v4_to_v5(connection)
            SQLiteStore._migrate_v5_to_v6(connection)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 2:
            SQLiteStore._validate_required_tables(connection, version=2)
            SQLiteStore._migrate_v2_to_v3(connection)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._migrate_v4_to_v5(connection)
            SQLiteStore._migrate_v5_to_v6(connection)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 3:
            SQLiteStore._validate_required_tables(connection, version=3)
            SQLiteStore._migrate_v3_to_v4(connection)
            SQLiteStore._migrate_v4_to_v5(connection)
            SQLiteStore._migrate_v5_to_v6(connection)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 4:
            SQLiteStore._validate_required_tables(connection, version=4)
            SQLiteStore._migrate_v4_to_v5(connection)
            SQLiteStore._migrate_v5_to_v6(connection)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 5:
            SQLiteStore._validate_required_tables(connection, version=5)
            SQLiteStore._migrate_v5_to_v6(connection)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 6:
            SQLiteStore._validate_required_tables(connection, version=6)
            SQLiteStore._migrate_v6_to_v7(connection)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 7:
            SQLiteStore._validate_required_tables(connection, version=7)
            SQLiteStore._migrate_v7_to_v8(connection)
            SQLiteStore._migrate_v8_to_v9(connection)
            SQLiteStore._validate_required_tables(connection, version=SCHEMA_VERSION)
            return
        if version == 8:
            SQLiteStore._validate_required_tables(connection, version=8)
            SQLiteStore._migrate_v8_to_v9(connection)
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
    def _migrate_v4_to_v5(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V5_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 5")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v5_to_v6(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V6_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 6")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v6_to_v7(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V7_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 7")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v7_to_v8(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V8_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 8")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v8_to_v9(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V9_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 9")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        SQLiteStore._migrate_v9_to_v10(connection)

    @staticmethod
    def _migrate_v9_to_v10(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V10_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 10")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        SQLiteStore._migrate_v10_to_v11(connection)

    @staticmethod
    def _migrate_v10_to_v11(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V11_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 11")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        SQLiteStore._migrate_v11_to_v12(connection)

    @staticmethod
    def _migrate_v11_to_v12(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V12_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 12")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        SQLiteStore._migrate_v12_to_v13(connection)

    @staticmethod
    def _migrate_v12_to_v13(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V13_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 13")
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
        if version >= 5:
            required.update({"paper_limit_orders", "paper_limit_actions"})
        if version >= 8:
            required.add("paper_state_revisions")
        if version >= 10:
            required.add("paper_protection_actions")
        if version >= 11:
            required.add("live_market_actions")
        if version >= 12:
            required.update({"live_limit_acceptance_sessions", "live_limit_actions"})
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

    @property
    def normalized_path(self) -> str:
        """Stable absolute database path used in mutation provenance."""
        self._assert_owner()
        return str(self.path.resolve())

    @property
    def database_identity(self) -> str:
        """Non-secret digest identifying the normalized persistence path."""
        return hashlib.sha256(self.normalized_path.encode("utf-8")).hexdigest()

    def create_live_limit_acceptance_session(
        self, record: LiveLimitAcceptanceSessionRecord,
    ) -> LiveLimitAcceptanceSessionRecord:
        """Explicitly persist an operator-authorized session; never auto-arm one."""
        self._assert_owner()
        if record.state is not LiveLimitAcceptanceState.ARMED:
            raise ValueError("a new LIVE Limit acceptance session must be ARMED explicitly")
        if record.environment != "MAINNET" or record.capability != "LIVE_LIMIT_CREATE":
            raise ValueError("LIVE Limit acceptance requires MAINNET LIVE_LIMIT_CREATE scope")
        if record.max_create_count < 1:
            raise ValueError("max_create_count must be positive")
        _decimal_text(record.aggregate_notional_ceiling)
        _decimal_text(record.per_order_ceiling)
        _decimal_text(record.reserved_notional)
        if record.aggregate_notional_ceiling <= 0 or record.per_order_ceiling <= 0:
            raise ValueError("acceptance ceilings must be positive")
        if record.per_order_ceiling > record.aggregate_notional_ceiling:
            raise ValueError("per-order ceiling cannot exceed aggregate ceiling")
        if record.reserved_count != 0 or record.reserved_notional != 0:
            raise ValueError("a new acceptance session cannot begin with reservations")
        if record.opened_at_ms < 0 or record.expires_at_ms <= record.opened_at_ms:
            raise ValueError("acceptance session timestamps are invalid")
        if record.updated_at_ms < record.opened_at_ms:
            raise ValueError("acceptance session update timestamp is invalid")
        if record.authorized_session_generation < 1:
            raise ValueError("authorized session generation must be positive")
        if record.database_identity != self.database_identity:
            raise PersistenceError("acceptance session database identity mismatch")
        required = (
            record.acceptance_session_id, record.authorized_build_sha,
            record.operator_authorization_reference,
        )
        if any(not value.strip() for value in required):
            raise ValueError("acceptance session authorization fields must be non-empty")
        try:
            with self._transaction():
                self._connection.execute(
                    """INSERT INTO live_limit_acceptance_sessions (
                        acceptance_session_id, trading_account_id, environment, symbol,
                        capability, state, max_create_count, aggregate_notional_ceiling,
                        per_order_ceiling, reserved_count, reserved_notional, opened_at_ms,
                        expires_at_ms, authorized_build_sha, database_identity,
                        operator_authorization_reference, authorized_session_generation,
                        updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, '0', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.acceptance_session_id, record.trading_account_id.value,
                        record.environment, record.symbol.value, record.capability,
                        record.state.value, record.max_create_count,
                        _decimal_text(record.aggregate_notional_ceiling),
                        _decimal_text(record.per_order_ceiling), record.opened_at_ms,
                        record.expires_at_ms, record.authorized_build_sha,
                        record.database_identity, record.operator_authorization_reference,
                        record.authorized_session_generation, record.updated_at_ms,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateIdentity("LIVE Limit acceptance session already exists") from exc
        loaded = self.get_live_limit_acceptance_session(
            record.acceptance_session_id, record.trading_account_id,
            record.environment, record.symbol, record.capability,
        )
        if loaded is None:
            raise PersistenceError("committed LIVE Limit acceptance session disappeared")
        return loaded

    def get_live_limit_acceptance_session(
        self, acceptance_session_id: str, account_id: TradingAccountId,
        environment: str, symbol: Symbol, capability: str,
    ) -> LiveLimitAcceptanceSessionRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """SELECT * FROM live_limit_acceptance_sessions
               WHERE acceptance_session_id=? AND trading_account_id=? AND environment=?
                 AND symbol=? AND capability=?""",
            (acceptance_session_id, account_id.value, environment, symbol.value, capability),
        ).fetchone()
        return _live_limit_session_from_row(row) if row is not None else None

    def select_live_limit_acceptance_session(
        self, *, account_id: TradingAccountId, environment: str, symbol: Symbol,
        capability: str, session_generation: int, client_action_id: str,
        occurred_at_ms: int,
    ) -> LiveLimitAcceptanceSessionRecord:
        """Resolve replay ownership first, otherwise require one eligible ARMED session."""
        self._assert_owner()
        action_rows = self._connection.execute(
            """SELECT acceptance_session_id FROM live_limit_actions
               WHERE trading_account_id=? AND session_generation=? AND client_action_id=?
               ORDER BY created_at_ms DESC""",
            (account_id.value, session_generation, client_action_id),
        ).fetchall()
        if len(action_rows) > 1:
            raise PersistenceError("LIVE Limit client action identity is ambiguous across sessions")
        if action_rows:
            session_id = action_rows[0]["acceptance_session_id"]
            session = self.get_live_limit_acceptance_session(
                session_id, account_id, environment, symbol, capability,
            )
            if session is None:
                raise PersistenceError("LIVE Limit replay session scope is unavailable")
            return session
        rows = self._connection.execute(
            """SELECT * FROM live_limit_acceptance_sessions
               WHERE trading_account_id=? AND environment=? AND symbol=? AND capability=?
                 AND authorized_session_generation=? AND state='ARMED'
                 AND opened_at_ms<=? AND expires_at_ms>?
               ORDER BY opened_at_ms DESC""",
            (account_id.value, environment, symbol.value, capability,
             session_generation, occurred_at_ms, occurred_at_ms),
        ).fetchall()
        if len(rows) != 1:
            raise PersistenceError("exactly one eligible LIVE Limit acceptance session is required")
        return _live_limit_session_from_row(rows[0])

    def admit_live_limit_create(
        self, *, acceptance_session_id: str, environment: str, capability: str,
        session_generation: int, client_action_id: str, request_fingerprint: str,
        record: CommandRecord, reserved_notional: Decimal,
        runtime: LiveLimitRuntimeAttribution, occurred_at_ms: int,
    ) -> LiveLimitAdmissionResult:
        """Atomically own identity, budget and single-flight before dispatch is possible."""
        self._assert_owner()
        self._validate_live_limit_admission_inputs(
            environment=environment, capability=capability,
            session_generation=session_generation, client_action_id=client_action_id,
            request_fingerprint=request_fingerprint, record=record,
            reserved_notional=reserved_notional, runtime=runtime,
            occurred_at_ms=occurred_at_ms,
        )
        try:
            with self._transaction():
                existing_row = self._connection.execute(
                    """SELECT * FROM live_limit_actions WHERE acceptance_session_id=?
                       AND trading_account_id=? AND session_generation=?
                       AND client_action_id=?""",
                    (acceptance_session_id, record.trading_account_id.value,
                     session_generation, client_action_id),
                ).fetchone()
                if existing_row is not None:
                    existing = _live_limit_action_from_row(existing_row)
                    if existing.request_fingerprint != request_fingerprint:
                        raise DuplicateIdentity(
                            "client_action_id was reused with different LIVE Limit intent"
                        )
                    return LiveLimitAdmissionResult(existing, False)

                session_row = self._connection.execute(
                    """SELECT * FROM live_limit_acceptance_sessions
                       WHERE acceptance_session_id=? AND trading_account_id=?
                         AND environment=? AND symbol=? AND capability=?""",
                    (acceptance_session_id, record.trading_account_id.value,
                     environment, record.symbol.value, capability),
                ).fetchone()
                if session_row is None:
                    raise PersistenceError("LIVE Limit acceptance scope is unavailable or mismatched")
                session = _live_limit_session_from_row(session_row)
                if session.state is not LiveLimitAcceptanceState.ARMED:
                    raise PersistenceError("LIVE Limit acceptance session is not ARMED")
                if occurred_at_ms < session.opened_at_ms or occurred_at_ms >= session.expires_at_ms:
                    raise PersistenceError("LIVE Limit acceptance session is outside its time window")
                if runtime.build_sha != session.authorized_build_sha:
                    raise PersistenceError("LIVE Limit acceptance build mismatch")
                if runtime.database_identity != session.database_identity:
                    raise PersistenceError("LIVE Limit acceptance database mismatch")
                if session_generation != session.authorized_session_generation:
                    raise PersistenceError("LIVE Limit acceptance account session mismatch")
                unresolved = self._connection.execute(
                    """SELECT 1 FROM live_limit_actions
                       WHERE acceptance_session_id=? AND trading_account_id=?
                         AND environment=? AND symbol=? AND capability=?
                         AND (dispatch_state IN ('OWNED','DISPATCHING','UNKNOWN')
                              OR reconciliation_state='REQUIRED') LIMIT 1""",
                    (acceptance_session_id, record.trading_account_id.value,
                     environment, record.symbol.value, capability),
                ).fetchone()
                if unresolved is not None:
                    raise PersistenceError("LIVE Limit acceptance session has an unresolved owner")
                if reserved_notional > session.per_order_ceiling:
                    raise PersistenceError("LIVE Limit per-order ceiling exceeded")
                new_count = session.reserved_count + 1
                new_notional = session.reserved_notional + reserved_notional
                if new_count > session.max_create_count:
                    raise PersistenceError("LIVE Limit acceptance create count exhausted")
                if new_notional > session.aggregate_notional_ceiling:
                    raise PersistenceError("LIVE Limit aggregate notional ceiling exceeded")

                self._insert_command(record, "durable LIVE Limit acceptance ownership")
                self._connection.execute(
                    """INSERT INTO live_limit_actions (
                        acceptance_session_id, trading_account_id, environment, capability,
                        session_generation, symbol, operation, client_action_id,
                        request_fingerprint, command_id, order_link_id, exchange_order_id,
                        dispatch_state, reconciliation_state, reserved_count,
                        reserved_notional, build_sha, process_instance_id,
                        process_started_at_ms, process_id, database_path, database_identity,
                        schema_version, host_identity, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, 'CREATE', ?, ?, ?, ?, NULL,
                              'OWNED', 'NOT_REQUIRED', 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        acceptance_session_id, record.trading_account_id.value,
                        environment, capability, session_generation, record.symbol.value,
                        client_action_id, request_fingerprint, record.command_id.value,
                        record.order_link_id, _decimal_text(reserved_notional),
                        runtime.build_sha, runtime.process_instance_id,
                        runtime.process_started_at_ms, runtime.process_id,
                        runtime.database_path, runtime.database_identity,
                        runtime.schema_version, runtime.host_identity,
                        record.created_at_ms, record.updated_at_ms,
                    ),
                )
                next_state = (
                    LiveLimitAcceptanceState.EXHAUSTED.value
                    if new_count >= session.max_create_count else session.state.value
                )
                cursor = self._connection.execute(
                    """UPDATE live_limit_acceptance_sessions
                       SET reserved_count=?, reserved_notional=?, state=?, updated_at_ms=?
                       WHERE acceptance_session_id=? AND trading_account_id=?
                         AND environment=? AND symbol=? AND capability=?
                         AND state='ARMED' AND reserved_count=? AND reserved_notional=?""",
                    (new_count, _decimal_text(new_notional), next_state, occurred_at_ms,
                     acceptance_session_id, record.trading_account_id.value,
                     environment, record.symbol.value, capability,
                     session.reserved_count, _decimal_text(session.reserved_notional)),
                )
                if cursor.rowcount != 1:
                    raise ConcurrentUpdate("LIVE Limit acceptance reservation changed concurrently")
        except sqlite3.IntegrityError as exc:
            raise DuplicateIdentity("LIVE Limit durable identity conflict") from exc
        action = self.get_live_limit_action(
            acceptance_session_id, record.trading_account_id,
            session_generation, client_action_id,
        )
        if action is None:
            raise PersistenceError("committed LIVE Limit action disappeared")
        return LiveLimitAdmissionResult(action, True)

    def _validate_live_limit_admission_inputs(
        self, *, environment: str, capability: str, session_generation: int,
        client_action_id: str, request_fingerprint: str, record: CommandRecord,
        reserved_notional: Decimal, runtime: LiveLimitRuntimeAttribution,
        occurred_at_ms: int,
    ) -> None:
        if environment != "MAINNET" or capability != "LIVE_LIMIT_CREATE":
            raise PersistenceError("LIVE Limit admission scope mismatch")
        if session_generation < 1 or record.current_state is not CommandState.ADMITTED:
            raise PersistenceError("LIVE Limit command/session state is not admissible")
        try:
            _decimal_text(reserved_notional)
        except (TypeError, ValueError):
            raise PersistenceError("LIVE Limit reserved notional is invalid") from None
        if record.command_kind != "create_limit" or reserved_notional <= 0:
            raise PersistenceError("LIVE Limit create request is invalid")
        if record.requested_notional.value != reserved_notional:
            raise PersistenceError("LIVE Limit reserved notional does not match command")
        if occurred_at_ms != record.updated_at_ms:
            raise PersistenceError("LIVE Limit admission timestamp mismatch")
        if any(not value.strip() for value in (
            client_action_id, request_fingerprint, runtime.build_sha,
            runtime.process_instance_id, runtime.host_identity,
        )):
            raise PersistenceError("LIVE Limit identity/provenance is incomplete")
        if runtime.process_started_at_ms < 0 or runtime.process_id <= 0:
            raise PersistenceError("LIVE Limit process provenance is invalid")
        if runtime.process_started_at_ms > occurred_at_ms:
            raise PersistenceError("LIVE Limit process start is after admission")
        if runtime.schema_version != SCHEMA_VERSION:
            raise PersistenceError("LIVE Limit schema version mismatch")
        if runtime.database_path != self.normalized_path:
            raise PersistenceError("LIVE Limit database path mismatch")
        if runtime.database_identity != self.database_identity:
            raise PersistenceError("LIVE Limit database identity mismatch")

    def _insert_command(self, record: CommandRecord, reason: str) -> None:
        self._connection.execute(
            """INSERT INTO trading_commands (
                command_id, order_link_id, trading_account_id, category, symbol,
                position_idx, command_kind, side, requested_notional,
                normalized_price, normalized_quantity, origin, controller,
                current_state, version, exchange_order_id, created_at_ms, updated_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.command_id.value, record.order_link_id,
             record.trading_account_id.value, record.category.value,
             record.symbol.value, record.position_idx, record.command_kind,
             record.side.value, _decimal_text(record.requested_notional.value),
             _optional_decimal(record.normalized_price),
             _optional_decimal(record.normalized_quantity), record.origin.value,
             record.controller.value, record.current_state.value, record.version,
             None, record.created_at_ms, record.updated_at_ms),
        )
        self._connection.execute(
            """INSERT INTO command_state_history
               (command_id, previous_state, next_state, reason, occurred_at_ms)
               VALUES (?, NULL, ?, ?, ?)""",
            (record.command_id.value, record.current_state.value, reason, record.updated_at_ms),
        )

    def get_live_limit_action(
        self, acceptance_session_id: str, account_id: TradingAccountId,
        session_generation: int, client_action_id: str,
    ) -> LiveLimitActionRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            """SELECT * FROM live_limit_actions WHERE acceptance_session_id=?
               AND trading_account_id=? AND session_generation=? AND client_action_id=?""",
            (acceptance_session_id, account_id.value, session_generation, client_action_id),
        ).fetchone()
        return _live_limit_action_from_row(row) if row is not None else None

    def load_unresolved_live_limit_actions(
        self, account_id: TradingAccountId | None = None,
    ) -> tuple[LiveLimitActionRecord, ...]:
        """Load actions that must remain locked or require authoritative REST evidence."""
        self._assert_owner()
        clause = ""
        parameters: list[object] = []
        if account_id is not None:
            clause = " AND trading_account_id=?"
            parameters.append(account_id.value)
        rows = self._connection.execute(
            f"""SELECT * FROM live_limit_actions
                WHERE (dispatch_state IN ('OWNED','DISPATCHING','UNKNOWN')
                       OR reconciliation_state='REQUIRED'){clause}
                ORDER BY created_at_ms, acceptance_session_id, client_action_id""",
            parameters,
        ).fetchall()
        return tuple(_live_limit_action_from_row(row) for row in rows)

    def record_live_limit_outcome(
        self, action: LiveLimitActionRecord, *, disposition: str,
        exchange_order_id: OrderId | None, reason: str, occurred_at_ms: int,
        outcome_code: int | None = None,
    ) -> LiveLimitActionRecord:
        """Atomically persist the sole adapter attempt outcome and command state."""
        self._assert_owner()
        if disposition not in {"acknowledged", "rejected", "unknown"}:
            raise ValueError("unsupported LIVE Limit outcome disposition")
        if not reason.strip():
            raise ValueError("LIVE Limit outcome reason must be non-empty")
        dispatch_state = {
            "acknowledged": "ACKNOWLEDGED",
            "rejected": "ACKNOWLEDGED",
            "unknown": "UNKNOWN",
        }[disposition]
        reconciliation_state = "RESOLVED" if disposition == "rejected" else "REQUIRED"
        command_state = {
            "acknowledged": CommandState.ACKNOWLEDGED,
            "rejected": CommandState.REJECTED,
            "unknown": CommandState.UNKNOWN,
        }[disposition]
        with self._transaction():
            persisted_row = self._connection.execute(
                """SELECT * FROM live_limit_actions WHERE acceptance_session_id=?
                   AND trading_account_id=? AND session_generation=? AND client_action_id=?""",
                (action.acceptance_session_id, action.trading_account_id.value,
                 action.session_generation, action.client_action_id),
            ).fetchone()
            if persisted_row is None or _live_limit_action_from_row(persisted_row) != action:
                raise PersistenceError("LIVE Limit outcome identity no longer matches")
            command = self.get_command(action.command_id)
            if command is None or command.current_state is not CommandState.SUBMITTING:
                raise PersistenceError("LIVE Limit outcome command is not SUBMITTING")
            cursor = self._connection.execute(
                """UPDATE live_limit_actions SET dispatch_state=?, reconciliation_state=?,
                   exchange_order_id=?, outcome_disposition=?, outcome_reason=?,
                   outcome_at_ms=?, outcome_code=?, updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=?
                     AND dispatch_state='DISPATCHING'""",
                (dispatch_state, reconciliation_state,
                 exchange_order_id.value if exchange_order_id else None,
                 disposition, reason, occurred_at_ms, outcome_code, occurred_at_ms,
                 action.acceptance_session_id, action.trading_account_id.value,
                 action.session_generation, action.client_action_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit action has no pending dispatch outcome")
            command_cursor = self._connection.execute(
                """UPDATE trading_commands SET current_state=?, version=version+1,
                   exchange_order_id=?, updated_at_ms=?
                   WHERE command_id=? AND current_state=? AND version=?""",
                (command_state.value,
                 exchange_order_id.value if exchange_order_id else None,
                 occurred_at_ms, command.command_id.value,
                 CommandState.SUBMITTING.value, command.version),
            )
            if command_cursor.rowcount != 1:
                raise ConcurrentUpdate("LIVE Limit command changed during outcome persistence")
            self._connection.execute(
                """INSERT INTO command_state_history
                   (command_id, previous_state, next_state, reason, occurred_at_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (command.command_id.value, CommandState.SUBMITTING.value,
                 command_state.value, reason, occurred_at_ms),
            )
        current = self.get_live_limit_action(
            action.acceptance_session_id, action.trading_account_id,
            action.session_generation, action.client_action_id,
        )
        if current is None:
            raise PersistenceError("persisted LIVE Limit outcome disappeared")
        return current

    def complete_live_limit_reconciliation(
        self, action: LiveLimitActionRecord, *, exchange_order_id: OrderId,
        occurred_at_ms: int,
    ) -> LiveLimitActionRecord:
        """Mark exchange-correlated evidence resolved without changing reservation."""
        self._assert_owner()
        with self._transaction():
            cursor = self._connection.execute(
                """UPDATE live_limit_actions SET dispatch_state='ACKNOWLEDGED',
                   reconciliation_state='RESOLVED', exchange_order_id=?, updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=?
                     AND dispatch_state IN ('DISPATCHING','ACKNOWLEDGED','UNKNOWN')""",
                (exchange_order_id.value, occurred_at_ms, action.acceptance_session_id,
                 action.trading_account_id.value, action.session_generation,
                 action.client_action_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit reconciliation identity/state mismatch")
        current = self.get_live_limit_action(
            action.acceptance_session_id, action.trading_account_id,
            action.session_generation, action.client_action_id,
        )
        if current is None:
            raise PersistenceError("reconciled LIVE Limit action disappeared")
        return current

    def begin_live_limit_dispatch(
        self, action: LiveLimitActionRecord, *, runtime: LiveLimitRuntimeAttribution,
        occurred_at_ms: int,
    ) -> CommandRecord:
        """Persist the irreversible boundary; caller may dispatch only after this returns."""
        self._assert_owner()
        with self._transaction():
            persisted_row = self._connection.execute(
                """SELECT * FROM live_limit_actions WHERE acceptance_session_id=?
                   AND trading_account_id=? AND session_generation=? AND client_action_id=?""",
                (action.acceptance_session_id, action.trading_account_id.value,
                 action.session_generation, action.client_action_id),
            ).fetchone()
            if persisted_row is None:
                raise PersistenceError("LIVE Limit action ownership is unavailable")
            persisted = _live_limit_action_from_row(persisted_row)
            if persisted != action or runtime != persisted.runtime:
                raise PersistenceError("LIVE Limit dispatch identity/runtime attribution mismatch")
            cursor = self._connection.execute(
                """UPDATE live_limit_actions
                   SET dispatch_state='DISPATCHING', reconciliation_state='REQUIRED', updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=? AND dispatch_state='OWNED'""",
                (occurred_at_ms, action.acceptance_session_id,
                 action.trading_account_id.value, action.session_generation,
                 action.client_action_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit action is not dispatchable")
            command = self.get_command(action.command_id)
            if command is None or command.current_state is not CommandState.ADMITTED:
                raise PersistenceError("LIVE Limit command is not dispatchable")
            command_cursor = self._connection.execute(
                """UPDATE trading_commands SET current_state=?, version=version+1, updated_at_ms=?
                   WHERE command_id=? AND current_state=? AND version=?""",
                (CommandState.SUBMITTING.value, occurred_at_ms, action.command_id.value,
                 CommandState.ADMITTED.value, command.version),
            )
            if command_cursor.rowcount != 1:
                raise ConcurrentUpdate("LIVE Limit command changed before dispatch")
            self._connection.execute(
                """INSERT INTO command_state_history
                   (command_id, previous_state, next_state, reason, occurred_at_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (action.command_id.value, CommandState.ADMITTED.value,
                 CommandState.SUBMITTING.value,
                 "LIVE Limit adapter dispatch durably started", occurred_at_ms),
            )
        command = self.get_command(action.command_id)
        if command is None:
            raise PersistenceError("LIVE Limit dispatch command disappeared")
        return command

    def mark_live_limit_unknown(
        self, action: LiveLimitActionRecord, *, occurred_at_ms: int,
    ) -> None:
        self._assert_owner()
        with self._transaction():
            command = self.get_command(action.command_id)
            allowed_command_states = {CommandState.SUBMITTING, CommandState.ACKNOWLEDGED}
            if command is None or command.current_state not in allowed_command_states:
                raise PersistenceError("LIVE Limit command cannot enter UNKNOWN")
            cursor = self._connection.execute(
                """UPDATE live_limit_actions SET dispatch_state='UNKNOWN',
                   reconciliation_state='REQUIRED', updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=?
                     AND dispatch_state IN ('DISPATCHING','ACKNOWLEDGED')""",
                (occurred_at_ms, action.acceptance_session_id,
                 action.trading_account_id.value, action.session_generation,
                 action.client_action_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit action cannot enter UNKNOWN")
            command_cursor = self._connection.execute(
                """UPDATE trading_commands SET current_state=?, version=version+1,
                   updated_at_ms=? WHERE command_id=? AND current_state=? AND version=?""",
                (CommandState.UNKNOWN.value, occurred_at_ms, command.command_id.value,
                 command.current_state.value, command.version),
            )
            if command_cursor.rowcount != 1:
                raise ConcurrentUpdate("LIVE Limit command changed before UNKNOWN")
            self._connection.execute(
                """INSERT INTO command_state_history
                   (command_id, previous_state, next_state, reason, occurred_at_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (command.command_id.value, command.current_state.value,
                 CommandState.UNKNOWN.value,
                 "LIVE Limit outcome remains unknown after reconciliation",
                 occurred_at_ms),
            )

    def mark_live_limit_reconciled(
        self, action: LiveLimitActionRecord, *, exchange_order_id: OrderId,
        occurred_at_ms: int,
    ) -> None:
        """Record authoritative reconciliation without releasing acceptance budget."""
        self._assert_owner()
        with self._transaction():
            command = self.get_command(action.command_id)
            if command is None or command.current_state is not CommandState.SUBMITTING:
                raise PersistenceError("LIVE Limit command cannot be acknowledged")
            cursor = self._connection.execute(
                """UPDATE live_limit_actions SET dispatch_state='ACKNOWLEDGED',
                   reconciliation_state='RESOLVED', exchange_order_id=?, updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=?
                     AND dispatch_state IN ('DISPATCHING','UNKNOWN')""",
                (exchange_order_id.value, occurred_at_ms, action.acceptance_session_id,
                 action.trading_account_id.value, action.session_generation,
                 action.client_action_id),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit action cannot be reconciled")
            command_cursor = self._connection.execute(
                """UPDATE trading_commands SET current_state=?, version=version+1,
                   exchange_order_id=?, updated_at_ms=?
                   WHERE command_id=? AND current_state=? AND version=?""",
                (CommandState.ACKNOWLEDGED.value, exchange_order_id.value,
                 occurred_at_ms, action.command_id.value,
                 CommandState.SUBMITTING.value, command.version),
            )
            if command_cursor.rowcount != 1:
                raise ConcurrentUpdate("LIVE Limit command changed during reconciliation")
            self._connection.execute(
                """INSERT INTO command_state_history
                   (command_id, previous_state, next_state, reason, occurred_at_ms)
                   VALUES (?, ?, ?, ?, ?)""",
                (action.command_id.value, CommandState.SUBMITTING.value,
                 CommandState.ACKNOWLEDGED.value,
                 "LIVE Limit order found by authoritative reconciliation",
                 occurred_at_ms),
            )

    def release_live_limit_pre_dispatch_failure(
        self, action: LiveLimitActionRecord, *, occurred_at_ms: int,
    ) -> None:
        """Release only when durable OWNED proves adapter dispatch never began."""
        self._assert_owner()
        with self._transaction():
            current = self._connection.execute(
                """SELECT dispatch_state, reserved_count, reserved_notional
                   FROM live_limit_actions WHERE acceptance_session_id=?
                     AND trading_account_id=? AND session_generation=?
                     AND client_action_id=?""",
                (action.acceptance_session_id, action.trading_account_id.value,
                 action.session_generation, action.client_action_id),
            ).fetchone()
            if current is None or current["dispatch_state"] != "OWNED":
                raise PersistenceError("reservation cannot be released after dispatch began")
            self._connection.execute(
                """UPDATE live_limit_actions SET dispatch_state='PRE_DISPATCH_FAILED',
                   reconciliation_state='RESOLVED', updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND session_generation=? AND client_action_id=?""",
                (occurred_at_ms, action.acceptance_session_id,
                 action.trading_account_id.value, action.session_generation,
                 action.client_action_id),
            )
            session_row = self._connection.execute(
                """SELECT reserved_count, reserved_notional
                   FROM live_limit_acceptance_sessions
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND environment=? AND symbol=? AND capability=?""",
                (action.acceptance_session_id, action.trading_account_id.value,
                 action.environment, action.symbol.value, action.capability),
            ).fetchone()
            if session_row is None:
                raise PersistenceError("LIVE Limit acceptance session disappeared")
            next_count = int(session_row["reserved_count"]) - int(current["reserved_count"])
            next_notional = (
                _load_decimal(session_row["reserved_notional"])
                - _load_decimal(current["reserved_notional"])
            )
            cursor = self._connection.execute(
                """UPDATE live_limit_acceptance_sessions SET state='ARMED',
                   reserved_count=?, reserved_notional=?, updated_at_ms=?
                   WHERE acceptance_session_id=? AND trading_account_id=?
                     AND environment=? AND symbol=? AND capability=?
                     AND reserved_count>=?""",
                (next_count, _decimal_text(next_notional), occurred_at_ms,
                 action.acceptance_session_id,
                 action.trading_account_id.value, action.environment,
                 action.symbol.value, action.capability, int(current["reserved_count"])),
            )
            if cursor.rowcount != 1:
                raise PersistenceError("LIVE Limit reservation release failed")

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

    def get_paper_state_revision(
        self, trading_account_id: TradingAccountId, symbol: Symbol,
    ) -> int:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT revision FROM paper_state_revisions WHERE trading_account_id = ? AND symbol = ?",
            (trading_account_id.value, symbol.value),
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _advance_paper_state_revision(
        self, trading_account_id: TradingAccountId, symbol: Symbol,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO paper_state_revisions (trading_account_id, symbol, revision)
            VALUES (?, ?, 1)
            ON CONFLICT(trading_account_id, symbol)
            DO UPDATE SET revision = revision + 1
            """,
            (trading_account_id.value, symbol.value),
        )

    def mutate_paper_stop(
        self,
        *,
        client_action_id: str,
        request_fingerprint: str,
        operation: str,
        position_key: PositionKey,
        stop_loss: Decimal | None,
        updated_at_ms: int,
    ) -> tuple[ProtectionProjectionRecord | None, bool, bool]:
        return self.mutate_paper_protection_leg(
            client_action_id=client_action_id,
            request_fingerprint=request_fingerprint,
            operation=operation,
            position_key=position_key,
            leg="stop",
            trigger=stop_loss,
            updated_at_ms=updated_at_ms,
        )

    def mutate_paper_protection_leg(
        self,
        *,
        client_action_id: str,
        request_fingerprint: str,
        operation: str,
        position_key: PositionKey,
        leg: str,
        trigger: Decimal | None,
        updated_at_ms: int,
    ) -> tuple[ProtectionProjectionRecord | None, bool, bool]:
        """Apply one idempotent PAPER protection-leg mutation and revision atomically."""

        self._assert_owner()
        if leg not in {"stop", "take"}:
            raise ValueError("unsupported PAPER protection leg")
        column = "stop_loss" if leg == "stop" else "take_profit"
        action_operation = operation
        if operation not in {"create", "amend", "delete"}:
            raise ValueError("unsupported PAPER protection operation")
        if operation == "delete" and trigger is not None:
            raise ValueError("PAPER protection delete cannot carry a trigger")
        if operation != "delete" and trigger is None:
            raise ValueError("PAPER protection mutation requires a trigger")

        existing_action = self._connection.execute(
            """SELECT operation, request_fingerprint, trading_account_id, symbol
               FROM paper_protection_actions WHERE client_action_id = ?""",
            (client_action_id,),
        ).fetchone()
        if existing_action is not None:
            identity = (
                existing_action["operation"], existing_action["request_fingerprint"],
                existing_action["trading_account_id"], existing_action["symbol"],
            )
            expected = (
                action_operation, request_fingerprint,
                position_key.trading_account_id.value, position_key.symbol.value,
            )
            if identity != expected:
                raise DuplicateIdentity(
                    "client action identity already exists with different PAPER protection intent"
                )
            return self.get_protection_projection(position_key), False, True

        current = self.get_protection_projection(position_key)
        current_trigger = None if current is None else getattr(current, column)
        if operation == "create" and current_trigger is not None:
            raise PersistenceError(f"PAPER {leg.upper()} already exists")
        if operation == "amend" and current_trigger is None:
            raise PersistenceError(f"PAPER {leg.upper()} is missing")

        changed = (
            current_trigger is None
            if operation == "create"
            else current_trigger != trigger
            if operation == "amend"
            else current_trigger is not None
        )
        with self._transaction():
            if operation == "delete":
                sibling = None if current is None else (
                    current.take_profit if leg == "stop" else current.stop_loss
                )
                if changed and sibling is not None:
                    self._connection.execute(
                        f"""UPDATE protection_projections
                           SET {column}=NULL, status='confirmed_active', pending_command_id=NULL,
                               version=version+1, evidence_at_ms=?, updated_at_ms=?
                           WHERE trading_account_id=? AND category=? AND symbol=? AND position_idx=?""",
                        (
                            updated_at_ms, updated_at_ms,
                            position_key.trading_account_id.value, position_key.category.value,
                            position_key.symbol.value, position_key.position_idx,
                        ),
                    )
                elif changed and current is not None:
                    self._connection.execute(
                        """DELETE FROM protection_projections
                           WHERE trading_account_id=? AND category=? AND symbol=? AND position_idx=?""",
                        (
                            position_key.trading_account_id.value, position_key.category.value,
                            position_key.symbol.value, position_key.position_idx,
                        ),
                    )
            elif current is None:
                self._connection.execute(
                    """INSERT INTO protection_projections
                       (trading_account_id, category, symbol, position_idx, status,
                        take_profit, stop_loss, trailing_stop, pending_command_id,
                        version, evidence_at_ms, updated_at_ms)
                       VALUES (?, ?, ?, ?, 'confirmed_active', ?, ?, NULL, NULL, 1, ?, ?)""",
                    (
                        position_key.trading_account_id.value, position_key.category.value,
                        position_key.symbol.value, position_key.position_idx,
                        _decimal_text(trigger) if leg == "take" else None,
                        _decimal_text(trigger) if leg == "stop" else None,
                        updated_at_ms, updated_at_ms,
                    ),
                )
            elif changed:
                self._connection.execute(
                    f"""UPDATE protection_projections
                       SET {column}=?, status='confirmed_active', pending_command_id=NULL,
                           version=version+1, evidence_at_ms=?, updated_at_ms=?
                       WHERE trading_account_id=? AND category=? AND symbol=? AND position_idx=?""",
                    (
                        _decimal_text(trigger), updated_at_ms, updated_at_ms,
                        position_key.trading_account_id.value, position_key.category.value,
                        position_key.symbol.value, position_key.position_idx,
                    ),
                )
            self._connection.execute(
                "INSERT INTO paper_protection_actions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    client_action_id, action_operation, request_fingerprint,
                    position_key.trading_account_id.value, position_key.symbol.value,
                    updated_at_ms,
                ),
            )
            if changed:
                self._advance_paper_state_revision(
                    position_key.trading_account_id, position_key.symbol,
                )
        return self.get_protection_projection(position_key), changed, False

    def clear_paper_protection_for_flat(
        self, position_key: PositionKey,
    ) -> bool:
        """Remove stale PAPER protection only when durable position is already FLAT."""

        self._assert_owner()
        position = self.get_position_projection(position_key)
        if position is not None and (
            position.side is not PositionSide.FLAT or position.quantity.value != 0
        ):
            raise PersistenceError("cannot clear PAPER protection for an open position")
        if self.get_protection_projection(position_key) is None:
            return False
        with self._transaction():
            self._delete_protection_projection(position_key)
            self._advance_paper_state_revision(
                position_key.trading_account_id, position_key.symbol,
            )
        return True

    def create_paper_limit(
        self, *, client_action_id: str, request_fingerprint: str,
        order_id: OrderId, order_link_id: str, trading_account_id: TradingAccountId,
        symbol: Symbol, side: OrderSide, price: Decimal, quantity: Decimal,
        created_at_ms: int,
    ) -> tuple[PaperLimitOrderRecord, bool]:
        self._assert_owner()
        existing_action = self._connection.execute(
            "SELECT operation, request_fingerprint, order_id FROM paper_limit_actions WHERE client_action_id = ?",
            (client_action_id,),
        ).fetchone()
        if existing_action is not None:
            if existing_action[0] != "create" or existing_action[1] != request_fingerprint:
                raise DuplicateIdentity("client action identity was reused with different intent")
            existing = self.get_paper_limit(
                str(existing_action[2]), trading_account_id,
            )
            if existing is None:
                raise PersistenceError("durable create action references no PAPER limit")
            return existing, False
        record = PaperLimitOrderRecord(
            order_id, order_link_id, trading_account_id, symbol, side, price, quantity,
            Decimal("0"), "GTC", "open", created_at_ms, created_at_ms,
        )
        with self._transaction():
            self._connection.execute(
                """INSERT INTO paper_limit_orders (
                    order_id, order_link_id, trading_account_id, symbol, side, price,
                    quantity, filled_quantity, time_in_force, status, created_at_ms, updated_at_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, '0', 'GTC', 'open', ?, ?)""",
                (order_id.value, order_link_id, trading_account_id.value, symbol.value,
                 side.value, _decimal_text(price), _decimal_text(quantity),
                 created_at_ms, created_at_ms),
            )
            self._connection.execute(
                "INSERT INTO paper_limit_actions VALUES (?, 'create', ?, ?, ?)",
                (client_action_id, request_fingerprint, order_id.value, created_at_ms),
            )
            self._advance_paper_state_revision(trading_account_id, symbol)
        return record, True

    def cancel_paper_limit(
        self, *, client_action_id: str, request_fingerprint: str,
        order_id: OrderId, trading_account_id: TradingAccountId, updated_at_ms: int,
    ) -> tuple[PaperLimitOrderRecord | None, bool]:
        self._assert_owner()
        current = self._get_paper_limit_by_id(order_id.value)
        if current is not None and current.trading_account_id != trading_account_id:
            raise ValueError("PAPER limit account does not match active account")
        action = self._connection.execute(
            "SELECT operation, request_fingerprint, order_id FROM paper_limit_actions WHERE client_action_id = ?",
            (client_action_id,),
        ).fetchone()
        if action is not None:
            if action[0] != "cancel" or action[1] != request_fingerprint:
                raise DuplicateIdentity("client action identity was reused with different intent")
            return self.get_paper_limit(order_id.value, trading_account_id), False
        with self._transaction():
            self._connection.execute(
                "INSERT INTO paper_limit_actions VALUES (?, 'cancel', ?, NULL, ?)",
                (client_action_id, request_fingerprint, updated_at_ms),
            )
            cursor = self._connection.execute(
                "UPDATE paper_limit_orders SET status = 'cancelled', updated_at_ms = ? WHERE order_id = ? AND trading_account_id = ? AND status IN ('open', 'partially_filled')",
                (updated_at_ms, order_id.value, trading_account_id.value),
            )
            if cursor.rowcount == 1:
                row = self._connection.execute(
                    "SELECT trading_account_id, symbol FROM paper_limit_orders WHERE order_id = ? AND trading_account_id = ?",
                    (order_id.value, trading_account_id.value),
                ).fetchone()
                if row is None:
                    raise PersistenceError("cancelled PAPER limit is unavailable")
                self._advance_paper_state_revision(
                    TradingAccountId(str(row[0])), Symbol(str(row[1])),
                )
        return self.get_paper_limit(order_id.value, trading_account_id), cursor.rowcount == 1

    def amend_paper_limit(
        self, *, client_action_id: str, request_fingerprint: str,
        order_id: OrderId, trading_account_id: TradingAccountId,
        price: Decimal, updated_at_ms: int,
    ) -> tuple[PaperLimitOrderRecord, bool]:
        self._assert_owner()
        action = self._connection.execute(
            "SELECT operation, request_fingerprint, order_id FROM paper_limit_actions WHERE client_action_id = ?",
            (client_action_id,),
        ).fetchone()
        if action is not None:
            if action[0] != "amend" or action[1] != request_fingerprint or action[2] != order_id.value:
                raise DuplicateIdentity("client action identity was reused with different intent")
            existing = self.get_paper_limit(order_id.value, trading_account_id)
            if existing is None:
                raise PersistenceError("durable amend action references no PAPER limit")
            return existing, False

        current = self._get_paper_limit_by_id(order_id.value)
        if current is not None and current.trading_account_id != trading_account_id:
            raise ValueError("PAPER limit account does not match active account")
        if current is None or current.status not in {"open", "partially_filled"}:
            raise PersistenceError("PAPER limit is missing or inactive")

        changed = current.price != price
        with self._transaction():
            if changed:
                cursor = self._connection.execute(
                    "UPDATE paper_limit_orders SET price = ?, updated_at_ms = ? WHERE order_id = ? AND trading_account_id = ? AND status IN ('open', 'partially_filled')",
                    (_decimal_text(price), updated_at_ms, order_id.value, trading_account_id.value),
                )
                if cursor.rowcount != 1:
                    raise PersistenceError("PAPER limit is missing or inactive")
            self._connection.execute(
                "INSERT INTO paper_limit_actions VALUES (?, 'amend', ?, ?, ?)",
                (client_action_id, request_fingerprint, order_id.value, updated_at_ms),
            )
            if changed:
                self._advance_paper_state_revision(
                    current.trading_account_id, current.symbol,
                )
        amended = self.get_paper_limit(order_id.value, trading_account_id)
        if amended is None:
            raise PersistenceError("amended PAPER limit is unavailable")
        return amended, changed

    def _get_paper_limit_by_id(self, order_id: str) -> PaperLimitOrderRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM paper_limit_orders WHERE order_id = ?", (order_id,),
        ).fetchone()
        return _paper_limit_from_row(row) if row is not None else None

    def get_paper_limit(
        self, order_id: str, trading_account_id: TradingAccountId,
    ) -> PaperLimitOrderRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM paper_limit_orders WHERE order_id = ? AND trading_account_id = ?",
            (order_id, trading_account_id.value),
        ).fetchone()
        return _paper_limit_from_row(row) if row is not None else None

    def load_active_paper_limits(
        self, trading_account_id: TradingAccountId, symbol: Symbol,
    ) -> tuple[PaperLimitOrderRecord, ...]:
        self._assert_owner()
        rows = self._connection.execute(
            "SELECT * FROM paper_limit_orders WHERE trading_account_id = ? AND symbol = ? AND status IN ('open', 'partially_filled') ORDER BY created_at_ms, order_id",
            (trading_account_id.value, symbol.value),
        )
        return tuple(_paper_limit_from_row(row) for row in rows)

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

    def claim_live_market_action(
        self, record: CommandRecord, *, session_generation: int,
        client_action_id: str, request_fingerprint: str,
    ) -> tuple[LiveMarketActionRecord, bool]:
        """Atomically bind one logical LIVE action to one durable command identity."""
        self._assert_owner()
        existing = self.get_live_market_action(
            record.trading_account_id, session_generation, client_action_id,
        )
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise DuplicateIdentity("client_action_id was reused with different LIVE intent")
            return existing, False
        try:
            with self._transaction():
                self._connection.execute(
                    """INSERT INTO trading_commands (
                        command_id, order_link_id, trading_account_id, category, symbol,
                        position_idx, command_kind, side, requested_notional,
                        normalized_price, normalized_quantity, origin, controller,
                        current_state, version, exchange_order_id, created_at_ms, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record.command_id.value, record.order_link_id,
                        record.trading_account_id.value, record.category.value,
                        record.symbol.value, record.position_idx, record.command_kind,
                        record.side.value, _decimal_text(record.requested_notional.value),
                        _optional_decimal(record.normalized_price),
                        _optional_decimal(record.normalized_quantity), record.origin.value,
                        record.controller.value, record.current_state.value, record.version,
                        None, record.created_at_ms, record.updated_at_ms,
                    ),
                )
                self._connection.execute(
                    "INSERT INTO command_state_history (command_id, previous_state, next_state, reason, occurred_at_ms) VALUES (?, NULL, ?, ?, ?)",
                    (record.command_id.value, record.current_state.value,
                     "durable LIVE client action claimed", record.updated_at_ms),
                )
                self._connection.execute(
                    "INSERT INTO live_market_actions VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                    (record.trading_account_id.value, session_generation, client_action_id,
                     request_fingerprint, record.command_id.value, record.order_link_id,
                     record.created_at_ms),
                )
        except sqlite3.IntegrityError:
            existing = self.get_live_market_action(
                record.trading_account_id, session_generation, client_action_id,
            )
            if existing is None or existing.request_fingerprint != request_fingerprint:
                raise DuplicateIdentity("LIVE action identity conflict")
            return existing, False
        return self.get_live_market_action(
            record.trading_account_id, session_generation, client_action_id,
        ), True

    def get_live_market_action(
        self, account_id: TradingAccountId, session_generation: int, client_action_id: str,
    ) -> LiveMarketActionRecord | None:
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM live_market_actions WHERE trading_account_id = ? AND session_generation = ? AND client_action_id = ?",
            (account_id.value, session_generation, client_action_id),
        ).fetchone()
        if row is None:
            return None
        return LiveMarketActionRecord(
            TradingAccountId(row["trading_account_id"]), int(row["session_generation"]),
            row["client_action_id"], row["request_fingerprint"],
            CommandId(row["command_id"]), row["order_link_id"],
            bool(row["dispatch_started"]), int(row["created_at_ms"]),
        )

    def find_live_market_action(
        self, account_id: TradingAccountId, client_action_id: str,
    ) -> LiveMarketActionRecord | None:
        """Find the original durable LIVE action across restarted sessions."""
        self._assert_owner()
        row = self._connection.execute(
            """SELECT * FROM live_market_actions
               WHERE trading_account_id = ? AND client_action_id = ?
               ORDER BY created_at_ms, session_generation LIMIT 1""",
            (account_id.value, client_action_id),
        ).fetchone()
        if row is None:
            return None
        return LiveMarketActionRecord(
            TradingAccountId(row["trading_account_id"]), int(row["session_generation"]),
            row["client_action_id"], row["request_fingerprint"],
            CommandId(row["command_id"]), row["order_link_id"],
            bool(row["dispatch_started"]), int(row["created_at_ms"]),
        )

    def load_unresolved_live_market_actions(
        self, account_id: TradingAccountId | None = None,
    ) -> tuple[LiveMarketActionRecord, ...]:
        """Load durable LIVE actions whose exchange outcome still needs REST evidence."""
        self._assert_owner()
        parameters: list[object] = [
            CommandState.SUBMITTING.value, CommandState.ACKNOWLEDGED.value,
            CommandState.UNKNOWN.value, CommandState.RECONCILING.value,
        ]
        account_clause = ""
        if account_id is not None:
            account_clause = " AND a.trading_account_id = ?"
            parameters.append(account_id.value)
        rows = self._connection.execute(
            f"""SELECT a.* FROM live_market_actions a
                JOIN trading_commands c ON c.command_id = a.command_id
                WHERE c.current_state IN (?, ?, ?, ?){account_clause}
                ORDER BY a.created_at_ms, a.trading_account_id, a.session_generation""",
            parameters,
        ).fetchall()
        return tuple(
            LiveMarketActionRecord(
                TradingAccountId(row["trading_account_id"]), int(row["session_generation"]),
                row["client_action_id"], row["request_fingerprint"],
                CommandId(row["command_id"]), row["order_link_id"],
                bool(row["dispatch_started"]), int(row["created_at_ms"]),
            )
            for row in rows
        )

    def begin_live_market_dispatch(self, action: LiveMarketActionRecord, *, occurred_at_ms: int) -> CommandRecord | None:
        """Claim the sole irreversible dispatch attempt and persist SUBMITTING atomically."""
        self._assert_owner()
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE live_market_actions SET dispatch_started = 1 WHERE trading_account_id = ? AND session_generation = ? AND client_action_id = ? AND dispatch_started = 0",
                (action.trading_account_id.value, action.session_generation, action.client_action_id),
            )
            if cursor.rowcount != 1:
                return None
            command = self.get_command(action.command_id)
            if command is None or command.current_state is not CommandState.ADMITTED:
                raise PersistenceError("claimed LIVE command is not dispatchable")
            self._connection.execute(
                "UPDATE trading_commands SET current_state = ?, version = ?, updated_at_ms = ? WHERE command_id = ? AND current_state = ? AND version = ?",
                (CommandState.SUBMITTING.value, command.version + 1, occurred_at_ms,
                 command.command_id.value, CommandState.ADMITTED.value, command.version),
            )
            self._connection.execute(
                "INSERT INTO command_state_history (command_id, previous_state, next_state, reason, occurred_at_ms) VALUES (?, ?, ?, ?, ?)",
                (command.command_id.value, CommandState.ADMITTED.value,
                 CommandState.SUBMITTING.value, "single LIVE mutation attempt durably started",
                 occurred_at_ms),
            )
        return self.get_command(action.command_id)

    def has_unresolved_live_market_action(
        self, account_id: TradingAccountId, session_generation: int,
    ) -> bool:
        self._assert_owner()
        row = self._connection.execute(
            """SELECT 1 FROM live_market_actions a
               JOIN trading_commands c ON c.command_id = a.command_id
               WHERE a.trading_account_id = ? AND a.session_generation = ?
                 AND c.current_state IN (?, ?, ?, ?)
               LIMIT 1""",
            (account_id.value, session_generation, CommandState.SUBMITTING.value,
             CommandState.ACKNOWLEDGED.value, CommandState.UNKNOWN.value,
             CommandState.RECONCILING.value),
        ).fetchone()
        return row is not None

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
            self._clear_protection_after_confirmed_flat(projection)
            if command_id is not None:
                self._correlate_command_order(command_id, execution.order_id)
            self._advance_paper_state_revision(
                execution.dedup_key.trading_account_id, execution.symbol,
            )
        return ExecutionApplyResult.APPLIED

    def apply_paper_limit_execution_once(
        self,
        order_id: OrderId,
        execution: Execution,
        projection: PositionProjectionUpdate,
        *,
        updated_at_ms: int,
    ) -> ExecutionApplyResult:
        if execution.order_id != order_id:
            raise ValueError("execution order does not match PAPER limit")
        if execution.dedup_key.trading_account_id != projection.position_key.trading_account_id:
            raise ValueError("execution and projection account differ")
        if execution.dedup_key.category is not projection.position_key.category:
            raise ValueError("execution and projection category differ")
        if execution.symbol != projection.position_key.symbol:
            raise ValueError("execution and projection symbol differ")
        if execution.quantity.value <= 0:
            raise ValueError("PAPER limit execution quantity must be positive")

        with self._transaction():
            existing_execution = self._execution_row(execution.dedup_key)
            if existing_execution is not None:
                if _execution_from_row(existing_execution) != execution:
                    raise ImmutableExecutionConflict(
                        "execution identity already exists with different immutable evidence"
                    )
                return ExecutionApplyResult.DUPLICATE

            row = self._connection.execute(
                "SELECT * FROM paper_limit_orders WHERE order_id = ?",
                (order_id.value,),
            ).fetchone()
            if row is None:
                raise PersistenceError("PAPER limit is missing")

            order = _paper_limit_from_row(row)
            if order.status not in {"open", "partially_filled"}:
                raise PersistenceError("PAPER limit is inactive")
            if order.trading_account_id != execution.dedup_key.trading_account_id:
                raise ValueError("PAPER limit and execution account differ")
            if order.symbol != execution.symbol:
                raise ValueError("PAPER limit and execution symbol differ")
            if order.side is not execution.side:
                raise ValueError("PAPER limit and execution side differ")

            new_filled = order.filled_quantity + execution.quantity.value
            if new_filled > order.quantity:
                raise ValueError("PAPER limit execution exceeds remaining quantity")

            new_status = (
                "filled"
                if new_filled == order.quantity
                else "partially_filled"
            )

            self._insert_execution(execution)
            self._write_projection(projection)
            self._clear_protection_after_confirmed_flat(projection)

            cursor = self._connection.execute(
                """
                UPDATE paper_limit_orders
                SET filled_quantity = ?, status = ?, updated_at_ms = ?
                WHERE order_id = ?
                  AND filled_quantity = ?
                  AND status IN ('open', 'partially_filled')
                """,
                (
                    _decimal_text(new_filled),
                    new_status,
                    updated_at_ms,
                    order_id.value,
                    _decimal_text(order.filled_quantity),
                ),
            )
            if cursor.rowcount != 1:
                raise ConcurrentUpdate("PAPER limit fill state changed concurrently")
            self._advance_paper_state_revision(
                execution.dedup_key.trading_account_id, execution.symbol,
            )

        return ExecutionApplyResult.APPLIED

    def _clear_protection_after_confirmed_flat(
        self, projection: PositionProjectionUpdate,
    ) -> None:
        if projection.side is PositionSide.FLAT:
            if projection.quantity.value != 0:
                raise ValueError("FLAT projection must have zero quantity")
            self._delete_protection_projection(projection.position_key)

    def _delete_protection_projection(self, position_key: PositionKey) -> None:
        self._connection.execute(
            """DELETE FROM protection_projections
               WHERE trading_account_id=? AND category=? AND symbol=? AND position_idx=?""",
            (
                position_key.trading_account_id.value, position_key.category.value,
                position_key.symbol.value, position_key.position_idx,
            ),
        )

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

    def load_open_position_projections(
        self, trading_account_id: TradingAccountId,
    ) -> tuple[PositionProjectionRecord, ...]:
        """Return one-way open net positions for exactly one account."""

        self._assert_owner()
        rows = self._connection.execute(
            """
            SELECT * FROM position_projections
            WHERE trading_account_id = ? AND category = ? AND position_idx = 0
            ORDER BY symbol
            """,
            (trading_account_id.value, Category.LINEAR.value),
        )
        projections = tuple(_projection_from_row(row) for row in rows)
        return tuple(
            item for item in projections
            if item.side is not PositionSide.FLAT and item.quantity.value > 0
        )

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
