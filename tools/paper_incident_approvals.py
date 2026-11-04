"""Exact read-only evidence for the six historical PAPER idle approvals.

Shared by legacy protected handoff and post-Gitless EDITOR_ONLY reconciliation.
This never opens/migrates/writes the real PAPER database or authorizes START.
"""

import json
from collections import Counter
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


def _failed_limit_evidence_shape(conn, *, bad_orders, approved_at_ms: int) -> str:
    """Bounded, non-identifying READ-ONLY evidence; never changes acceptance.

    Return categories and chronology, not order IDs, candidate IDs, exact
    trade quantities or database values. Any diagnostic failure leaves the
    original BLOCKED gate in force.
    """
    status = Counter()
    quantity = Counter()
    chronology = Counter()
    executions = 0
    robot_entries = 0
    box_owners = 0
    sampled = bad_orders[:16]
    try:
        for order_id, raw_status, raw_quantity, created_at, *_ in sampled:
            label = raw_status if raw_status in (
                "filled", "cancelled", "open", "partially_filled", "pending",
                "rejected", "expired", "failed",
            ) else "other"
            status[label] += 1
            try:
                value = Decimal(str(raw_quantity))
                if not value.is_finite():
                    category = "invalid"
                elif value == 0:
                    category = "zero"
                elif value > 0:
                    category = "positive"
                else:
                    category = "negative"
            except (InvalidOperation, TypeError, ValueError):
                category = "invalid"
            quantity[category] += 1
            moment = (
                "before" if type(created_at) is int and created_at < approved_at_ms
                else "since" if type(created_at) is int
                else "unknown"
            )
            chronology[moment] += 1
            if isinstance(order_id, str) and order_id:
                executions += bool(conn.execute(
                    "SELECT 1 FROM executions WHERE trading_account_id='paper' "
                    "AND order_id=? LIMIT 1", (order_id,),
                ).fetchone())
                robot_entries += bool(conn.execute(
                    "SELECT 1 FROM robot_entry_orders "
                    "WHERE trading_account_id='paper' AND order_id=? LIMIT 1",
                    (order_id,),
                ).fetchone())
                box_owners += bool(conn.execute(
                    "SELECT 1 FROM box_order_ownership "
                    "WHERE trading_account_id='paper' AND order_id=? LIMIT 1",
                    (order_id,),
                ).fetchone())
    except Exception:
        return "diagnostic_unavailable"
    summary = lambda values: ",".join(
        f"{key}={count}" for key, count in sorted(values.items())
    )
    return (
        f"bad={len(bad_orders)};sample={len(sampled)};"
        f"time[{summary(chronology)}];status[{summary(status)}];"
        f"qty[{summary(quantity)}];exec={executions};"
        f"robotentry={robot_entries};boxowner={box_owners}"
    )


def _prove_old_inusdt_limits_flat(conn, *, orders, approved_at_ms: int) -> bool:
    """Incident-only evidence for two *prior* cancelled, partly filled LIMITs.

    Closing evidence is the complete symbol execution ledger's signed zero
    balance together with one synchronized FLAT projection, not the LIMIT
    terminal status. Never infer zero fills from 'cancelled'. This predicate
    is deliberately independent of order/candidate naming or trade prices.
    """
    if type(approved_at_ms) is not int or approved_at_ms <= 0:
        return False
    # The exact observed incident: two pre-approval partial fills. Any
    # additional abnormal order, newer order, or owner conflicts blocks.
    legacy = [row for row in orders
              if row[1] != "cancelled" or not _zero_filled(row[2])]
    if len(legacy) != 2 or len({row[0] for row in legacy}) != 2:
        return False
    for order_id, status, filled, created_at, side, quantity in legacy:
        if (not isinstance(order_id, str) or not order_id
                or status != "cancelled"
                or type(created_at) is not int or not 0 < created_at < approved_at_ms
                or side not in ("Buy", "Sell")):
            return False
        try:
            filled_dec = Decimal(str(filled))
            ordered_dec = Decimal(str(quantity))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if (not filled_dec.is_finite() or not ordered_dec.is_finite()
                or not 0 < filled_dec < ordered_dec):
            return False
        # A prior Robot entry marker is not itself proof of an OPEN owner.
        # It must be linked unambiguously to this historical order, but
        # cannot be a reservation of a current Box candidate.
        marker = conn.execute(
            "SELECT COUNT(*) FROM robot_entry_orders "
            "WHERE trading_account_id='paper' AND order_id=?", (order_id,),
        ).fetchone()
        if marker is None or marker[0] != 1:
            return False
        if conn.execute(
            "SELECT 1 FROM box_order_ownership WHERE trading_account_id='paper' "
            "AND order_id=? LIMIT 1", (order_id,),
        ).fetchone() is not None:
            return False
        fills = conn.execute(
            "SELECT side, quantity, exchange_timestamp_ms FROM executions "
            "WHERE trading_account_id='paper' AND symbol='INUSDT' "
            "AND order_id=?", (order_id,),
        ).fetchall()
        if not fills:
            return False
        summed = Decimal("0")
        for fill_side, raw_qty, timestamp in fills:
            if (fill_side != side or type(timestamp) is not int
                    or not created_at <= timestamp < approved_at_ms):
                return False
            try:
                qty = Decimal(str(raw_qty))
            except (InvalidOperation, TypeError, ValueError):
                return False
            if not qty.is_finite() or qty <= 0:
                return False
            summed += qty
        if summed != filled_dec:
            return False
    # Independent, complete immutable execution ledger, including any
    # Market exit: no unbalanced past exposure and no fill after approval.
    executions = conn.execute(
        "SELECT side, quantity, exchange_timestamp_ms FROM executions "
        "WHERE trading_account_id='paper' AND symbol='INUSDT'",
    ).fetchall()
    if not executions:
        return False
    net = Decimal("0")
    for side, raw_qty, timestamp in executions:
        if (side not in ("Buy", "Sell") or type(timestamp) is not int
                or not 0 < timestamp < approved_at_ms):
            return False
        try:
            qty = Decimal(str(raw_qty))
        except (InvalidOperation, TypeError, ValueError):
            return False
        if not qty.is_finite() or qty <= 0:
            return False
        net += qty if side == "Buy" else -qty
    if net != 0:
        return False
    projections = conn.execute(
        "SELECT side, quantity, sync_state FROM position_projections "
        "WHERE trading_account_id='paper' AND symbol='INUSDT'",
    ).fetchall()
    if (len(projections) != 1
            or projections[0][0] != "Flat"
            or not _zero_filled(projections[0][1])
            or projections[0][2] not in ("synced", "synchronized")):
        return False
    return conn.execute(
        "SELECT 1 FROM robot_trades WHERE trading_account_id='paper' "
        "AND symbol='INUSDT' AND exit_time_ms IS NULL LIMIT 1",
    ).fetchone() is None


def _historical_approval_progress(conn, *, candidate_id: str, symbol: str,
                                  revision: int, raw_state: str,
                                  approved_at_ms: int | None = None,
                                  blocked_reasons: list[str] | None = None) -> bool:
    """Report only a bounded invariant code; never log state JSON or owner IDs."""
    def blocked(reason: str) -> bool:
        if blocked_reasons is not None:
            blocked_reasons.append(reason)
        return False

    expected_revision, expected_phase = _INCIDENT_ADVANCED_APPROVALS[symbol]
    # The 2026-11-04 protected STOP attempt left a durable BNCUSDT
    # APPROVED/RETEST_DETECTED state at revision 7 (confirmed by owner-only
    # READ-ONLY VPS snapshot). An additional revision is *not* proof of entry:
    # accept only this incident-specific value, and only after the unchanged
    # per-order, execution, command, trade and owner checks below.
    allowed_revision = (
        revision == expected_revision
        or (symbol == "BNCUSDT" and expected_revision == 6 and revision == 7)
    )
    if not allowed_revision or not isinstance(raw_state, str):
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
        "SELECT order_id, status, filled_quantity, created_at_ms, side, quantity "
        "FROM paper_limit_orders "
        "WHERE trading_account_id='paper' AND symbol=?", (symbol,),
    ).fetchall()
    bad_orders = [
        row for row in orders
        if row[1] != "cancelled" or not _zero_filled(row[2])
    ]
    if bad_orders:
        # No general historical-fill exception. Only INUSDT's two
        # observed pre-approval, settled partial fills may pass after proving
        # exact order execution linkage and complete signed FLAT ledger.
        if (symbol == "INUSDT"
                and _prove_old_inusdt_limits_flat(
                    conn, orders=orders, approved_at_ms=approved_at_ms,
                )):
            return True
        detail = _failed_limit_evidence_shape(
            conn, bad_orders=bad_orders,
            approved_at_ms=approved_at_ms if type(approved_at_ms) is int else -1,
        )
        return blocked("symbol_limit_not_cancelled_zero_fill:" + detail)
    return True

def _six_approval_progress_snapshot(conn) -> str:
    """Six fixed labels only; no IDs, quantities, free-text JSON or SQL writes.

    Fail-closed proof diagnostics share its existing read-only transaction.
    The snapshot never changes which revisions or phases are acceptable.
    """
    try:
        rows = conn.execute(
            "SELECT symbol,state_revision,robot_state_json FROM robot_candidates "
            "WHERE trading_account_id='paper' AND status='APPROVED'"
        ).fetchall()
        by_symbol = {}
        for symbol, revision, raw_state in rows:
            if symbol not in IDLE_APPROVALS:
                continue
            rev = str(revision) if type(revision) is int and 0 <= revision < 1000 else "?"
            kind = "N" if raw_state is None else "X"
            phase = "?"
            if isinstance(raw_state, str):
                try:
                    parsed = json.loads(raw_state)
                    if isinstance(parsed, dict):
                        kind = "O"
                        phase = {
                            "BOX_ENTRY_READY": "B",
                            "RETEST_DETECTED": "R",
                            "ENTRY_PENDING": "P",
                        }.get(parsed.get("phase"), "?")
                except (TypeError, ValueError):
                    pass
            if symbol in by_symbol:
                by_symbol[symbol] = "multiple"
            else:
                by_symbol[symbol] = rev + phase + kind
        labels = {
            "1000FLOKIUSDT": "FLOKI", "BNCUSDT": "BNC",
            "HEMIUSDT": "HEMI", "INUSDT": "IN",
            "PLAYSOUTUSDT": "PLAYS", "RUNEUSDT": "RUNE",
        }
        return ",".join(
            labels[symbol] + "=" + by_symbol.get(symbol, "missing")
            for symbol in IDLE_APPROVALS
        )
    except (TypeError, ValueError):
        return "unavailable"


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
                    approved_at_ms=approved, blocked_reasons=details,
                )
            )
        )
        _require(
            proven,
            "approved_candidate_has_admission_progress:"
            + symbol + ":" + (details[0] if details else "approved_metadata_invalid")
            + (":six=" + _six_approval_progress_snapshot(conn) if not proven else ""),
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


