"""Durable Robot-owned PAPER protection-trigger obligations.

This module extends the persistence boundary without changing execution semantics:
D2.1 only latches trigger evidence, owns stable close identities, exposes unresolved
work for restart, and provides optimistic state transitions. It does not dispatch
orders or subscribe to market data.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from terminal.domain.models import ExecutionId, OrderId, Symbol, TradingAccountId


SCHEMA_V17_MIGRATION_STATEMENTS = (
    """
    CREATE TABLE paper_protection_obligations (
        obligation_id TEXT PRIMARY KEY,
        trade_id TEXT NOT NULL UNIQUE,
        trading_account_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        protection_version INTEGER NOT NULL,
        winning_leg TEXT NOT NULL,
        trigger_price TEXT NOT NULL,
        observed_exit_price TEXT NOT NULL,
        observed_quantity TEXT NOT NULL,
        market_event_id TEXT NOT NULL,
        source_received_at_ms INTEGER NOT NULL,
        latched_at_ms INTEGER NOT NULL,
        order_id TEXT NOT NULL UNIQUE,
        exec_id TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        version INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        FOREIGN KEY (trade_id) REFERENCES robot_trades(trade_id),
        CHECK (protection_version >= 1),
        CHECK (winning_leg IN ('STOP', 'TAKE')),
        CHECK (status IN ('TRIGGERED', 'DISPATCHING', 'RESOLVED')),
        CHECK (version >= 1),
        CHECK (source_received_at_ms >= 0),
        CHECK (latched_at_ms >= source_received_at_ms),
        CHECK (updated_at_ms >= latched_at_ms)
    ) WITHOUT ROWID
    """,
)


@dataclass(frozen=True, slots=True)
class PaperProtectionObligationRecord:
    obligation_id: str
    trade_id: str
    trading_account_id: TradingAccountId
    symbol: Symbol
    protection_version: int
    winning_leg: str
    trigger_price: Decimal
    observed_exit_price: Decimal
    observed_quantity: Decimal
    market_event_id: str
    source_received_at_ms: int
    latched_at_ms: int
    order_id: OrderId
    exec_id: ExecutionId
    status: str
    version: int
    updated_at_ms: int


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        raise TypeError("protection obligation decimal values must be Decimal")
    if not value.is_finite():
        raise ValueError("protection obligation decimal values must be finite")
    return str(value)


def _load_decimal(value: str) -> Decimal:
    try:
        result = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("persisted protection obligation Decimal is invalid") from exc
    if not result.is_finite():
        raise ValueError("persisted protection obligation Decimal must be finite")
    return result


def _record_from_row(row: sqlite3.Row) -> PaperProtectionObligationRecord:
    return PaperProtectionObligationRecord(
        obligation_id=row["obligation_id"],
        trade_id=row["trade_id"],
        trading_account_id=TradingAccountId(row["trading_account_id"]),
        symbol=Symbol(row["symbol"]),
        protection_version=int(row["protection_version"]),
        winning_leg=row["winning_leg"],
        trigger_price=_load_decimal(row["trigger_price"]),
        observed_exit_price=_load_decimal(row["observed_exit_price"]),
        observed_quantity=_load_decimal(row["observed_quantity"]),
        market_event_id=row["market_event_id"],
        source_received_at_ms=int(row["source_received_at_ms"]),
        latched_at_ms=int(row["latched_at_ms"]),
        order_id=OrderId(row["order_id"]),
        exec_id=ExecutionId(row["exec_id"]),
        status=row["status"],
        version=int(row["version"]),
        updated_at_ms=int(row["updated_at_ms"]),
    )


def _stable_identities(trade_id: str) -> tuple[str, OrderId, ExecutionId]:
    digest = hashlib.sha256(f"paper-protection\0{trade_id}".encode("utf-8")).hexdigest()
    return (
        f"paper-protection-{digest}",
        OrderId(f"paper-protection-order-{digest}"),
        ExecutionId(f"paper-protection-exec-{digest}"),
    )


def _install_schema_extension() -> None:
    from terminal.persistence import schema

    if getattr(schema, "SCHEMA_VERSION", 0) >= 17:
        return
    if schema.SCHEMA_VERSION != 16:
        raise RuntimeError("paper protection obligations require Terminal schema v16 baseline")
    schema.SCHEMA_V17_MIGRATION_STATEMENTS = SCHEMA_V17_MIGRATION_STATEMENTS
    schema.SCHEMA_STATEMENTS = schema.SCHEMA_STATEMENTS + SCHEMA_V17_MIGRATION_STATEMENTS
    schema.SCHEMA_VERSION = 17


def _install_store_extension() -> None:
    from terminal.persistence import sqlite_store as store_module

    SQLiteStore = store_module.SQLiteStore
    if getattr(SQLiteStore, "_paper_protection_obligations_v17_installed", False):
        return

    original_initializer = SQLiteStore._initialize_or_validate_schema

    def _validate_v17(connection: sqlite3.Connection) -> None:
        SQLiteStore._validate_required_tables(connection, version=16)
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='paper_protection_obligations'"
        ).fetchone()
        if row is None:
            raise store_module.SchemaError("Terminal schema v17 is incomplete")

    def _migrate_v16_to_v17(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in SCHEMA_V17_MIGRATION_STATEMENTS:
                connection.execute(statement)
            connection.execute("PRAGMA user_version = 17")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        _validate_v17(connection)

    def _initialize_or_validate_schema(connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 17:
            _validate_v17(connection)
            return
        if version == 16:
            SQLiteStore._validate_required_tables(connection, version=16)
            _migrate_v16_to_v17(connection)
            return

        original_initializer(connection)
        migrated_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if migrated_version == 16:
            _migrate_v16_to_v17(connection)
        elif migrated_version == 17:
            _validate_v17(connection)
        else:
            raise store_module.SchemaError(
                f"Terminal schema migration did not reach v17: {migrated_version}"
            )

    def schema_version(self) -> int:
        self._assert_owner()
        return int(self._connection.execute("PRAGMA user_version").fetchone()[0])

    def has_table(self, table_name: str) -> bool:
        self._assert_owner()
        if not isinstance(table_name, str) or not table_name.strip():
            raise ValueError("table_name must be non-empty")
        row = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name.strip(),),
        ).fetchone()
        return row is not None

    def get_paper_protection_obligation(self, obligation_id: str):
        self._assert_owner()
        row = self._connection.execute(
            "SELECT * FROM paper_protection_obligations WHERE obligation_id=?",
            (obligation_id,),
        ).fetchone()
        return _record_from_row(row) if row is not None else None

    def latch_paper_protection_obligation(
        self, *, trade_id: str, protection_version: int, winning_leg: str,
        trigger_price: Decimal, observed_exit_price: Decimal,
        observed_quantity: Decimal, market_event_id: str,
        source_received_at_ms: int, latched_at_ms: int,
    ):
        self._assert_owner()
        if not isinstance(trade_id, str) or not trade_id.strip():
            raise ValueError("trade_id must be non-empty")
        if protection_version < 1:
            raise ValueError("protection_version must be positive")
        if winning_leg not in {"STOP", "TAKE"}:
            raise ValueError("winning_leg must be STOP or TAKE")
        for value in (trigger_price, observed_exit_price, observed_quantity):
            _decimal_text(value)
        if trigger_price <= 0 or observed_exit_price <= 0 or observed_quantity <= 0:
            raise ValueError("protection obligation prices/quantity must be positive")
        if not isinstance(market_event_id, str) or not market_event_id.strip():
            raise ValueError("market_event_id must be non-empty")
        if source_received_at_ms < 0 or latched_at_ms < source_received_at_ms:
            raise ValueError("protection obligation timestamps are invalid")

        existing = self._connection.execute(
            "SELECT * FROM paper_protection_obligations WHERE trade_id=?",
            (trade_id,),
        ).fetchone()
        if existing is not None:
            return _record_from_row(existing), False

        trade = self._connection.execute(
            "SELECT trading_account_id, symbol, exit_time_ms FROM robot_trades WHERE trade_id=?",
            (trade_id,),
        ).fetchone()
        if trade is None:
            raise store_module.PersistenceError("Robot trade does not exist")
        if trade["exit_time_ms"] is not None:
            raise store_module.PersistenceError("Robot trade is already closed")

        obligation_id, order_id, exec_id = _stable_identities(trade_id)
        try:
            with self._transaction():
                existing = self._connection.execute(
                    "SELECT * FROM paper_protection_obligations WHERE trade_id=?",
                    (trade_id,),
                ).fetchone()
                if existing is not None:
                    return _record_from_row(existing), False
                self._connection.execute(
                    """INSERT INTO paper_protection_obligations (
                        obligation_id, trade_id, trading_account_id, symbol,
                        protection_version, winning_leg, trigger_price,
                        observed_exit_price, observed_quantity, market_event_id,
                        source_received_at_ms, latched_at_ms, order_id, exec_id,
                        status, version, updated_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRIGGERED', 1, ?)""",
                    (
                        obligation_id, trade_id, trade["trading_account_id"], trade["symbol"],
                        protection_version, winning_leg, _decimal_text(trigger_price),
                        _decimal_text(observed_exit_price), _decimal_text(observed_quantity),
                        market_event_id.strip(), source_received_at_ms, latched_at_ms,
                        order_id.value, exec_id.value, latched_at_ms,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            existing = self._connection.execute(
                "SELECT * FROM paper_protection_obligations WHERE trade_id=?",
                (trade_id,),
            ).fetchone()
            if existing is not None:
                return _record_from_row(existing), False
            raise store_module.DuplicateIdentity(
                "PAPER protection obligation durable identity conflict"
            ) from exc

        created = get_paper_protection_obligation(self, obligation_id)
        if created is None:
            raise store_module.PersistenceError("latched PAPER protection obligation disappeared")
        return created, True

    def load_unresolved_paper_protection_obligations(self, trading_account_id: TradingAccountId):
        self._assert_owner()
        rows = self._connection.execute(
            """SELECT * FROM paper_protection_obligations
               WHERE trading_account_id=? AND status!='RESOLVED'
               ORDER BY latched_at_ms, obligation_id""",
            (trading_account_id.value,),
        ).fetchall()
        return tuple(_record_from_row(row) for row in rows)

    def transition_paper_protection_obligation(
        self, obligation_id: str, *, expected_status: str, next_status: str,
        expected_version: int, updated_at_ms: int,
    ):
        self._assert_owner()
        transitions = {
            "TRIGGERED": {"DISPATCHING"},
            "DISPATCHING": {"RESOLVED"},
            "RESOLVED": set(),
        }
        if expected_status not in transitions or next_status not in transitions[expected_status]:
            raise ValueError("unsupported PAPER protection obligation transition")
        if expected_version < 1 or updated_at_ms < 0:
            raise ValueError("invalid PAPER protection obligation revision/timestamp")
        with self._transaction():
            cursor = self._connection.execute(
                """UPDATE paper_protection_obligations
                   SET status=?, version=version+1, updated_at_ms=?
                   WHERE obligation_id=? AND status=? AND version=? AND updated_at_ms<=?""",
                (
                    next_status, updated_at_ms, obligation_id,
                    expected_status, expected_version, updated_at_ms,
                ),
            )
            if cursor.rowcount != 1:
                raise store_module.ConcurrentUpdate(
                    "PAPER protection obligation state/version no longer matches"
                )
        current = get_paper_protection_obligation(self, obligation_id)
        if current is None:
            raise store_module.PersistenceError("PAPER protection obligation disappeared")
        return current

    SQLiteStore._initialize_or_validate_schema = staticmethod(_initialize_or_validate_schema)
    SQLiteStore.schema_version = schema_version
    SQLiteStore.has_table = has_table
    SQLiteStore.get_paper_protection_obligation = get_paper_protection_obligation
    SQLiteStore.latch_paper_protection_obligation = latch_paper_protection_obligation
    SQLiteStore.load_unresolved_paper_protection_obligations = (
        load_unresolved_paper_protection_obligations
    )
    SQLiteStore.transition_paper_protection_obligation = transition_paper_protection_obligation
    SQLiteStore._paper_protection_obligations_v17_installed = True


def install() -> None:
    """Install the v17 schema and SQLiteStore extension exactly once."""

    _install_schema_extension()
    _install_store_extension()
