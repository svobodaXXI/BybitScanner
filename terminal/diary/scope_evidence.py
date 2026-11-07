"""Read-only, same-snapshot execution provenance for account-scoped Diary.

Execution facts have no controller field. Use UNIQUE durable commands or exact
Robot-entry/protection attestations; ambiguous/LEGACY/external evidence is unknown.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from terminal.domain.models import Category, ExecutionDedupKey, ExecutionId, Origin, TradingAccountId
from .scoped_statistics_archive import StatisticsScopeError


def load_order_origins_from_connection(
    connection: sqlite3.Connection, *, account_id: str,
) -> dict[ExecutionDedupKey, Origin]:
    """Use the CALLER'S read transaction, so fills and origins share one snapshot."""
    if not isinstance(account_id, str) or not account_id.strip() or account_id != account_id.strip():
        raise StatisticsScopeError("account_identity_required")
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
                TradingAccountId(row["trading_account_id"]), Category.LINEAR, ExecutionId(row["exec_id"]),
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
            # Missing, EXTERNAL and inconsistent origin/controller remain unknown.

        # PAPER Robot LIMIT entries are recorded in robot_entry_orders, not
        # necessarily in trading_commands. LEGACY (unattested) remains UNKNOWN.
        # STOP/TAKE exits have an immutable obligation with exact order + exec
        # identity and resolved Robot trade lineage. Never infer from symbol/time.
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        robot_rows: list[sqlite3.Row] = []
        if {"robot_entry_orders", "paper_limit_orders"} <= tables:
            robot_rows.extend(connection.execute(
                """SELECT e.trading_account_id, e.category, e.exec_id
                   FROM executions e
                   JOIN robot_entry_orders r
                     ON r.order_id=e.order_id AND r.trading_account_id=e.trading_account_id
                   JOIN paper_limit_orders p
                     ON p.order_id=r.order_id AND p.trading_account_id=r.trading_account_id
                   WHERE e.trading_account_id=?
                     AND r.origin='ROBOT' AND r.admission_version IS NOT NULL""",
                (account_id,),
            ).fetchall())
        if {"paper_protection_obligations", "robot_trades"} <= tables:
            robot_rows.extend(connection.execute(
                """SELECT e.trading_account_id, e.category, e.exec_id
                   FROM executions e
                   JOIN paper_protection_obligations o
                     ON o.trading_account_id=e.trading_account_id
                    AND o.order_id=e.order_id AND o.exec_id=e.exec_id
                   JOIN robot_trades r
                     ON r.trade_id=o.trade_id AND r.trading_account_id=e.trading_account_id
                   WHERE e.trading_account_id=? AND o.status='RESOLVED'""",
                (account_id,),
            ).fetchall())
        for robot_row in robot_rows:
            if robot_row["category"] != Category.LINEAR.value:
                raise StatisticsScopeError("unsupported_statistics_category")
            key = ExecutionDedupKey(
                TradingAccountId(robot_row["trading_account_id"]),
                Category.LINEAR, ExecutionId(robot_row["exec_id"]),
            )
            matching_commands = observed.get(key, [])
            if len(matching_commands) != 1:
                raise StatisticsScopeError("ambiguous_execution_command_ownership")
            command = matching_commands[0]
            if command["command_id"] is not None and (
                command["origin"], command["controller"]
            ) != (Origin.ROBOT.value, "robot"):
                raise StatisticsScopeError("conflicting_robot_execution_ownership")
            if key in results and results[key] != Origin.ROBOT:
                raise StatisticsScopeError("conflicting_robot_execution_ownership")
            results[key] = Origin.ROBOT
        return results
    except sqlite3.Error as exc:
        raise StatisticsScopeError("execution_source_unavailable") from exc


def load_order_origins_read_only(
    database_path: str | Path, *, account_id: str,
) -> dict[ExecutionDedupKey, Origin]:
    """Legacy independent read API; snapshot publishers must use shared connection."""
    if not isinstance(account_id, str) or not account_id.strip() or account_id != account_id.strip():
        raise StatisticsScopeError("account_identity_required")
    path = Path(database_path)
    if not path.is_file():
        raise StatisticsScopeError("execution_source_unavailable")
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise StatisticsScopeError("execution_source_unavailable") from exc
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        result = load_order_origins_from_connection(connection, account_id=account_id)
        connection.rollback()
        return result
    finally:
        connection.close()
