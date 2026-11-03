"""Exact read-only evidence for the six historical PAPER idle approvals.

Shared by legacy protected handoff and post-Gitless EDITOR_ONLY reconciliation.
This never opens/migrates/writes the real PAPER database or authorizes START.
"""

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
        _require(
            type(approved) is int and approved > 0 and approved == approved_at_ms
            and type(revision) is int and revision == 0 and raw_state is None,
            "approved_candidate_has_admission_progress",
        )
        _require(
            sum(projected_symbol == symbol for projected_symbol, *_ in positions) <= 1,
            "ambiguous_approved_candidate_projection",
        )
        for table, predicate, params in (
            ("robot_trades", "candidate_id=?", (candidate_id,)),
            ("box_attempt_ownership", "candidate_id=?", (candidate_id,)),
            ("trading_commands", "symbol=? AND created_at_ms>=?", (symbol, approved)),
            ("paper_limit_orders", "symbol=? AND created_at_ms>=?", (symbol, approved)),
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


