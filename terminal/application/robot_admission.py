"""Durable Robot v0.1 candidate admission gate.

The gate is the boundary between the Scanner/Telegram candidate handoff and
Terminal SQLite Robot authority. It admits no candidate unless durable Robot
runtime state is ROBOT_RUNNING + READY. It never submits, retries, amends,
cancels, or closes an order.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping
import time

from robot_candidate_store import approve_candidate, load_candidate
import robot_l_shape
from robot_state_machine import is_supported_pattern
from terminal.domain.models import Symbol, TradingAccountId
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


def _admit_box_plan_candidate(
    handle: str, *, database_path: Path | str | None, clock_ms,
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

    store = SQLiteStore.open(
        Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    )
    try:
        candidates = store.load_robot_candidates(PAPER_ACCOUNT_ID)
        sources = [item for item in candidates if item.candidate_id.startswith(source_prefix)]
        if len(sources) != 1:
            raise RobotAdmissionRejected("Scanner candidate is not admissible")
        source = sources[0]
        error = box_plan_source_admission_error(source)
        if error is not None:
            raise RobotAdmissionRejected(error)

        linked = [
            item for item in candidates
            if item.status != "BOX_PLAN_ONLY"
            and item.signal_snapshot.get("source_box_candidate_id") == source.candidate_id
        ]
        if len(linked) > 1:
            raise RobotAdmissionRejected("Robot candidate identity conflicts with durable state")
        if linked:
            return linked[0], False

        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotAdmissionRejected("Robot runtime state is unavailable")
        if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
            raise RobotAdmissionRejected("Robot admission is not ready")
        owners = active_robot_owner_candidate_ids(store, PAPER_ACCOUNT_ID, source.symbol)
        if owners:
            raise RobotAdmissionRejected(
                "Robot symbol already has an active exposure owner: " + ",".join(owners)
            )
        try:
            return store.handoff_box_plan_to_robot(
                source.candidate_id,
                symbol=source.symbol,
                expected_snapshot_sha256=source.snapshot_sha256,
                approved_at_ms=now,
            )
        except (PersistenceError, ValueError) as exc:
            raise RobotAdmissionRejected("Robot candidate identity conflicts with durable state") from exc
    finally:
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


def admit_robot_candidate(
    candidate_id: str,
    *,
    approval: Mapping[str, Any] | None = None,
    database_path: Path | str | None = None,
    store_dir: Path | str | None = None,
    clock_ms=None,
) -> tuple[RobotCandidateRecord, bool]:
    """Admit one approved Scanner candidate into authoritative SQLite state.

    Existing durable admission is returned idempotently. A new candidate is
    admitted only while the durable Robot runtime is ROBOT_RUNNING + READY.
    A ``bp-`` handle names an immutable Ikigai Box plan (SQLite only, no JSON envelope).
    """

    if str(candidate_id).startswith(BOX_PLAN_HANDLE_PREFIX):
        return _admit_box_plan_candidate(
            str(candidate_id), database_path=database_path, clock_ms=clock_ms,
        )

    candidate = load_candidate(candidate_id, store_dir=store_dir)
    error = scanner_candidate_admission_error(candidate)
    if error is not None:
        raise RobotAdmissionRejected(error)
    symbol = Symbol(str(candidate["symbol"]).strip())
    snapshot = candidate["signal_snapshot"]
    is_l_shape = robot_l_shape.is_l_shape_snapshot(snapshot)

    resolved_database_path = (
        Path(database_path) if database_path is not None else DEFAULT_DATABASE_PATH
    )
    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    if not isinstance(now, int) or isinstance(now, bool) or now < 0:
        raise RobotAdmissionRejected("Robot admission clock returned invalid timestamp")

    store = SQLiteStore.open(resolved_database_path)
    try:
        existing = store.get_robot_candidate(candidate_id)
        if existing is not None:
            if existing.status == "BOX_PLAN_ONLY":
                raise RobotAdmissionRejected("BOX_PLAN_ONLY cannot enter execution admission")
            if (
                existing.trading_account_id != PAPER_ACCOUNT_ID
                or existing.symbol != symbol
            ):
                raise RobotAdmissionRejected("Robot candidate identity conflicts with durable state")
            return existing, False

        runtime = store.get_robot_runtime_state(PAPER_ACCOUNT_ID)
        if runtime is None:
            raise RobotAdmissionRejected("Robot runtime state is unavailable")
        if runtime.mode != "ROBOT_RUNNING" or runtime.recovery_status != "READY":
            raise RobotAdmissionRejected("Robot admission is not ready")

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
    finally:
        store.close()

    # Legacy JSON is only the Scanner handoff envelope. Its approval marker is
    # updated after authoritative SQLite admission and remains idempotent.
    approve_candidate(
        candidate_id,
        approval=approval,
        store_dir=store_dir,
    )
    return record, created
