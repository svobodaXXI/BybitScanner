"""READ-ONLY evidence gate for exceptional FLAT PAPER recovery.

This does NOT stop/restart a backend, resolve obligations, waive the canonical
safe-stop, or authorize a process signal. It is the independently testable
precondition for a separately approved shutdown transition. Unknown evidence
fails closed; keep the existing backend alive.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3

from tools.runtime_intent import expected_database_identity, http_get
from tools.stop_robot_runtime import _database_path, _environment


class FlatRecoveryBlocked(RuntimeError):
    pass


_TERMINAL_COMMANDS = (
    "filled", "cancelled", "amended", "rejected", "failed", "owner_attested_closed",
)


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise FlatRecoveryBlocked(reason)


def _singleton(conn: sqlite3.Connection, query: str) -> tuple:
    rows = conn.execute(query).fetchall()
    _require(len(rows) == 1, "missing_or_ambiguous_paper_state")
    return tuple(rows[0])


def prove_flat_recovery(
    conn: sqlite3.Connection, *, expected_identity: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
) -> str:
    """Inspect one SQLite transaction and independently supplied API snapshots.

    Caller must hold a snapshot transaction. This evidence is a *preflight*
    only; an authorization and a separate atomic shutdown design are required.
    """
    _require(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("database_identity") == expected_identity,
        "paper_backend_identity_or_mode_unproven",
    )
    _require(
        scanner.get("mode") == "SCANNER_STOPPED",
        "scanner_not_stopped",
    )
    _require(
        autopilot.get("mode") == "OFF",
        "autopilot_not_off",
    )
    _require(
        protection.get("healthy") is True
        and protection.get("covered_symbols") == []
        and protection.get("armed_symbols") == []
        and protection.get("unhealthy_symbols") == {},
        "protection_not_quiescent",
    )
    _require(
        conn.execute("PRAGMA integrity_check").fetchone() == ("ok",),
        "database_integrity_unproven",
    )
    _require(
        _singleton(
            conn, "SELECT mode, recovery_status FROM robot_runtime_state "
                  "WHERE trading_account_id='paper'",
        ) == ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        "unexpected_robot_state",
    )
    _require(
        _singleton(
            conn, "SELECT mode FROM robot_autopilot_state "
                  "WHERE trading_account_id='paper'",
        ) == ("OFF",),
        "durable_autopilot_not_off",
    )
    positions = conn.execute(
        "SELECT symbol, side, quantity FROM position_projections "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    for symbol, side, raw_quantity in positions:
        try:
            quantity = Decimal(str(raw_quantity))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FlatRecoveryBlocked("invalid_paper_position_quantity") from exc
        _require(
            bool(symbol) and side == "Flat" and quantity.is_finite()
            and quantity == 0, "paper_position_not_proven_flat",
        )
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM robot_trades "
            "WHERE trading_account_id='paper' AND exit_time_ms IS NULL",
        ).fetchone()[0] == 0,
        "open_robot_trade",
    )
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM robot_candidates "
            "WHERE trading_account_id='paper' AND status='OPEN'",
        ).fetchone()[0] == 0,
        "open_robot_candidate",
    )
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM paper_limit_orders "
            "WHERE trading_account_id='paper' AND status NOT IN ('filled','cancelled')",
        ).fetchone()[0] == 0,
        "active_or_unknown_paper_limit",
    )
    placeholders = ",".join("?" for _ in _TERMINAL_COMMANDS)
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM trading_commands WHERE trading_account_id='paper' "
            f"AND current_state NOT IN ({placeholders})",
            _TERMINAL_COMMANDS,
        ).fetchone()[0] == 0,
        "unfinished_or_unknown_trading_command",
    )

    obligations = conn.execute(
        "SELECT o.symbol, o.trade_id, o.winning_leg, o.status, o.order_id, "
        "o.exec_id, o.observed_quantity, t.pattern, t.exit_reason, "
        "t.exit_time_ms, t.exit_price, e.order_id, e.symbol, e.quantity, "
        "e.exchange_timestamp_ms, e.price, e.side "
        "FROM paper_protection_obligations o "
        "LEFT JOIN robot_trades t ON t.trade_id=o.trade_id "
        " AND t.trading_account_id=o.trading_account_id AND t.symbol=o.symbol "
        "LEFT JOIN executions e ON e.trading_account_id=o.trading_account_id "
        " AND e.category='linear' AND e.exec_id=o.exec_id "
        "WHERE o.trading_account_id='paper' AND o.status!='RESOLVED'",
    ).fetchall()
    _require(len(obligations) == 1, "unexpected_unresolved_obligations")
    (symbol, trade_id, leg, status, order_id, exec_id, observed_quantity,
     pattern, reason, exit_time, exit_price, execution_order, execution_symbol,
     executed_qty, execution_time, execution_price, execution_side) = obligations[0]
    _require(
        symbol == "BUSDT" and bool(trade_id) and leg == "STOP"
        and status == "DISPATCHING" and bool(order_id) and bool(exec_id)
        and pattern == "IKIGAI_BOX" and reason == "TAKE"
        and exit_time is not None and exit_time == execution_time
        and order_id == execution_order and symbol == execution_symbol
        and execution_side == "Sell"
        and Decimal(str(observed_quantity)) == Decimal(str(executed_qty))
        and Decimal(str(exit_price)) == Decimal(str(execution_price)),
        "busdt_historical_stop_evidence_unproven",
    )
    for required_symbol in ("BUSDT", "VIRTUALUSDT"):
        _require(
            any(row[0] == required_symbol and row[1] == "Flat" for row in positions),
            "required_flat_projection_missing",
        )
    return "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY"


def inspect_live(db_path: Path, *, root: Path, env: dict) -> str:
    """Read API and SQLite evidence. No mutation or process control."""
    base = "http://127.0.0.1:8765"
    paths = {
        "backend": "/api/health",
        "scanner": "/api/scanner/status",
        "autopilot": "/api/robot/autopilot",
        "protection": "/api/robot/protection-health",
    }
    snapshots = {}
    for name, route in paths.items():
        response = http_get(base + route, 5)
        _require(response.status == 200, name + "_api_unavailable")
        body = response.json()
        _require(isinstance(body, dict), name + "_api_invalid")
        snapshots[name] = body
    _require(db_path.is_file(), "paper_database_missing")
    try:
        # URI mode=ro: this tool never creates, migrates or modifies PAPER DB.
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.execute("BEGIN")
            return prove_flat_recovery(
                conn, expected_identity=expected_database_identity(root, env),
                **snapshots,
            )
    except sqlite3.Error as exc:
        raise FlatRecoveryBlocked("database_evidence_unreadable") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PAPER FLAT recovery read-only gate")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    args = parser.parse_args(argv)
    root = Path("/opt/BybitScanner")
    env = _environment(args.env_file)
    try:
        print(inspect_live(_database_path(root, env), root=root, env=env))
        print("No shutdown or deployment authorized; backend remains running.")
        return 0
    except (FlatRecoveryBlocked, OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}; backend retained")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
