"""READ-ONLY evidence for the *one* JASMY Flat/OPEN legacy PAPER incident.

This is NOT a shutdown permission or a flat_paper_recovery_gate override.
No signal, reconciliation, SQL write, staging, or deployment can result from it.
A separate reviewed lifecycle transition must re-attest all evidence under the
writer barrier immediately before any owner-authorized one-shot handoff.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from types import SimpleNamespace

from terminal.application.robot_breakout_monitor import (
    RobotBreakoutMonitorError, robot_entry_order_ids,
)
from terminal.application.robot_nonrobot_close_proof import prove_nonrobot_robot_close
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_runtime import PaperRuntime
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked, _require

ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("JASMYUSDT")
TRADE_ID = "robot-trade-2a023e646fd8add8b5b30cd8"
CANDIDATE_ID = "2a023e646fd8add8b5b30cd8"
OLD_SHA = "f100ef369a1105443332b5729b558464c27be48f"
PROOF_LABEL = "JASMY_FLAT_ORPHAN_LEDGER_PROVEN_ONLY"


def prove_jasmy_legacy_flat(
    conn: sqlite3.Connection, *, expected_identity: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
):
    """Evaluate all conditions from ONE stable read transaction.

    Requires the *existing* immutable JASMY command/fill proof, in addition
    to account-wide FLAT/quiescence. It does not relax the separate historical
    BUSDT incident gate, or allow an OPEN trade other than this exact one.
    """
    _require(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("database_identity") == expected_identity
        and backend.get("build_sha") == OLD_SHA
        and bool(backend.get("process_instance_id")),
        "jasmy_backend_identity_unproven",
    )
    _require(scanner.get("mode") == "SCANNER_STOPPED", "scanner_not_stopped")
    _require(autopilot.get("mode") == "OFF", "autopilot_not_off")
    _require(
        protection.get("healthy") is True
        and protection.get("unhealthy_symbols") == {},
        "protection_unhealthy",
    )
    # The legacy backend incorrectly presents a stale JASMY Robot ownership
    # as EXPOSURE after the authoritative position became Flat. Never allow
    # genuine exposure or any other stale coverage through this exception.
    coverage = (
        protection.get("covered_symbols"), protection.get("armed_symbols"),
        protection.get("coverage_roles"),
    )
    _require(
        coverage == (["JASMYUSDT"], [], {"JASMYUSDT": "EXPOSURE"})
        or coverage == ([], [], {}),
        "unexpected_protection_coverage",
    )
    _require(conn.execute("PRAGMA quick_check").fetchone() == ("ok",),
             "paper_database_integrity_unproven")
    robot_states = conn.execute(
        "SELECT mode, recovery_status FROM robot_runtime_state "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(
        len(robot_states) == 1
        and tuple(robot_states[0])[0] == "ROBOT_RUNNING"
        and tuple(robot_states[0])[1] in ("PAUSED", "RECONCILIATION_REQUIRED"),
        "robot_admission_not_closed",
    )
    ap_states = conn.execute(
        "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'",
    ).fetchall()
    _require(len(ap_states) == 1 and ap_states[0][0] == "OFF",
             "durable_autopilot_not_off")
    rows = conn.execute(
        "SELECT symbol, side, quantity, sync_state FROM position_projections "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(bool(rows) and any(row[0] == SYMBOL.value for row in rows),
             "jasmy_position_missing")
    from decimal import Decimal, InvalidOperation
    try:
        _require(all(
            bool(symbol) and side == "Flat"
            and Decimal(str(quantity)).is_finite()
            and Decimal(str(quantity)) == 0
            and sync_state == "synced"
            for symbol, side, quantity, sync_state in rows
        ), "paper_position_not_proven_flat")
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FlatRecoveryBlocked("paper_position_evidence_invalid") from exc

    trades = conn.execute(
        "SELECT trade_id, candidate_id, symbol FROM robot_trades "
        "WHERE trading_account_id='paper' AND exit_time_ms IS NULL",
    ).fetchall()
    _require(
        [tuple(row) for row in trades] == [(TRADE_ID, CANDIDATE_ID, SYMBOL.value)],
        "unexpected_open_robot_trade",
    )
    candidates = conn.execute(
        "SELECT candidate_id, symbol, status FROM robot_candidates "
        "WHERE trading_account_id='paper' AND status IN ('OPEN','APPROVED')",
    ).fetchall()
    _require(
        [tuple(row) for row in candidates] == [(CANDIDATE_ID, SYMBOL.value, "OPEN")],
        "unexpected_active_robot_candidate",
    )
    _require(conn.execute(
        "SELECT COUNT(*) FROM paper_limit_orders WHERE trading_account_id='paper' "
        "AND status NOT IN ('filled','cancelled')",
    ).fetchone()[0] == 0, "active_or_unknown_paper_limit")
    _require(conn.execute(
        "SELECT COUNT(*) FROM trading_commands WHERE trading_account_id='paper' "
        "AND current_state NOT IN "
        "('filled','cancelled','amended','rejected','failed','owner_attested_closed')",
    ).fetchone()[0] == 0, "unfinished_or_unknown_trading_command")
    _require(conn.execute(
        "SELECT COUNT(*) FROM paper_protection_obligations "
        "WHERE trading_account_id='paper' AND status!='RESOLVED'",
    ).fetchone()[0] == 0, "unresolved_protection_obligation")
    _require(conn.execute(
        "SELECT COUNT(*) FROM reconciliation_checkpoints "
        "WHERE trading_account_id='paper' AND completed_at_ms IS NULL",
    ).fetchone()[0] == 0, "unresolved_reconciliation_checkpoint")

    # Construct a read-only adapter directly over the already-open SQLite
    # snapshot. SQLiteStore.open() is FORBIDDEN: it may migrate or add indexes.
    store = SQLiteStore(conn, Path("/read-only-snapshot"), 5000)
    trade = store.get_robot_trade(TRADE_ID)
    candidate = store.get_robot_candidate(CANDIDATE_ID)
    position = store.get_position_projection(PositionKey(
        ACCOUNT, Category.LINEAR, SYMBOL, 0,
    ))
    _require(
        trade is not None and candidate is not None and position is not None
        and trade.trading_account_id == ACCOUNT and trade.symbol == SYMBOL
        and candidate.trading_account_id == ACCOUNT
        and candidate.status == "OPEN"
        and position.side is PositionSide.FLAT
        and trade.entry_path in ("LIMIT", "MARKET"),
        "jasmy_ownership_unproven",
    )
    try:
        entry_ids = robot_entry_order_ids(
            store, ACCOUNT, candidate,
            (candidate.robot_state or {}).get("execution") or {},
            entry_path=trade.entry_path,
        )
    except (RobotBreakoutMonitorError, ValueError) as exc:
        raise FlatRecoveryBlocked("jasmy_entry_identity_invalid") from exc
    _require(bool(entry_ids), "jasmy_entry_identity_missing")
    fills = store.load_executions_for_symbol(ACCOUNT, SYMBOL)
    _require(bool(fills), "jasmy_execution_missing")
    close_order = fills[-1].order_id.value
    _require(close_order.startswith("paper-order-tw_"),
             "jasmy_close_order_identity_invalid")
    command = store.get_paper_command_by_order_link(
        ACCOUNT, close_order.removeprefix("paper-order-"),
    )
    fees = PaperRuntime._robot_entry_fees(SimpleNamespace(store=store), trade)
    proof = prove_nonrobot_robot_close(
        trade=trade, candidate=candidate, position=position,
        executions=fills, command=command,
        entry_order_ids=tuple(item.value for item in entry_ids),
        entry_fees=fees, unique_open_owner=True, has_competing_work=False,
    )
    _require(proof is not None, "jasmy_immutable_close_proof_missing")
    return PROOF_LABEL


def inspect_read_only(
    db_path: Path, *, expected_identity: str, snapshots: dict,
) -> str:
    """For isolated review/preflight only; never interact with a running owner."""
    _require(db_path.is_file(), "paper_database_missing")
    try:
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            return prove_jasmy_legacy_flat(
                conn, expected_identity=expected_identity, **snapshots,
            )
    except sqlite3.Error as exc:
        raise FlatRecoveryBlocked("paper_database_evidence_unreadable") from exc
