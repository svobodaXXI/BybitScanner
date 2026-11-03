"""Read-only preflight evidence for exactly two legacy PAPER Flat/OPEN Robot lots.

Not a canonical coordinator, shutdown exception, lifecycle repair, trade close,
or permission to deploy. In particular, this NEVER broadens the incident-scoped
JASMY-only SIGINT path. Every missing/ambiguous fill blocks the transition.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
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
# The exceptional old-release handoff is for these observed incident lots,
# not any future unrelated trades on the same pair of symbols. FLOW's durable
# trade/candidate IDs are not yet attested; require its observed lot identity
# and independent immutable execution proof instead of inventing those IDs.
JASMY_TRADE_ID = "robot-trade-2a023e646fd8add8b5b30cd8"
JASMY_CANDIDATE_ID = "2a023e646fd8add8b5b30cd8"
INCIDENT_LOT = {
    "JASMYUSDT": ("SHORT", "DOUBLE TOP", Decimal("399")),
    "FLOWUSDT": ("LONG", "MIRROR", Decimal("6550.8")),
}
PROOF_LABEL = "TWO_ORPHANS_IMMUTABLE_CLOSE_EVIDENCE_ONLY"


# Exact observed approvals, never a general candidate exemption. The Box
# candidate IDs were available only as bounded prefix/suffix evidence; their
# approval and zero-entry evidence must independently match the durable DB.
IDLE_APPROVALS = {
    "1000FLOKIUSDT": ("box-robot-aa55", "af8c6"),
    "BNCUSDT": ("589fc4625b687906eb778630", ""),
    "HEMIUSDT": ("box-robot-feaa", "24c43"),
    "INUSDT": ("box-robot-9631", "e84e8"),
    "PLAYSOUTUSDT": ("b4a30317bc2b6fa3777711c3", ""),
    "RUNEUSDT": ("box-robot-358e", "4dd3b"),
}


def _prove_six_inert_approvals(conn, candidates, positions) -> None:
    """No admission, order, execution or Box ownership since each approval.

    A candidate with runtime progress is NOT automatically invalidated. This
    is read-only evidence authorizing only the exact frozen incident handoff;
    its durable status is left for the next legitimate owner to reconcile.
    """
    _require(
        len(candidates) == len(IDLE_APPROVALS)
        and {row[1] for row in candidates} == set(IDLE_APPROVALS)
        and all(row[2] == "APPROVED" for row in candidates),
        "unexpected_active_robot_candidate",
    )
    for candidate_id, symbol, _ in candidates:
        prefix, suffix = IDLE_APPROVALS[symbol]
        _require(
            candidate_id.startswith(prefix)
            and (not suffix or candidate_id.endswith(suffix))
            and len(candidate_id) >= len(prefix) + len(suffix),
            "unexpected_approved_candidate_identity",
        )
        state = conn.execute(
            "SELECT approved_at_ms, state_revision, robot_state_json "
            "FROM robot_candidates WHERE trading_account_id='paper' AND candidate_id=?",
            (candidate_id,),
        ).fetchall()
        _require(len(state) == 1, "approved_candidate_identity_missing")
        approved_at, revision, raw_state = tuple(state[0])
        _require(
            type(approved_at) is int and approved_at > 0
            and type(revision) is int and revision == 0
            and raw_state is None,
            "approved_candidate_has_admission_progress",
        )
        _require(
            sum(projected_symbol == symbol for projected_symbol, *_ in positions) <= 1,
            "ambiguous_approved_candidate_projection",
        )
        for table, predicate, params in (
            ("robot_trades", "candidate_id=?", (candidate_id,)),
            ("box_attempt_ownership", "candidate_id=?", (candidate_id,)),
            ("trading_commands", "symbol=? AND created_at_ms>=?", (symbol, approved_at)),
            ("paper_limit_orders", "symbol=? AND created_at_ms>=?", (symbol, approved_at)),
            ("executions", "symbol=? AND exchange_timestamp_ms>=?", (symbol, approved_at)),
        ):
            query = (
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE trading_account_id='paper' AND {predicate}"
            )
            _require(
                conn.execute(query, params).fetchone()[0] == 0,
                "approved_candidate_execution_or_ownership_unknown",
            )


def prove_two_flat_orphans(
    conn: sqlite3.Connection, *, expected_identity: str,
    backend: dict, scanner: dict, autopilot: dict, protection: dict,
) -> str:
    """Read one stable SQLite snapshot; never call HTTP, migrate or write.

    Requires a separately frozen ingress and a uniquely attributable manual
    closing execution for EACH Robot lot. No other OPEN or APPROVED owner is
    allowed. Passing this preflight does not release the canonical stop fence.
    """
    # A coordinator must supply a single already-open, non-writable snapshot.
    # Reading independently committed rows can falsely pair a Flat projection
    # with a close execution or candidate from another runtime generation.
    _require(conn.in_transaction, "stable_snapshot_transaction_required")
    # Even an explicit BEGIN IMMEDIATE writer barrier must be query-only;
    # its reservation pins evidence but cannot authorize SQL mutations.
    _require(tuple(conn.execute("PRAGMA query_only").fetchone()) == (1,),
             "read_only_snapshot_required")
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
    covered = protection.get("covered_symbols")
    armed = protection.get("armed_symbols")
    roles = protection.get("coverage_roles")
    _require(
        isinstance(covered, list) and isinstance(armed, list)
        and isinstance(roles, dict)
        and len(covered) == len(set(covered))
        and len(armed) == len(set(armed)),
        "unexpected_protection_coverage",
    )
    # The incident's legacy backend retains coverage after BOTH trades have
    # already closed. Its WebSocket disconnect cannot become healthy because
    # the Robot ledger still claims those Flat trades are OPEN. Only this
    # precise frozen legacy shape may rely on immutable close/zero-entry proof
    # instead of feed continuity; other unhealthy causes remain forbidden.
    stale_incident = protection.get("healthy") is False
    if stale_incident:
        _require(
            protection.get("unhealthy_symbols") == {
                "JASMYUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
                "FLOWUSDT": "websocket_disconnect:WebSocketConnectionClosedException",
            },
            "protection_unhealthy",
        )
        idle_arms = {"BBUSDT", "KITEUSDT"}
        _require(
            set(roles) == EXPECTED_SYMBOLS | idle_arms
            and roles == {
                "JASMYUSDT": "EXPOSURE", "FLOWUSDT": "EXPOSURE",
                "BBUSDT": "ENTRY_PENDING", "KITEUSDT": "ENTRY_PENDING",
            }
            and set(covered) == set(roles)
            and set(armed) == idle_arms,
            "unexpected_protection_coverage",
        )
    else:
        _require(
            protection.get("healthy") is True
            and protection.get("unhealthy_symbols") == {},
            "protection_unhealthy",
        )
        _require(
            not armed
            and (
                (covered == [] and roles == {})
                or (len(covered) == 2 and set(covered) == EXPECTED_SYMBOLS
                    and roles == {symbol: "EXPOSURE" for symbol in EXPECTED_SYMBOLS})
            ),
            "unexpected_protection_coverage",
        )
    _require(tuple(conn.execute("PRAGMA quick_check").fetchone()) == ("ok",),
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
    open_candidates = [row for row in candidates if row[2] == "OPEN"]
    _require(
        len(open_candidates) == 2
        and {(row[0], row[1], row[2]) for row in open_candidates}
        == {(row[1], row[2], "OPEN") for row in rows},
        "unexpected_active_robot_candidate",
    )
    extra_candidates = [row for row in candidates if row[2] != "OPEN"]
    if stale_incident:
        # This exception is confined to the six *observed* idle approvals.
        # Mere APPROVED status and zero working LIMITs are NOT proof of
        # never-started execution. Check each candidate independently inside
        # the pinned transaction; UNKNOWN/filled/linked owner always blocks.
        _prove_six_inert_approvals(conn, extra_candidates, positions)
        for idle_symbol in ("BBUSDT", "KITEUSDT"):
            _require(
                sum(symbol == idle_symbol for symbol, *_ in positions) <= 1,
                "ambiguous_pending_entry_projection",
            )
            _require(
                not any(row[1] == idle_symbol for row in candidates),
                "stale_pending_entry_has_candidate_owner",
            )
    else:
        _require(not extra_candidates, "unexpected_active_robot_candidate")
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
        expected_direction, expected_pattern, expected_quantity = INCIDENT_LOT[symbol_text]
        _require(
            (symbol_text != "JASMYUSDT" or
             (trade_id == JASMY_TRADE_ID and candidate_id == JASMY_CANDIDATE_ID)),
            "unexpected_incident_robot_lot",
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
            and trade.entry_path in ("LIMIT", "MARKET")
            and trade.direction == expected_direction
            and str(trade.pattern).upper() == expected_pattern
            and trade.entry_quantity == expected_quantity,
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



def inspect_read_only(
    db_path: Path, *, expected_identity: str, snapshots: dict,
) -> str:
    """Coordinator's non-mutating preflight entrypoint, NOT a stop authorization.

    HTTP snapshots are supplied by the caller BEFORE opening the transaction.
    The caller must still re-attest runtime identity and immutable DB evidence
    at the separately approved handoff boundary. No SQL writes or migrations.
    """
    _require(db_path.is_file(), "paper_database_missing")
    _require(
        hashlib.sha256(str(db_path.resolve()).encode("utf-8")).hexdigest()
        == expected_identity,
        "paper_database_path_identity_mismatch",
    )
    try:
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            return prove_two_flat_orphans(
                conn, expected_identity=expected_identity, **snapshots,
            )
    except sqlite3.Error as exc:
        raise FlatRecoveryBlocked("paper_database_evidence_unreadable") from exc
