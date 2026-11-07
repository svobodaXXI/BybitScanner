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
    # The old backend cannot retire temporary entry arms while reconciliation
    # is REQUIRED. Accept *only* the incident-specific, independently proven
    # non-exposure subscriptions, not arbitrary active protection.
    _require(
        protection.get("healthy") is True
        and protection.get("unhealthy_symbols") == {},
        "protection_unhealthy",
    )
    covered = protection.get("covered_symbols")
    armed = protection.get("armed_symbols")
    roles = protection.get("coverage_roles", {})
    _require(
        isinstance(covered, (list, tuple))
        and isinstance(armed, (list, tuple))
        and isinstance(roles, dict),
        "protection_coverage_unproven",
    )
    strictly_quiescent = covered == [] and armed == [] and roles == {}
    known_incident_coverage = (
        len(covered) == 3
        and set(covered) == {"BUSDT", "AUSDT", "KMNOUSDT"}
        and len(armed) == 2
        and set(armed) == {"AUSDT", "KMNOUSDT"}
        and roles == {
            "BUSDT": "OBLIGATION",
            "AUSDT": "ENTRY_PENDING",
            "KMNOUSDT": "ENTRY_PENDING",
        }
    )
    _require(
        strictly_quiescent or known_incident_coverage,
        "unexpected_or_unsafe_protection_coverage",
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
        "SELECT symbol, side, quantity, sync_state FROM position_projections "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    for symbol, side, raw_quantity, sync_state in positions:
        try:
            quantity = Decimal(str(raw_quantity))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FlatRecoveryBlocked("invalid_paper_position_quantity") from exc
        _require(
            bool(symbol) and side == "Flat" and quantity.is_finite()
            and quantity == 0 and sync_state in ("synced", "synchronized"),
            "paper_position_not_proven_flat",
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
            "WHERE trading_account_id='paper' AND (status IS NULL OR status NOT IN ('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))",
        ).fetchone()[0] == 0,
        "open_robot_candidate",
    )
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM paper_limit_orders "
            "WHERE trading_account_id='paper' AND (status IS NULL OR status NOT IN ('filled','cancelled'))",
        ).fetchone()[0] == 0,
        "active_or_unknown_paper_limit",
    )
    placeholders = ",".join("?" for _ in _TERMINAL_COMMANDS)
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM trading_commands WHERE trading_account_id='paper' "
            f"AND (current_state IS NULL OR current_state NOT IN ({placeholders}))",
            _TERMINAL_COMMANDS,
        ).fetchone()[0] == 0,
        "unfinished_or_unknown_trading_command",
    )

    # An interrupted reconciliation can still own pending PAPER work even
    # when positions, LIMITs and commands appear terminal. Preserve the same
    # account-scoped checkpoint fence used by canonical shutdown/JASMY proof.
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM reconciliation_checkpoints "
            "WHERE trading_account_id='paper' AND completed_at_ms IS NULL",
        ).fetchone()[0] == 0,
        "unfinished_reconciliation_checkpoint",
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
        "WHERE o.trading_account_id='paper' AND (o.status IS NULL OR o.status!='RESOLVED')",
    ).fetchall()
    _require(len(obligations) == 1, "unexpected_unresolved_obligations")
    (symbol, trade_id, leg, status, order_id, exec_id, observed_quantity,
     pattern, reason, exit_time, exit_price, execution_order, execution_symbol,
     executed_qty, execution_time, execution_price, execution_side) = obligations[0]
    # Decimal equality alone can accept matching infinities; malformed
    # values must fail as evidence, not escape as a numeric exception.
    try:
        observed = Decimal(str(observed_quantity))
        executed = Decimal(str(executed_qty))
        trade_exit = Decimal(str(exit_price))
        fill_exit = Decimal(str(execution_price))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FlatRecoveryBlocked("busdt_historical_stop_evidence_unproven") from exc
    _require(
        symbol == "BUSDT" and bool(trade_id) and leg == "STOP"
        and status == "DISPATCHING" and bool(order_id) and bool(exec_id)
        and pattern == "IKIGAI_BOX" and reason == "TAKE"
        and exit_time is not None and exit_time == execution_time
        and order_id == execution_order and symbol == execution_symbol
        and execution_side == "Sell"
        and all(value.is_finite() and value > 0 for value in (
            observed, executed, trade_exit, fill_exit,
        ))
        and observed == executed and trade_exit == fill_exit,
        "busdt_historical_stop_evidence_unproven",
    )
    if known_incident_coverage:
        # An APPROVED but not yet OPEN candidate on an armed symbol could still
        # be awaiting its entry submission. Do not treat this as a stale arm.
        _require(
            conn.execute(
                "SELECT COUNT(*) FROM robot_candidates "
                "WHERE trading_account_id='paper' "
                "AND symbol IN ('AUSDT', 'KMNOUSDT') "
                "AND status IN ('APPROVED','OPEN')",
            ).fetchone()[0] == 0,
            "armed_entry_candidate_still_owned",
        )
        # No other unresolved obligation, open Robot trade/candidate, working
        # limit or unsettled command passed above. The BUSDT subscription is
        # only for this exact historical STOP; entry arms have no durable work.
        _require(
            symbol == "BUSDT" and status == "DISPATCHING",
            "incident_obligation_proof_missing",
        )
    for required_symbol in ("BUSDT", "VIRTUALUSDT"):
        _require(
            any(row[0] == required_symbol and row[1] == "Flat" for row in positions),
            "required_flat_projection_missing",
        )
    return "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY"



def _prove_one_orphan_protection(protection: dict, symbol: str) -> None:
    """Only a stranded Flat/OPEN owner's isolated, drained monitor may remain.

    Called after the durable FLAT, order and ownership checks. A disconnected
    PAPER market-data monitor is not evidence of exposure, but cannot waive
    any armed order, other symbol's fault or pending ingress.
    """
    covered, armed = protection.get("covered_symbols"), protection.get("armed_symbols")
    roles, unhealthy = protection.get("coverage_roles"), protection.get("unhealthy_symbols")
    _require(isinstance(covered, (list, tuple))
             and isinstance(armed, (list, tuple)) and isinstance(roles, dict)
             and isinstance(unhealthy, dict) and not armed,
             "one_orphan_protection_shape_unknown")
    if protection.get("healthy") is True:
        _require(unhealthy == {} and not covered and roles == {},
                 "one_orphan_protection_not_quiescent")
        return
    reason = unhealthy.get(symbol)
    _require(
        protection.get("healthy") is False
        and covered == [symbol] and roles == {symbol: "EXPOSURE"}
        and unhealthy == {symbol: reason}
        and reason in ("ingress_overflow",
                       "websocket_disconnect:WebSocketConnectionClosedException"),
        "one_orphan_unrelated_protection_failure",
    )
    ingress = protection.get("ingress")
    _require(
        isinstance(ingress, dict) and ingress.get("current_pending") == 0,
        "one_orphan_protection_ingress_not_drained",
    )


def prove_one_flat_orphan(
    conn: sqlite3.Connection, *, expected_identity: str, expected_build_sha: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
) -> str:
    """Fail-closed, read-only proof of ONE previously executed manual Robot close.

    This is neither a Robot ledger mutation nor permission to stop a process.
    The caller must freeze admission and independently pin its release, DB,
    process identity and listener before an explicitly authorized handoff.
    There are no symbol/clock/incident-specific exceptions.
    """
    from decimal import InvalidOperation
    from types import SimpleNamespace
    from terminal.application.robot_breakout_monitor import (
        RobotBreakoutMonitorError, robot_entry_order_ids,
    )
    from terminal.application.robot_nonrobot_close_proof import prove_nonrobot_robot_close
    from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
    from terminal.persistence.sqlite_store import SQLiteStore
    from terminal.runtime.paper_runtime import PaperRuntime

    account = TradingAccountId("paper")
    _require(conn.in_transaction and tuple(conn.execute("PRAGMA query_only").fetchone()) == (1,),
             "one_orphan_requires_readonly_snapshot")
    _require(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("database_identity") == expected_identity
        and backend.get("build_sha") == expected_build_sha
        and isinstance(backend.get("process_instance_id"), str)
        and bool(backend["process_instance_id"].strip()),
        "one_orphan_backend_identity_unproven",
    )
    _require(scanner.get("mode") == "SCANNER_STOPPED"
             and scanner.get("worker_quiescent") is not False,
             "one_orphan_scanner_not_quiescent")
    _require(autopilot.get("mode") == "OFF", "one_orphan_autopilot_not_off")
    _require(tuple(conn.execute("PRAGMA quick_check").fetchone()) == ("ok",),
             "one_orphan_database_not_integral")
    scanner_rows = conn.execute(
        "SELECT mode FROM scanner_runtime_state WHERE trading_account_id='paper'"
    ).fetchall()
    _require(
        len(scanner_rows) == 1 and tuple(scanner_rows[0]) == ("SCANNER_STOPPED",),
        "one_orphan_durable_scanner_not_frozen",
    )
    autopilot_rows = conn.execute(
        "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'"
    ).fetchall()
    _require(
        len(autopilot_rows) == 1 and tuple(autopilot_rows[0]) == ("OFF",),
        "one_orphan_durable_autopilot_not_off",
    )
    state = conn.execute(
        "SELECT mode,recovery_status,reason FROM robot_runtime_state "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(len(state) == 1 and state[0][0] == "ROBOT_RUNNING",
             "one_orphan_robot_mode_changed")
    _, recovery, reason = state[0]
    _require(
        recovery in ("PAUSED", "RECONCILIATION_REQUIRED"),
        "one_orphan_unrecognized_recovery_state",
    )

    positions = conn.execute(
        "SELECT symbol,side,quantity,sync_state FROM position_projections "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(bool(positions), "one_orphan_positions_missing")
    for symbol, side, raw, sync in positions:
        try:
            quantity = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise FlatRecoveryBlocked("one_orphan_invalid_position_quantity") from exc
        _require(isinstance(symbol, str) and bool(symbol)
                 and side == "Flat" and quantity.is_finite() and quantity == 0
                 and sync in ("synced", "synchronized"),
                 "one_orphan_exposure_or_unsynced_position")

    rows = conn.execute(
        "SELECT trade_id,candidate_id,symbol FROM robot_trades "
        "WHERE trading_account_id='paper' AND exit_time_ms IS NULL",
    ).fetchall()
    _require(len(rows) == 1, "one_orphan_requires_exactly_one_trade")
    trade_id, candidate_id, symbol = rows[0]
    # Canonical reconcile changes the durable reason after a proven failure.
    # Its post-failure message must name THIS exact still-OPEN trade; do not
    # mistake another fault for permission to retire this owner.
    _require(
        recovery == "PAUSED"
        or (
            isinstance(reason, str)
            and (
                (reason.startswith("ROBOT_PROTECTION_COVERAGE_LOST symbol=")
                 and reason.endswith(" reason=ingress_overflow"))
                or reason == (
                    "reconcile_robot cannot prove Robot ownership/protection for: "
                    + str(trade_id)
                )
            )
        ),
        "one_orphan_unrecognized_recovery_reason",
    )
    _require(
        sum(position_symbol == symbol for position_symbol, *_ in positions) == 1
        and isinstance(trade_id, str) and bool(trade_id)
        and isinstance(candidate_id, str) and bool(candidate_id),
        "one_orphan_ownership_ambiguous",
    )
    active = conn.execute(
        "SELECT candidate_id,symbol,status,approved_at_ms FROM robot_candidates "
        "WHERE trading_account_id='paper' "
        "AND (status IS NULL OR status NOT IN "
        "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))",
    ).fetchall()
    open_rows = [row for row in active if row[2] == "OPEN"]
    _require(len(open_rows) == 1 and open_rows[0][:3] == (candidate_id,symbol,"OPEN"),
             "one_orphan_competing_open_candidate")
    for cid, approved_symbol, status, approved in active:
        if status == "OPEN":
            continue
        _require(status == "APPROVED" and type(approved) is int and approved > 0
                 and bool(cid) and bool(approved_symbol),
                 "one_orphan_approval_identity_unproven")
        for table, condition in (
            ("executions", "exchange_timestamp_ms IS NULL OR exchange_timestamp_ms >= ?"),
            ("paper_limit_orders", "created_at_ms IS NULL OR "
             "(created_at_ms >= ? AND (status IS NULL OR status != 'cancelled'))"),
            ("trading_commands", "created_at_ms IS NULL OR "
             "(created_at_ms >= ? AND (current_state IS NULL OR "
             "current_state NOT IN ('cancelled','rejected','failed','amended')))"),
        ):
            _require(
                conn.execute(
                    f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                    f"AND symbol=? AND ({condition}) LIMIT 1", (approved_symbol,approved),
                ).fetchone() is None,
                "one_orphan_approval_may_enter",
            )
        _require(
            conn.execute(
                "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
                "AND candidate_id=? LIMIT 1", (cid,),
            ).fetchone() is None,
            "one_orphan_approval_has_trade",
        )

    for table, condition in (
        ("paper_limit_orders", "status IS NULL OR status NOT IN ('filled','cancelled')"),
        ("trading_commands", "current_state IS NULL OR current_state NOT IN "
         "('filled','cancelled','amended','rejected','failed','owner_attested_closed')"),
        ("paper_protection_obligations", "status IS NULL OR status != 'RESOLVED'"),
        ("reconciliation_checkpoints", "completed_at_ms IS NULL"),
    ):
        _require(
            conn.execute(
                f"SELECT 1 FROM {table} WHERE trading_account_id='paper' "
                f"AND ({condition}) LIMIT 1",
            ).fetchone() is None, "one_orphan_unfinished_" + table,
        )

    _prove_one_orphan_protection(protection, symbol)

    # Use the SAME immutable ownership/fill predicate as canonical reconcile.
    # No SQL UPDATE, fake exit attribution, Market order or REST mutation.
    conn.row_factory = sqlite3.Row
    store = SQLiteStore(conn, Path("/read-only-snapshot"), 5000)
    trade = store.get_robot_trade(trade_id)
    candidate = store.get_robot_candidate(candidate_id)
    position = store.get_position_projection(
        PositionKey(account, Category.LINEAR, Symbol(symbol), 0),
    )
    _require(
        trade is not None and candidate is not None and position is not None
        and trade.trading_account_id == account and trade.trade_id == trade_id
        and trade.candidate_id == candidate_id and trade.symbol == Symbol(symbol)
        and candidate.trading_account_id == account and candidate.candidate_id == candidate_id
        and candidate.status == "OPEN" and candidate.symbol == Symbol(symbol)
        and position.side is PositionSide.FLAT and position.quantity.value == 0,
        "one_orphan_immutable_owner_missing",
    )
    try:
        entry_ids = robot_entry_order_ids(
            store, account, candidate, (candidate.robot_state or {}).get("execution") or {},
            entry_path=trade.entry_path,
        )
    except (RobotBreakoutMonitorError, ValueError) as exc:
        raise FlatRecoveryBlocked("one_orphan_entry_identity_unproven") from exc
    _require(bool(entry_ids), "one_orphan_entry_fill_missing")
    fills = store.load_executions_for_symbol(account, Symbol(symbol))
    _require(bool(fills) and fills[-1].order_id.value.startswith("paper-order-tw_"),
             "one_orphan_close_execution_missing")
    command = store.get_paper_command_by_order_link(
        account, fills[-1].order_id.value.removeprefix("paper-order-"),
    )
    fees = PaperRuntime._robot_entry_fees(SimpleNamespace(store=store), trade)
    evidence = prove_nonrobot_robot_close(
        trade=trade, candidate=candidate, position=position,
        executions=fills, command=command,
        entry_order_ids=tuple(item.value for item in entry_ids),
        entry_fees=fees, unique_open_owner=True, has_competing_work=False,
    )
    _require(evidence is not None, "one_orphan_manual_close_proof_missing")
    return "ONE_FLAT_ORPHAN_IMMUTABLE_CLOSE_EVIDENCE_ONLY"


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
