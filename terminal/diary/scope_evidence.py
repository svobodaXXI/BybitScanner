"""Read-only provenance lookup for account-scoped Trading Diary reports.

The execution fact has no controller field. Only a UNIQUE matching immutable
trading command can prove MANUAL/ROBOT attribution; missing/conflicting
ownership remains unattributed rather than guessed from symbol or timestamp.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal.domain.models import Category, ExecutionDedupKey, ExecutionId, Origin, TradingAccountId

from .scoped_statistics_archive import StatisticsScopeError


def load_order_origins_read_only(
    database_path: str | Path, *, account_id: str,
) -> dict[ExecutionDedupKey, Origin]:
    """Resolve only proven local executions; never create/migrate/write PAPER DB."""
    if not isinstance(account_id, str) or not account_id.strip() or account_id != account_id.strip():
        raise StatisticsScopeError("account_identity_required")
    path = Path(database_path)
    if not path.is_file():
        raise StatisticsScopeError("execution_source_unavailable")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT e.trading_account_id, e.category, e.exec_id,
                      c.command_id, c.origin, c.controller
               FROM executions e
               LEFT JOIN trading_commands c
                 ON c.trading_account_id=e.trading_account_id
                AND c.exchange_order_id=e.order_id
               WHERE e.trading_account_id=?
               ORDER BY e.category, e.exec_id, c.command_id""",
            (account_id,),
        )
        observed: dict[ExecutionDedupKey, list[sqlite3.Row]] = {}
        for row in rows:
            if row["category"] != Category.LINEAR.value:
                raise StatisticsScopeError("unsupported_statistics_category")
            key = ExecutionDedupKey(
                TradingAccountId(row["trading_account_id"]),
                Category.LINEAR,
                ExecutionId(row["exec_id"]),
            )
            observed.setdefault(key, []).append(row)
        results: dict[ExecutionDedupKey, Origin] = {}
        for key, entries in observed.items():
            if len(entries) != 1:
                raise StatisticsScopeError("ambiguous_execution_command_ownership")
            row = entries[0]
            pair = (row["origin"], row["controller"])
            if pair == (Origin.TERMINAL_MANUAL.value, "manual"):
                results[key] = Origin.TERMINAL_MANUAL
            elif pair == (Origin.ROBOT.value, "robot"):
                results[key] = Origin.ROBOT
            # An unmatched/external/legacy command remains UNKNOWN to the
            # scope publisher; it blocks any episode containing this fill.
        return results
    except sqlite3.Error as exc:
        raise StatisticsScopeError("execution_source_unavailable") from exc
    finally:
        connection.close()
