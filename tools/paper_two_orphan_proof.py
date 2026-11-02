"""Read-only preflight evidence for exactly two legacy PAPER Flat/OPEN Robot lots.

Not a canonical coordinator, shutdown exception, lifecycle repair, trade close,
or permission to deploy. In particular, this NEVER broadens the incident-scoped
JASMY-only SIGINT path. Every missing/ambiguous fill blocks the transition.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace

from terminal.application.robot_breakout_monitor import (
    RobotBreakoutMonitorError, robot_entry_order_ids,
)
from terminal.application.robot_nonrobot_close_proof import prove_nonrobot_robot_close
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_runtime import PaperRuntime
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked, _require
from tools.jasmy_flat_handoff_proof import OLD_SHA as INCIDENT_BACKEND_SHA

ACCOUNT = TradingAccountId("paper")
EXPECTED_SYMBOLS = frozenset({"JASMYUSDT", "FLOWUSDT"})
PROOF_LABEL = "TWO_ORPHANS_IMMUTABLE_CLOSE_EVIDENCE_ONLY"


def prove_two_flat_orphans(
    conn: sqlite3.Connection, *, expected_identity: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
) -> str:
    """Read one stable SQLite snapshot; never call HTTP, migrate or write.

    Requires a separately frozen ingress and a uniquely attributable manual
    closing execution for EACH Robot lot. No other OPEN or APPROVED owner is
    allowed. Passing this preflight does not release the canonical stop fence.
    """
    _require(
        backend.get("ok") is True
        and backend.get("component") == "paper_backend"
        and backend.get("mode") == "paper"
        and backend.get("paper_live_safe") is True
        and backend.get("database_identity") == expected_identity
        and backend.get("build_sha") == INCIDENT_BACKEND_SHA
        and bool(backend.get("process_instance_id")),
        "paper_backend_identity_unproven",
    )
    _require(scanner.get("mode") == "SCANNER_STOPPED", "scanner_not_stopped")
    _require(autopilot.get("mode") == "OFF", "autopilot_not_off")
    _require(
        protection.get("healthy") is True
        and protection.get("unhealthy_symbols") == {},
        "protection_unhealthy",
    )
    covered = protection.get("covered_symbols")
    armed = protection.get("armed_symbols")
    roles = protection.get("coverage_roles")
    _require(
        isinstance(covered, list) and isinstance(armed, list)
        and isinstance(roles, dict) and not armed
        and (
            (covered == [] and roles == {})
            or (len(covered) == 2 and set(covered) == EXPECTED_SYMBOLS
                and roles == {symbol: "EXPOSURE" for symbol in EXPECTED_SYMBOLS})
        ),
        "unexpected_protection_coverage",
    )
    _require(conn.execute("PRAGMA quick_check").fetchone() == ("ok",),
             "paper_database_integrity_unproven")
    state = conn.execute(
        "SELECT mode, recovery_status FROM robot_runtime_state "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(
        len(state) == 1 and tuple(state[0])[0] == "ROBOT_RUNNING"
        and tuple(state[0])[1] in ("PAUSED", "RECONCILIATION_REQUIRED"),
        "robot_admission_not_frozen",
    )
    durable_auto = conn.execute(
        "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'",
    ).fetchall()
    _require(len(durable_auto) == 1 and durable_auto[0][0] == "OFF",
             "durable_autopilot_not_off")
    positions = conn.execute(
        "SELECT symbol, side, quantity, sync_state FROM position_projections "
        "WHERE trading_account_id='paper'",
    ).fetchall()
    _require(bool(positions), "paper_positions_missing")
    # A second projection for either orphan symbol could conceal an alternate
    # position owner even if both rows say Flat. Do not guess which is canonical.
    for orphan_symbol in EXPECTED_SYMBOLS:
        _require(
            sum(symbol == orphan_symbol for symbol, *_ in positions) == 1,
            "ambiguous_orphan_position_projection",
        )
    for symbol, side, raw, sync in positions:
        try:
            quantity = Decimal(str(raw))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise FlatRecoveryBlocked("invalid_paper_position") from exc
        _require(
            bool(symbol) and side == "Flat" and quantity.is_finite()
            and quantity == 0 and sync in ("synced", "synchronized"),
            "paper_position_not_proven_flat",
        )
    rows = conn.execute(
        "SELECT trade_id, candidate_id, symbol FROM robot_trades "
        "WHERE trading_account_id='paper' AND exit_time_ms IS NULL",
    ).fetchall()
    _require(
        len(rows) == 2 and len({row[0] for row in rows}) == 2
        and len({row[1] for row in rows}) == 2
        and {row[2] for row in rows} == EXPECTED_SYMBOLS,
        "unexpected_open_robot_owners",
    )
    candidates = conn.execute(
        "SELECT candidate_id, symbol, status FROM robot_candidates "
        "WHERE trading_account_id='paper' "
        "AND (status IS NULL OR status NOT IN "
        "('BOX_PLAN_ONLY','CLOSED','EXPIRED','INVALIDATED'))",
    ).fetchall()
    _require(
        len(candidates) == 2
        and {(row[0], row[1], row[2]) for row in candidates}
        == {(row[1], row[2], "OPEN") for row in rows},
        "unexpected_active_robot_candidate",
    )
    for table, condition, reason in (
        ("paper_limit_orders", "(status IS NULL OR status NOT IN ('filled','cancelled'))",
         "active_or_unknown_paper_limit"),
        ("trading_commands", "(current_state IS NULL OR current_state NOT IN "
         "('filled','cancelled','amended','rejected','failed','owner_attested_closed'))",
         "unfinished_or_unknown_trading_command"),
        ("paper_protection_obligations", "(status IS NULL OR status!='RESOLVED')",
         "unresolved_protection_obligation"),
        ("reconciliation_checkpoints", "completed_at_ms IS NULL",
         "unresolved_reconciliation_checkpoint"),
    ):
        count = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE trading_account_id='paper' AND {condition}",
        ).fetchone()[0]
        _require(count == 0, reason)

    # Direct adapter over the existing read-only transaction, not SQLiteStore.open
    # (which may migrate). Any missing ownership proof fails closed.
    store = SQLiteStore(conn, Path("/read-only-snapshot"), 5000)
    for trade_id, candidate_id, symbol_text in rows:
        symbol = Symbol(symbol_text)
        trade = store.get_robot_trade(trade_id)
        candidate = store.get_robot_candidate(candidate_id)
        position = store.get_position_projection(
            PositionKey(ACCOUNT, Category.LINEAR, symbol, 0),
        )
        _require(
            trade is not None and candidate is not None and position is not None
            and trade.trading_account_id == ACCOUNT
            and candidate.trading_account_id == ACCOUNT
            and trade.trade_id == trade_id
            and trade.candidate_id == candidate_id
            and trade.symbol == symbol
            and candidate.candidate_id == candidate_id
            and candidate.symbol == symbol
            and candidate.status == "OPEN"
            and position.side is PositionSide.FLAT
            and trade.entry_path in ("LIMIT", "MARKET"),
            "orphan_lot_identity_unproven",
        )
        try:
            entry_ids = robot_entry_order_ids(
                store, ACCOUNT, candidate,
                (candidate.robot_state or {}).get("execution") or {},
                entry_path=trade.entry_path,
            )
        except (RobotBreakoutMonitorError, ValueError) as exc:
            raise FlatRecoveryBlocked("orphan_entry_identity_invalid") from exc
        _require(bool(entry_ids), "orphan_entry_identity_missing")
        fills = store.load_executions_for_symbol(ACCOUNT, symbol)
        _require(bool(fills), "orphan_execution_missing")
        close_id = fills[-1].order_id.value
        _require(close_id.startswith("paper-order-tw_"),
                 "orphan_close_order_identity_invalid")
        command = store.get_paper_command_by_order_link(
            ACCOUNT, close_id.removeprefix("paper-order-"),
        )
        fees = PaperRuntime._robot_entry_fees(SimpleNamespace(store=store), trade)
        evidence = prove_nonrobot_robot_close(
            trade=trade, candidate=candidate, position=position,
            executions=fills, command=command,
            entry_order_ids=tuple(item.value for item in entry_ids),
            entry_fees=fees, unique_open_owner=True, has_competing_work=False,
        )
        _require(evidence is not None, "orphan_immutable_close_proof_missing")
    return PROOF_LABEL
