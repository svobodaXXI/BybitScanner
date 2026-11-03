"""Exact read-only evidence for the six historical PAPER idle approvals.

Shared by legacy protected handoff and post-Gitless EDITOR_ONLY reconciliation.
This never opens/migrates/writes the real PAPER database or authorizes START.
"""

import json
from decimal import Decimal, InvalidOperation

from tools.flat_paper_recovery_gate import _require

# Observed historical JASMY Robot candidate; never match by symbol alone.
JASMY_CANDIDATE_ID = "2a023e646fd8add8b5b30cd8"
JASMY_TRADE_ID = "robot-trade-2a023e646fd8add8b5b30cd8"

IDLE_APPROVALS = {
    "1000FLOKIUSDT": ("box-robot-aa55", "af8c6"),
    "BNCUSDT": ("589fc4625b687906eb778630", ""),
    "HEMIUSDT": ("box-robot-feaa", "24c43"),
    "INUSDT": ("box-robot-9631", "e84e8"),
    "PLAYSOUTUSDT": ("b4a30317bc2b6fa3777711c3", ""),
    "RUNEUSDT": ("box-robot-358e", "4dd3b"),
}

# Only the six rows observed in the 2026-11-03 read-only VPS forensic
# snapshot may carry historical candidate progress. Their presence is not
# evidence of a fill: every associated entry order/command/execution is
# checked independently below. Unknown revisions/phases stay BLOCKED.
_INCIDENT_ADVANCED_APPROVALS = {
    "1000FLOKIUSDT": (6, "BOX_ENTRY_READY"),
    "BNCUSDT": (6, "RETEST_DETECTED"),
    "HEMIUSDT": (6, "BOX_ENTRY_READY"),
    "INUSDT": (6, "BOX_ENTRY_READY"),
    "PLAYSOUTUSDT": (4, "RETEST_DETECTED"),
    "RUNEUSDT": (3, "BOX_ENTRY_READY"),
}


def _zero_filled(value: object) -> bool:
    try:
        number = Decimal(str(value))
        return number.is_finite() and number == 0
    except (InvalidOperation, TypeError, ValueError):
        return False


def _historical_approval_progress(conn, *, candidate_id: str, symbol: str,
                                  revision: int, raw_state: str,
                                  blocked_reasons: list[str] | None = None) -> bool:
    """Report only a bounded invariant code; never log state JSON or owner IDs."""
    def blocked(reason: str) -> bool:
        if blocked_reasons is not None:
            blocked_reasons.append(reason)
        return False

    expected_revision, expected_phase = _INCIDENT_ADVANCED_APPROVALS[symbol]
    if revision != expected_revision or not isinstance(raw_state, str):
        return blocked("revision_or_state_type_mismatch")
    try:
        state = json.loads(raw_state)
    except (ValueError, TypeError):
        return blocked("state_json_invalid")
    if not isinstance(state, dict) or state.get("phase") != expected_phase:
        return blocked("state_phase_mismatch")
    # A Box's source plan and its order-reservation ledger are NOT the Robot
    # candidate ID. Check all source-owned order identities too; an unissued
    # reservation is not a fill, but any executed/foreign/exit identity blocks.
    if expected_phase == "BOX_ENTRY_READY":
        source = state.get("source_box_candidate_id")
        if (not isinstance(source, str) or not source.startswith("box-plan-")
                or candidate_id != "box-robot-" + source.removeprefix("box-plan-")):
            return blocked("box_source_candidate_identity_mismatch")
        reservations = conn.execute(
            "SELECT order_id, role FROM box_order_ownership "
            "WHERE trading_account_id='paper' AND candidate_id=?", (source,),
        ).fetchall()
        for order_id, role in reservations:
            if not isinstance(order_id, str) or not order_id or role != "ENTRY":
                return blocked("box_reservation_role_or_id_mismatch")
            if conn.execute(
                "SELECT 1 FROM executions WHERE trading_account_id='paper' "
                "AND order_id=? LIMIT 1", (order_id,),
            ).fetchone() is not None:
                return blocked("box_reserved_order_has_execution")
            if conn.execute(
                "SELECT 1 FROM trading_commands WHERE trading_account_id='paper' "
                "AND (exchange_order_id=? OR order_link_id=?) LIMIT 1",
                (order_id, order_id),
            ).fetchone() is not None:
                return blocked("box_reserved_order_has_command")
            orders = conn.execute(
                "SELECT symbol, status, filled_quantity FROM paper_limit_orders "
                "WHERE trading_account_id='paper' AND order_id=?", (order_id,),
            ).fetchall()
            if len(orders) > 1 or any(
                row[0] != symbol or row[1] != "cancelled"
                or not _zero_filled(row[2]) for row in orders
            ):
                return blocked("box_reserved_order_not_cancelled_zero_fill")
    # Even cancelled LIMIT orders can have fills. Never rely on terminal
    # status alone, and never allow an unproved partially-filled retirement.
    orders = conn.execute(
        "SELECT status, filled_quantity FROM paper_limit_orders "
        "WHERE trading_account_id='paper' AND symbol=?", (symbol,),
    ).fetchall()
    if not all(status == "cancelled" and _zero_filled(filled)
               for status, filled in orders):
        return blocked("symbol_limit_not_cancelled_zero_fill")
    return True

def prove_six_inert_approvals(conn, approvals, positions) -> None:
    """Attest exact known, unadmitted approvals in the pinned read-only snapshot."""
    _require(
        len(approvals) == len(IDLE_APPROVALS)
        and {row[1] for row in approvals} == set(IDLE_APPROVALS),
        "unexpected_active_robot_candidate",
    )
    # Entry metadata without a matching order is not absence of execution.
    _require(
        conn.execute(
            "SELECT COUNT(*) FROM robot_entry_orders m "
            "LEFT JOIN paper_limit_orders o ON m.order_id=o.order_id "
            "WHERE m.trading_account_id='paper' AND o.order_id IS NULL"
        ).fetchone()[0] == 0,
        "orphan_robot_entry_order_metadata",
    )
    for candidate_id, symbol, status, approved_at_ms in approvals:
        prefix, suffix = IDLE_APPROVALS[symbol]
        _require(
            status == "APPROVED"
            and (candidate_id == prefix if not suffix else (
                candidate_id.startswith(prefix) and candidate_id.endswith(suffix)
                and len(candidate_id) >= len(prefix) + len(suffix)
            )),
            "unexpected_approved_candidate_identity",
        )
        state = conn.execute(
            "SELECT approved_at_ms, state_revision, robot_state_json "
            "FROM robot_candidates WHERE trading_account_id='paper' AND candidate_id=?",
            (candidate_id,),
        ).fetchall()
        _require(len(state) == 1, "approved_candidate_identity_missing")
        approved, revision, raw_state = tuple(state[0])
        details = []
        proven = (
            type(approved) is int and approved > 0 and approved == approved_at_ms
            and type(revision) is int and (
                (revision == 0 and raw_state is None)
                or _historical_approval_progress(
                    conn, candidate_id=candidate_id, symbol=symbol,
                    revision=revision, raw_state=raw_state,
                    blocked_reasons=details,
                )
            )
        )
        _require(
            proven,
            "approved_candidate_has_admission_progress:"
            + symbol + ":" + (details[0] if details else "approved_metadata_invalid"),
        )
        _require(
            sum(projected_symbol == symbol for projected_symbol, *_ in positions) <= 1,
            "ambiguous_approved_candidate_projection",
        )
        for table, predicate, params in (
            ("robot_trades", "candidate_id=?", (candidate_id,)),
            ("box_attempt_ownership", "candidate_id=?", (candidate_id,)),
            ("trading_commands",
             ("symbol=? AND created_at_ms>=?" if revision == 0 else
              "symbol=? AND created_at_ms>=? AND "
              "(current_state IS NULL OR current_state NOT IN "
              "('cancelled','amended','rejected','failed'))"),
             (symbol, approved)),
            ("paper_limit_orders",
             ("symbol=? AND created_at_ms>=?" if revision == 0 else
              "symbol=? AND created_at_ms>=? AND "
              "(status IS NULL OR status!='cancelled')"),
             (symbol, approved)),
            ("executions", "symbol=? AND exchange_timestamp_ms>=?", (symbol, approved)),
        ):
            _require(
                conn.execute(
                    f"SELECT COUNT(*) FROM {table} "
                    f"WHERE trading_account_id='paper' AND {predicate}",
                    params,
                ).fetchone()[0] == 0,
                "approved_candidate_execution_or_ownership_unknown",
            )


