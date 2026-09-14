"""True read-only SQLite reader for Robot Statistics v1."""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import RobotStatisticsTrade


class RobotStatisticsReadError(RuntimeError):
    """Statistics read failed closed because durable evidence was unavailable."""


_REQUIRED_TABLES = frozenset({"robot_trades", "robot_candidates"})

_REQUIRED_TRADE_COLUMNS = frozenset(
    {
        "trade_id",
        "trading_account_id",
        "candidate_id",
        "symbol",
        "direction",
        "pattern",
        "source_timeframe",
        "signal_time_ms",
        "entry_time_ms",
        "entry_path",
        "actual_wv",
        "average_entry",
        "entry_quantity",
        "entry_position_version",
        "stop_price",
        "take_price",
        "exit_time_ms",
        "exit_price",
        "exit_reason",
        "realized_pnl_usdt",
        "realized_pnl_pct",
        "fees_costs_usdt",
    }
)

_REQUIRED_CANDIDATE_COLUMNS = frozenset(
    {
        "candidate_id",
        "trading_account_id",
    }
)


def _load_decimal(value: object, *, field: str) -> Decimal:
    if not isinstance(value, str):
        raise RobotStatisticsReadError(
            f"{field} must be persisted as canonical Decimal text"
        )
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RobotStatisticsReadError(f"{field} is not a valid Decimal") from exc
    if not result.is_finite():
        raise RobotStatisticsReadError(f"{field} must be finite")
    return result


def _load_optional_decimal(value: object, *, field: str) -> Decimal | None:
    if value is None:
        return None
    return _load_decimal(value, field=field)


class RobotStatisticsReader:
    """Account-scoped Robot statistics reader with no write-capable initialization."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)

    def _connect_read_only(self) -> sqlite3.Connection:
        path = self._database_path

        if not path.exists():
            raise RobotStatisticsReadError("statistics database does not exist")
        if not path.is_file():
            raise RobotStatisticsReadError("statistics database path is not a file")

        uri = path.resolve().as_uri() + "?mode=ro"
        try:
            connection = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            raise RobotStatisticsReadError(
                "unable to open statistics database read-only"
            ) from exc

        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _table_columns(
        connection: sqlite3.Connection,
        table_name: str,
    ) -> frozenset[str]:
        rows = connection.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
        return frozenset(str(row["name"]) for row in rows)

    @classmethod
    def _validate_schema(cls, connection: sqlite3.Connection) -> None:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ('robot_trades', 'robot_candidates')
            """
        ).fetchall()
        tables = frozenset(str(row["name"]) for row in table_rows)

        missing_tables = _REQUIRED_TABLES - tables
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise RobotStatisticsReadError(
                f"statistics schema missing required tables: {missing}"
            )

        trade_columns = cls._table_columns(connection, "robot_trades")
        missing_trade_columns = _REQUIRED_TRADE_COLUMNS - trade_columns
        if missing_trade_columns:
            missing = ", ".join(sorted(missing_trade_columns))
            raise RobotStatisticsReadError(
                f"robot_trades missing required columns: {missing}"
            )

        candidate_columns = cls._table_columns(connection, "robot_candidates")
        missing_candidate_columns = _REQUIRED_CANDIDATE_COLUMNS - candidate_columns
        if missing_candidate_columns:
            missing = ", ".join(sorted(missing_candidate_columns))
            raise RobotStatisticsReadError(
                f"robot_candidates missing required columns: {missing}"
            )

    def load_completed_trades(
        self,
        *,
        trading_account_id: str,
    ) -> tuple[RobotStatisticsTrade, ...]:
        if not trading_account_id or not trading_account_id.strip():
            raise ValueError("trading_account_id must be non-empty")

        connection = self._connect_read_only()
        try:
            self._validate_schema(connection)

            rows = connection.execute(
                """
                SELECT
                    t.trade_id,
                    t.trading_account_id,
                    t.candidate_id,
                    t.symbol,
                    t.direction,
                    t.pattern,
                    t.source_timeframe,
                    t.signal_time_ms,
                    t.entry_time_ms,
                    t.entry_path,
                    t.actual_wv,
                    t.average_entry,
                    t.entry_quantity,
                    t.entry_position_version,
                    t.stop_price,
                    t.take_price,
                    t.exit_time_ms,
                    t.exit_price,
                    t.exit_reason,
                    t.realized_pnl_usdt,
                    t.realized_pnl_pct,
                    t.fees_costs_usdt
                FROM robot_trades AS t
                INNER JOIN robot_candidates AS c
                    ON c.candidate_id = t.candidate_id
                   AND c.trading_account_id = t.trading_account_id
                WHERE t.trading_account_id = ?
                  AND t.exit_time_ms IS NOT NULL
                  AND t.exit_price IS NOT NULL
                  AND t.exit_reason IS NOT NULL
                  AND t.realized_pnl_usdt IS NOT NULL
                  AND t.realized_pnl_pct IS NOT NULL
                ORDER BY t.exit_time_ms, t.trade_id
                """,
                (trading_account_id,),
            ).fetchall()

            return tuple(self._trade_from_row(row) for row in rows)
        except sqlite3.Error as exc:
            raise RobotStatisticsReadError(
                "failed to read Robot statistics"
            ) from exc
        finally:
            connection.close()

    @staticmethod
    def _trade_from_row(row: sqlite3.Row) -> RobotStatisticsTrade:
        exit_time_ms = row["exit_time_ms"]
        exit_price = row["exit_price"]
        exit_reason = row["exit_reason"]
        realized_pnl_usdt = row["realized_pnl_usdt"]
        realized_pnl_pct = row["realized_pnl_pct"]

        if (
            exit_time_ms is None
            or exit_price is None
            or exit_reason is None
            or realized_pnl_usdt is None
            or realized_pnl_pct is None
        ):
            raise RobotStatisticsReadError(
                "completed trade contains incomplete close evidence"
            )

        entry_quantity = _load_optional_decimal(
            row["entry_quantity"],
            field="entry_quantity",
        )
        entry_position_version = row["entry_position_version"]
        if entry_position_version is not None:
            entry_position_version = int(entry_position_version)

        return RobotStatisticsTrade(
            trade_id=str(row["trade_id"]),
            trading_account_id=str(row["trading_account_id"]),
            candidate_id=str(row["candidate_id"]),
            symbol=str(row["symbol"]),
            direction=str(row["direction"]),
            pattern=str(row["pattern"]),
            source_timeframe=str(row["source_timeframe"]),
            signal_time_ms=int(row["signal_time_ms"]),
            entry_time_ms=int(row["entry_time_ms"]),
            entry_path=str(row["entry_path"]),
            actual_wv=_load_decimal(row["actual_wv"], field="actual_wv"),
            average_entry=_load_decimal(
                row["average_entry"],
                field="average_entry",
            ),
            entry_quantity=entry_quantity,
            entry_position_version=entry_position_version,
            stop_price=_load_decimal(row["stop_price"], field="stop_price"),
            take_price=_load_decimal(row["take_price"], field="take_price"),
            exit_time_ms=int(exit_time_ms),
            exit_price=_load_decimal(exit_price, field="exit_price"),
            exit_reason=str(exit_reason),
            realized_pnl_usdt=_load_decimal(
                realized_pnl_usdt,
                field="realized_pnl_usdt",
            ),
            realized_pnl_pct=_load_decimal(
                realized_pnl_pct,
                field="realized_pnl_pct",
            ),
            fees_costs_usdt=_load_optional_decimal(
                row["fees_costs_usdt"],
                field="fees_costs_usdt",
            ),
        )