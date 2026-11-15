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

        # An owned Box TAKE/partial EXIT is a PAPER LIMIT, not a Robot
        # protection obligation or an ENTRY. Its immutable source candidate
        # ownership can prove the Robot controller only together with the
        # exact handoff and the durable IKIGAI_BOX Robot trade. A name prefix,
        # same-symbol trade, or standalone Box plan is never sufficient.
        box_tables = {
            "paper_limit_orders", "paper_limit_actions",
            "box_order_ownership", "box_attempt_ownership",
            "robot_candidates", "robot_trades",
        }
        if box_tables <= tables and account_id == "paper":
            box_rows = connection.execute(
                """SELECT e.trading_account_id, e.category, e.exec_id
                   FROM executions e
                   JOIN paper_limit_orders p
                     ON p.trading_account_id=e.trading_account_id
                    AND p.order_id=e.order_id AND p.symbol=e.symbol
                    AND p.side=e.side
                   JOIN paper_limit_actions action
                     ON action.order_id=p.order_id AND action.operation='create'
                   JOIN box_order_ownership owned
                     ON owned.trading_account_id=e.trading_account_id
                    AND owned.order_id=e.order_id
                   JOIN box_attempt_ownership baseline
                     ON baseline.trading_account_id=owned.trading_account_id
                    AND baseline.candidate_id=owned.candidate_id
                    AND baseline.symbol=e.symbol
                   JOIN robot_candidates source
                     ON source.candidate_id=baseline.candidate_id
                    AND source.trading_account_id=e.trading_account_id
                    AND source.symbol=e.symbol AND source.status='BOX_PLAN_ONLY'
                   JOIN robot_candidates handoff
                     ON handoff.candidate_id='box-robot-' || substr(source.candidate_id, 10)
                    AND handoff.trading_account_id=e.trading_account_id
                    AND handoff.symbol=e.symbol AND handoff.status!='BOX_PLAN_ONLY'
                    AND json_extract(handoff.signal_snapshot_json,
                                     '$.source_box_candidate_id')=source.candidate_id
                   JOIN robot_trades trade
                     ON trade.candidate_id=handoff.candidate_id
                    AND trade.trading_account_id=e.trading_account_id
                    AND trade.symbol=e.symbol AND trade.pattern='IKIGAI_BOX'
                   WHERE e.trading_account_id=? AND e.category=?
                     AND source.candidate_id LIKE 'box-plan-%'
                     AND json_extract(source.signal_snapshot_json, '$.pattern')='IKIGAI_BOX'
                     AND json_extract(source.signal_snapshot_json, '$.environment')='PAPER'
                     AND json_extract(source.signal_snapshot_json, '$.identity.direction')=trade.direction
                     AND owned.role='EXIT' AND owned.slot BETWEEN 1 AND 4
                     AND ((trade.direction='LONG' AND e.side='Sell')
                       OR (trade.direction='SHORT' AND e.side='Buy'))
                     AND p.created_at_ms<=e.exchange_timestamp_ms
                     AND trade.entry_time_ms<=e.exchange_timestamp_ms
                     AND (trade.exit_time_ms IS NULL
                       OR e.exchange_timestamp_ms<=trade.exit_time_ms)""",
                (account_id, Category.LINEAR.value),
            ).fetchall()
            for box_row in box_rows:
                key = ExecutionDedupKey(
                    TradingAccountId(box_row["trading_account_id"]),
                    Category.LINEAR, ExecutionId(box_row["exec_id"]),
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
