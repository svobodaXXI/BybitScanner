"""Durable Robot v0.1 candidate admission gate.

The gate is the boundary between the Scanner/Telegram candidate handoff and
Terminal SQLite Robot authority. It admits no candidate unless durable Robot
runtime state is ROBOT_RUNNING + READY. It never submits, retries, amends,
cancels, or closes an order.
"""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping
import time

from robot_candidate_store import approve_candidate, load_candidate
import robot_l_shape
from robot_state_machine import is_supported_pattern
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.source_terminal_events import (
    SourceTerminalEventError, load_terminal_identities, source_terminal_events_path,
)
from terminal.persistence.sqlite_store import (
    PersistenceError,
    RobotCandidateRecord,
    SQLiteStore,
)


PAPER_ACCOUNT_ID = TradingAccountId("paper")
DEFAULT_DATABASE_PATH = Path(
    os.environ.get("BYBITSCANNER_PAPER_DB", "paper_runtime.sqlite3")
)

# Telegram callback_data is limited to 64 bytes and a Box source id is 73
# characters, so the owner button carries a 160-bit prefix of its digest.
BOX_PLAN_HANDLE_PREFIX = "bp-"
_BOX_PLAN_SOURCE_PREFIX = "box-plan-"
_BOX_PLAN_HANDLE_HEX = 40


def candidate_snapshot_sha256(snapshot: Mapping[str, Any]) -> str:
    """Hash the immutable Scanner snapshot exactly as Autopilot identifies it."""
    text = json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RobotAdmissionRejected(PersistenceError):
    """Raised when a candidate cannot cross the durable Robot admission gate."""


def box_plan_admission_handle(source_candidate_id: str) -> str:
    """Callback-safe handle naming exactly one immutable BOX_PLAN_ONLY source."""
    digest = str(source_candidate_id).removeprefix(_BOX_PLAN_SOURCE_PREFIX)
    if (not str(source_candidate_id).startswith(_BOX_PLAN_SOURCE_PREFIX) or len(digest) != 64
            or any(char not in "0123456789abcdef" for char in digest)):
        raise ValueError("invalid BOX_PLAN_ONLY candidate id")
    return BOX_PLAN_HANDLE_PREFIX + digest[:_BOX_PLAN_HANDLE_HEX]


def _box_plan_source_prefix(handle: str) -> str | None:
    digest = handle.removeprefix(BOX_PLAN_HANDLE_PREFIX)
    if (not handle.startswith(BOX_PLAN_HANDLE_PREFIX) or len(digest) != _BOX_PLAN_HANDLE_HEX
            or any(char not in "0123456789abcdef" for char in digest)):
        return None
    return _BOX_PLAN_SOURCE_PREFIX + digest


@dataclass(frozen=True, slots=True)
class RobotReentryAdmissionRequest:
    """Trusted strategy's verified linkage proposal, NOT a public JSON signal.

    Admission owns durable creation and the STOP proof recheck. Constructed
    only by canonical strategy adapters after closed-candle validation.
    The normal Robot candidate path is unchanged when this is omitted.
    """

    campaign_id: str
    direction: str
    frozen_thesis_sha256: str
    reserved_risk_usdt: Decimal
    original_risk_budget_usdt: Decimal | None = None
    previous_stop_exec_id: str | None = None
    confirmed_at_ms: int | None = None
    strategy_confirmation_proven: bool = False


def _reserve_reentry_with_canonical_candidate(
    store: SQLiteStore, record: RobotCandidateRecord,
    proposal: RobotReentryAdmissionRequest, *, now: int,
) -> None:
    """Participate in the caller's Robot Admission BEGIN IMMEDIATE; no orders."""
    if not isinstance(proposal, RobotReentryAdmissionRequest):
        raise RobotAdmissionRejected("reentry contract must originate from a trusted adapter")
    if proposal.previous_stop_exec_id is None:
        if proposal.original_risk_budget_usdt is None:
            raise RobotAdmissionRejected("original campaign risk budget missing")
        store.create_robot_reentry_campaign(
            account=PAPER_ACCOUNT_ID, campaign_id=proposal.campaign_id,
            first_candidate_id=record.candidate_id,
            frozen_thesis_sha256=proposal.frozen_thesis_sha256,
            direction=proposal.direction,
            original_risk_budget_usdt=proposal.original_risk_budget_usdt,
            reserved_risk_usdt=proposal.reserved_risk_usdt,
            reserved_at_ms=now,
        )
    else:
        if proposal.confirmed_at_ms is None:
            raise RobotAdmissionRejected("post-STOP confirmation timestamp missing")
        store.reserve_robot_stop_reentry(
            account=PAPER_ACCOUNT_ID, campaign_id=proposal.campaign_id,
            candidate_id=record.candidate_id,
            frozen_thesis_sha256=proposal.frozen_thesis_sha256,
            direction=proposal.direction,
            previous_stop_exec_id=proposal.previous_stop_exec_id,
            confirmed_at_ms=proposal.confirmed_at_ms,
            reserved_risk_usdt=proposal.reserved_risk_usdt,
            reserved_at_ms=now,
            strategy_confirmation_proven=proposal.strategy_confirmation_proven,
        )


def _admit_box_plan_candidate(
    handle: str, *, database_path: Path | str | None, clock_ms,
    transaction_store: SQLiteStore | None = None,
    expected_snapshot_sha256: str | None = None,
    linked_mirror_parent_candidate_id: str | None = None,
    reentry: RobotReentryAdmissionRequest | None = None,
) -> tuple[RobotCandidateRecord, bool]:
    """Owner admission of one frozen Box plan through the existing atomic handoff.

    The source stays immutable; only store.handoff_box_plan_to_robot() creates the
    linked APPROVED / BOX_ENTRY_READY candidate. A repeated tap returns it unchanged.
    """
    source_prefix = _box_plan_source_prefix(handle)
    if source_prefix is None:
        raise RobotAdmissionRejected("Scanner candidate is not admissible")
    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise RobotAdmissionRejected("Robot admission clock returned invalid timestamp")

    owns_store = transaction_store is None
    store = transaction_store or SQLiteStore.open(
        Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    )
    if not owns_store and not store.in_robot_admission_transaction():
        raise RobotAdmissionRejected("Robot admission transaction is not active")
    context = store.robot_admission_transaction() if owns_store else nullcontext()
    try:
        with context:
            # FIX-4: exact reads instead of the whole candidate table. The prefix read
            # holds every id the handle can name (any status); the lineage read holds
            # every non-plan row naming this source (any status, any symbol).
            sources = store.load_robot_candidates_by_id_prefix(PAPER_ACCOUNT_ID, source_prefix)
            if len(sources) != 1:
                raise RobotAdmissionRejected("Scanner candidate is not admissible")
            source = sources[0]
            error = box_plan_source_admission_error(source)
            if error is not None:
                raise RobotAdmissionRejected(error)
            if (expected_snapshot_sha256 is not None
                    and source.snapshot_sha256 != expected_snapshot_sha256):
                raise RobotAdmissionRejected("Robot candidate immutable snapshot changed")

            linked = [
                item for item in store.load_robot_candidates_for_box_source(
                    PAPER_ACCOUNT_ID, source.candidate_id)
                if item.status != "BOX_PLAN_ONLY"
                and item.signal_snapshot.get("source_box_candidate_id") == source.candidate_id
            ]
            if len(linked) > 1:
                raise RobotAdmissionRejected("Robot candidate identity conflicts with durable state")
            if linked:
                if reentry is not None:
                    _reserve_reentry_with_canonical_candidate(
                        store, linked[0], reentry, now=now,
                    )
                return linked[0], False

            runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
            if runtime is None:
                raise RobotAdmissionRejected("Robot runtime state is unavailable")
            if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
                raise RobotAdmissionRejected("Robot admission is not ready")
            direction = str((source.signal_snapshot.get("identity") or {}).get("direction", ""))
            parent = linked_mirror_parent_candidate(
                store,
                PAPER_ACCOUNT_ID,
                source.symbol,
                direction,
                excluded_candidate_ids={source.candidate_id},
            )
            allowed_parent = (
                parent is not None
                and parent.candidate_id == linked_mirror_parent_candidate_id
            )
            owners = active_robot_owner_candidate_ids(store, PAPER_ACCOUNT_ID, source.symbol)
            active_conflicts = [
                item.candidate_id
                for item in store.load_active_robot_candidate_states(PAPER_ACCOUNT_ID)
                if item.symbol == source.symbol
                and item.candidate_id != source.candidate_id
                and item.status in {"APPROVED", "OPEN"}
            ]
            if (
                (owners or active_conflicts or linked_mirror_parent_candidate_id is not None)
                and not allowed_parent
            ):
                raise RobotAdmissionRejected(
                    "Robot symbol already has an active owner: "
                    + ",".join(sorted(set(owners) | set(active_conflicts)))
                )
            try:
                record, created = store.handoff_box_plan_to_robot(
                    source.candidate_id,
                    symbol=source.symbol,
                    expected_snapshot_sha256=source.snapshot_sha256,
                    approved_at_ms=now,
                    linked_mirror_parent_candidate_id=(
                        parent.candidate_id if allowed_parent else None
                    ),
                    linked_mirror_parent_snapshot_sha256=(
                        parent.snapshot_sha256 if allowed_parent else None
                    ),
                )
                if reentry is not None:
                    _reserve_reentry_with_canonical_candidate(
                        store, record, reentry, now=now,
                    )
                return record, created
            except (PersistenceError, ValueError) as exc:
                raise RobotAdmissionRejected(
                    "Robot candidate identity conflicts with durable state"
                ) from exc
    finally:
        if owns_store:
            store.close()


def active_robot_owner_candidate_ids(
    store: SQLiteStore,
    trading_account_id: TradingAccountId,
    symbol: Symbol,
    *,
    excluding_candidate_id: str | None = None,
) -> tuple[str, ...]:
    """Return candidate ids that already own exposure on ``symbol``.

    Robot v0.1 PAPER uses one-way ``position_idx=0`` net positions. Ownership
    belongs to an OPEN lifecycle, or to an APPROVED lifecycle whose own entry
    LIMIT has authoritative non-zero fill evidence. Unfilled APPROVED
    candidates are not owners and remain recoverable.
    """
    owners: list[str] = []
    # Only APPROVED/OPEN can own exposure; skip snapshots and finished history.
    for record in store.load_active_robot_candidate_states(trading_account_id):
        if record.symbol != symbol or record.candidate_id == excluding_candidate_id:
            continue
        if record.status == "OPEN":
            owners.append(record.candidate_id)
            continue
        if record.status != "APPROVED" or not isinstance(record.robot_state, Mapping):
            continue
        execution = record.robot_state.get("execution")
        if not isinstance(execution, Mapping):
            continue
        order_id = execution.get("limit_order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            continue
        order = store.get_paper_limit(order_id, trading_account_id)
        if order is not None and order.filled_quantity > 0:
            owners.append(record.candidate_id)
    return tuple(sorted(set(owners)))


def linked_mirror_parent_candidate(
    store: SQLiteStore,
    trading_account_id: TradingAccountId,
    symbol: Symbol,
    direction: str,
    *,
    excluded_candidate_ids: set[str] | frozenset[str] = frozenset(),
) -> RobotCandidateRecord | None:
    """Return the sole compatible Wedge exposure owner for a linked Box.

    This is deliberately narrower than ordinary symbol ownership.  A pending
    Box can share the existing reservation only with one APPROVED Wedge
    campaign owner in the same direction, before either candidate has opened
    exposure, and only when no other active idea competes for the symbol.
    Every other case stays on the normal SYMBOL_OWNED path.
    """
    normalized = str(direction).strip().upper()
    if normalized not in {"LONG", "SHORT"}:
        return None
    if active_robot_owner_candidate_ids(store, trading_account_id, symbol):
        return None
    position = store.get_position_projection(
        PositionKey(trading_account_id, Category.LINEAR, symbol, 0)
    )
    if (
        position is not None
        and position.side is not PositionSide.FLAT
        and position.quantity.value > 0
    ):
        return None
    active = [
        item
        for item in store.load_active_robot_candidate_states(trading_account_id)
        if item.symbol == symbol
        and item.candidate_id not in excluded_candidate_ids
        and item.status in {"APPROVED", "OPEN"}
    ]
    if len(active) != 1:
        return None
    parent = store.get_robot_candidate(active[0].candidate_id)
    if (
        parent is None
        or parent.trading_account_id != trading_account_id
        or parent.symbol != symbol
        or parent.status != "APPROVED"
        or parent.signal_snapshot.get("pattern") not in {"Rising Wedge", "Falling Wedge"}
        or not isinstance(parent.robot_state, Mapping)
        or str(parent.robot_state.get("direction", "")).strip().upper() != normalized
    ):
        return None
    execution = parent.robot_state.get("execution")
    if isinstance(execution, Mapping):
        order_id = execution.get("limit_order_id")
        if isinstance(order_id, str) and order_id.strip():
            order = store.get_paper_limit(order_id, trading_account_id)
            if order is not None and order.status not in {"filled", "cancelled"}:
                return None
        if isinstance(execution.get("late_market_intent"), Mapping):
            return None
    return parent


def scanner_candidate_admission_error(candidate: Mapping[str, Any]) -> str | None:
    """Pure Scanner-candidate admissibility checks of ``admit_robot_candidate``.

    Returns the rejection message, or None when the immutable candidate may enter
    admission. Shared with the Autopilot SHADOW fact collector so both use exactly
    the same per-pattern rules (Wedge 1m/handoff geometry, L-shape frozen terms).
    An invalid symbol still raises ValueError, in the original order.
    """
    if candidate["status"] not in {"AVAILABLE", "APPROVED"}:
        return "Scanner candidate is not admissible"

    Symbol(str(candidate["symbol"]).strip())
    snapshot = candidate.get("signal_snapshot")
    if not isinstance(snapshot, dict):
        return "Scanner candidate snapshot is invalid"
    if (snapshot.get("pattern") == "IKIGAI_BOX"
            or candidate.get("status") == "BOX_PLAN_ONLY"):
        return "BOX_PLAN_ONLY cannot enter execution admission"
    is_l_shape = robot_l_shape.is_l_shape_snapshot(snapshot)
    if not is_l_shape and not is_supported_pattern(snapshot.get("pattern")):
        return "Scanner candidate pattern is not supported by Robot"

    source_timeframe = str(candidate.get("timeframe", "")).strip()
    if robot_l_shape.is_mirror_snapshot(snapshot) and not robot_l_shape.mirror_standalone_enabled():
        return "MIRROR standalone Robot is not enabled"
    if is_l_shape:
        if source_timeframe not in {"1", "5"}:
            return "L-shape Robot supports only 1m or 5m source timeframe"
        if snapshot.get("robot_handoff_ready") is not True:
            return "L-shape candidate has no Robot handoff"
        try:
            terms = robot_l_shape.frozen_terms(snapshot)
        except robot_l_shape.RobotLShapeError:
            return "Scanner candidate snapshot is invalid"
        if source_timeframe != terms.source_timeframe:
            return "L-shape source timeframe conflicts with frozen terms"
    elif source_timeframe != "1":
        if snapshot.get("robot_handoff_ready") is not True:
            return "Scanner candidate has no proven Robot 1m handoff"
        if not isinstance(snapshot.get("robot_geometry"), dict):
            return "Scanner candidate has no projected Robot geometry"
        cursor = snapshot.get("scanner_geometry_cursor")
        if (
            not isinstance(cursor, dict)
            or str(cursor.get("timeframe", "")).strip() != "1"
        ):
            return "Scanner candidate has no Robot 1m geometry cursor"
    return None


def box_plan_source_admission_error(
    source: RobotCandidateRecord, trading_account_id: TradingAccountId = PAPER_ACCOUNT_ID,
) -> str | None:
    """Pure source checks of the owner Box admission (shared with Autopilot SHADOW)."""
    if (source.status != "BOX_PLAN_ONLY"
            or source.trading_account_id != trading_account_id
            or source.signal_snapshot.get("pattern") != "IKIGAI_BOX"
            or source.signal_snapshot.get("identity", {}).get("symbol") != source.symbol.value):
        return "Scanner candidate is not admissible"
    return None


def _reject_source_terminal_snapshot(
    store: SQLiteStore, candidate_id: str, snapshot_sha256: str,
) -> None:
    """Fail closed: a proven source-terminal (EXPIRED/INVALIDATED) snapshot is never admitted.

    A missing sidecar proves nothing and admits; an unreadable, foreign or
    inconsistent one cannot be trusted, so a new admission is refused.
    """
    path = getattr(store, "path", None)
    if path is None:
        return
    try:
        identities = load_terminal_identities(
            source_terminal_events_path(path), PAPER_ACCOUNT_ID.value,
        )
    except SourceTerminalEventError:
        raise RobotAdmissionRejected("Source-terminal events are unavailable") from None
    if identities is not None and (candidate_id, snapshot_sha256) in identities:
        raise RobotAdmissionRejected("Scanner candidate snapshot is proven terminal")


def admit_robot_candidate(
    candidate_id: str,
    *,
    approval: Mapping[str, Any] | None = None,
    database_path: Path | str | None = None,
    store_dir: Path | str | None = None,
    clock_ms=None,
    transaction_store: SQLiteStore | None = None,
    expected_snapshot_sha256: str | None = None,
    mark_legacy_approved: bool = True,
    linked_mirror_parent_candidate_id: str | None = None,
    reentry: RobotReentryAdmissionRequest | None = None,
) -> tuple[RobotCandidateRecord, bool]:
    """Admit one approved Scanner candidate into authoritative SQLite state.

    Existing durable admission is returned idempotently. A new candidate is
    admitted only while the durable Robot runtime is ROBOT_RUNNING + READY.
    A ``bp-`` handle names an immutable Ikigai Box plan (SQLite only, no JSON envelope).
    """

    if str(candidate_id).startswith(BOX_PLAN_HANDLE_PREFIX):
        return _admit_box_plan_candidate(
            str(candidate_id), database_path=database_path, clock_ms=clock_ms,
            transaction_store=transaction_store,
            expected_snapshot_sha256=expected_snapshot_sha256,
            linked_mirror_parent_candidate_id=linked_mirror_parent_candidate_id,
            reentry=reentry,
        )

    candidate = load_candidate(candidate_id, store_dir=store_dir)
    error = scanner_candidate_admission_error(candidate)
    if error is not None:
        raise RobotAdmissionRejected(error)
    symbol = Symbol(str(candidate["symbol"]).strip())
    snapshot = candidate["signal_snapshot"]
    snapshot_sha256 = candidate_snapshot_sha256(snapshot)
    if (expected_snapshot_sha256 is not None
            and snapshot_sha256 != expected_snapshot_sha256):
        raise RobotAdmissionRejected("Robot candidate immutable snapshot changed")
    is_l_shape = robot_l_shape.is_l_shape_snapshot(snapshot)

    resolved_database_path = (
        Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    )
    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise RobotAdmissionRejected("Robot admission clock returned invalid timestamp")

    owns_store = transaction_store is None
    store = transaction_store or SQLiteStore.open(resolved_database_path)
    if not owns_store and not store.in_robot_admission_transaction():
        raise RobotAdmissionRejected("Robot admission transaction is not active")
    if not owns_store and mark_legacy_approved:
        raise ValueError("external Robot admission transaction must defer legacy approval")
    context = store.robot_admission_transaction() if owns_store else nullcontext()
    try:
        with context:
            existing = store.get_robot_candidate(candidate_id)
            if existing is not None:
                if existing.status == "BOX_PLAN_ONLY":
                    raise RobotAdmissionRejected("BOX_PLAN_ONLY cannot enter execution admission")
                if (
                    existing.trading_account_id != PAPER_ACCOUNT_ID
                    or existing.symbol != symbol
                    or (expected_snapshot_sha256 is not None
                        and existing.snapshot_sha256 != expected_snapshot_sha256)
                ):
                    raise RobotAdmissionRejected(
                        "Robot candidate identity conflicts with durable state"
                    )
                record, created = existing, False
            else:
                runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
                if runtime is None:
                    raise RobotAdmissionRejected("Robot runtime state is unavailable")
                if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
                    raise RobotAdmissionRejected("Robot admission is not ready")
                _reject_source_terminal_snapshot(store, candidate_id, snapshot_sha256)

                owners = active_robot_owner_candidate_ids(
                    store, PAPER_ACCOUNT_ID, symbol, excluding_candidate_id=candidate_id,
                )
                if owners:
                    raise RobotAdmissionRejected(
                        "Robot symbol already has an active exposure owner: " + ",".join(owners)
                    )

                record, created = store.create_robot_candidate(
                    candidate_id=candidate_id,
                    trading_account_id=PAPER_ACCOUNT_ID,
                    symbol=symbol,
                    status="APPROVED",
                    signal_snapshot=snapshot,
                    approved_at_ms=now,
                    updated_at_ms=now,
                )
                if created and is_l_shape:
                    state, _event = robot_l_shape.initialize_state({
                        "candidate_id": candidate_id,
                        "status": "APPROVED",
                        "signal_snapshot": snapshot,
                    })
                    record = store.save_robot_candidate_state(
                        candidate_id,
                        status="APPROVED",
                        robot_state=state,
                        expected_revision=record.state_revision,
                        updated_at_ms=now,
                    )
            if reentry is not None:
                _reserve_reentry_with_canonical_candidate(store, record, reentry, now=now)
    finally:
        if owns_store:
            store.close()

    # Legacy JSON is only the Scanner handoff envelope. Its approval marker is
    # updated after authoritative SQLite admission and remains idempotent.
    if mark_legacy_approved:
        approve_candidate(
            candidate_id,
            approval=approval,
            store_dir=store_dir,
        )
    return record, created
