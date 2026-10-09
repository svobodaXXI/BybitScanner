"""Autopilot SHADOW "First Eligible" observer (issue #446, slice A1).

Evaluates each Scanner Robot candidate once, at the moment it actually arrives
(Wedge / L-shape JSON handoff, or a frozen Ikigai Box plan), with the existing
Stage A policy, and appends the result to the existing immutable audit. It is
read-only for every trading object: it never calls admission, the planner, the
executor or any order path, and never creates or changes a candidate.

First Eligible: there is no ranking and no batch window. Candidates are
evaluated in arrival order, one by one; the audit order is that order.

Facts come only from authoritative state. A fact without an authoritative
source is reported as such (WAIT with an exact reason), never assumed:
- protection health: the in-process coverage manager when bound, else unknown;
- portfolio policy: no owner-approved source exists yet, so never ready.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

from pattern_robot_integration import is_robot_executable_signal
from robot_candidate_store import load_candidate
from terminal.application.robot_admission import (
    active_robot_owner_candidate_ids,
    box_plan_source_admission_error,
    scanner_candidate_admission_error,
)
from terminal.application.robot_autopilot import (
    RobotAutoAdmissionFacts,
    RobotAutoAdmissionResult,
    evaluate_auto_admission,
    record_auto_decision,
)
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotAutoDecisionRecord, SQLiteStore


SOURCE_SCANNER = "SCANNER"  # immutable Wedge / L-shape JSON candidate
SOURCE_BOX_PLAN = "BOX_PLAN"  # immutable BOX_PLAN_ONLY SQLite source
SHADOW_MODE = "SHADOW"
_TERMINAL_STATUSES = {"EXPIRED", "INVALIDATED"}
_ACTIVE_STATUSES = ("APPROVED", "OPEN")


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    facts: RobotAutoAdmissionFacts
    result: RobotAutoAdmissionResult
    decision: RobotAutoDecisionRecord
    created: bool


@dataclass(frozen=True, slots=True)
class _Candidate:
    ref: str
    pattern: str
    symbol: Symbol
    timeframe: str
    source_identity: str
    snapshot_sha256: str | None
    valid: bool
    executable: bool
    invalidated: bool
    already_admitted: bool
    own_ids: frozenset[str]


def _sha256(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scanner_candidate(store: SQLiteStore, ref: str, store_dir) -> _Candidate:
    envelope = load_candidate(ref, store_dir=store_dir)
    snapshot = envelope.get("signal_snapshot")
    timeframe = str(envelope.get("timeframe", "")).strip()
    try:
        error = scanner_candidate_admission_error(envelope)
    except ValueError:
        error = "invalid symbol"
    durable = store.get_robot_candidate(ref)
    pattern = str((snapshot or {}).get("pattern") or "UNKNOWN").strip() or "UNKNOWN"
    snapshot_sha = _sha256(snapshot)
    return _Candidate(
        ref=ref,
        pattern=pattern,
        symbol=Symbol(str(envelope.get("symbol") or "UNKNOWN").strip() or "UNKNOWN"),
        timeframe=timeframe or "UNKNOWN",
        source_identity=f"{ref}:{snapshot_sha}",
        snapshot_sha256=snapshot_sha,
        valid=error is None,
        executable=is_robot_executable_signal(snapshot, timeframe=timeframe),
        invalidated=durable is not None and durable.status in _TERMINAL_STATUSES,
        already_admitted=durable is not None,
        own_ids=frozenset({ref}),
    )


def _box_plan_candidate(
    store: SQLiteStore, ref: str, account: TradingAccountId,
) -> _Candidate:
    source = store.get_robot_candidate(ref)
    if source is None:
        raise LookupError(f"Box plan source not found: {ref}")
    identity = source.signal_snapshot.get("identity") or {}
    linked = [
        item for item in store.load_robot_candidates(account)
        if item.status != "BOX_PLAN_ONLY"
        and item.signal_snapshot.get("source_box_candidate_id") == source.candidate_id
    ]
    return _Candidate(
        ref=ref,
        pattern="IKIGAI_BOX",
        symbol=source.symbol,
        timeframe=str(identity.get("timeframe") or "UNKNOWN").strip() or "UNKNOWN",
        source_identity=f"{ref}:{source.snapshot_sha256}",
        snapshot_sha256=source.snapshot_sha256,
        # The Box gates (grid, P4 beyond F1.618, net RR >= 2, STOP) ran when the
        # plan was frozen; an inadmissible formation never becomes BOX_PLAN_ONLY.
        valid=box_plan_source_admission_error(source, account) is None,
        executable=True,
        invalidated=any(item.status in _TERMINAL_STATUSES for item in linked),
        already_admitted=bool(linked),
        own_ids=frozenset({ref, *(item.candidate_id for item in linked)}),
    )


def _symbol_owned(store: SQLiteStore, account: TradingAccountId, candidate: _Candidate) -> bool:
    """One controller per symbol (v0.1 decisions): Robot owner, active idea or manual position."""
    if active_robot_owner_candidate_ids(store, account, candidate.symbol):
        return True
    for record in store.load_active_robot_candidate_states(account):
        if (record.symbol == candidate.symbol and record.status in _ACTIVE_STATUSES
                and record.candidate_id not in candidate.own_ids):
            return True
    position = store.get_position_projection(PositionKey(account, Category.LINEAR, candidate.symbol, 0))
    return position is not None and position.side is not PositionSide.FLAT and position.quantity.value > 0


def observe_shadow_candidate(
    store: SQLiteStore,
    account: TradingAccountId,
    *,
    source: str,
    candidate_ref: str,
    protection_healthy: Callable[[], bool] | None = None,
    candidate_store_dir: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> ShadowObservation | None:
    """Evaluate one arrived candidate in SHADOW; return None when Autopilot is not SHADOW.

    OFF (the default) reads only the mode row and writes nothing. PAPER_AUTO is
    not part of this slice and is treated like OFF: no evaluation, no admission.
    A candidate already decided for the same immutable snapshot is not written again.
    """
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != SHADOW_MODE:
        return None
    if source == SOURCE_SCANNER:
        candidate = _scanner_candidate(store, candidate_ref, candidate_store_dir)
    elif source == SOURCE_BOX_PLAN:
        candidate = _box_plan_candidate(store, candidate_ref, account)
    else:
        raise ValueError(f"unknown Autopilot SHADOW source: {source!r}")

    runtime = store.get_robot_runtime_state(account)
    try:
        healthy = None if protection_healthy is None else bool(protection_healthy())
    except Exception:
        healthy = None
    facts = RobotAutoAdmissionFacts(
        autopilot_mode=state.mode,
        environment="PAPER",
        robot_mode=runtime.mode if runtime is not None else None,
        robot_recovery_status=runtime.recovery_status if runtime is not None else None,
        candidate_valid=candidate.valid,
        candidate_executable=candidate.executable,
        # Evaluated synchronously when the candidate arrives, never later in a batch.
        candidate_stale=False,
        candidate_invalidated=candidate.invalidated,
        already_admitted=candidate.already_admitted,
        reconciliation_clear=(
            runtime is not None and runtime.recovery_status != "RECONCILIATION_REQUIRED"
        ),
        symbol_owned=_symbol_owned(store, account, candidate),
        protection_healthy=healthy,
        # No owner-approved portfolio/capital policy source exists yet (issue #446).
        portfolio_policy_ready=False,
    )
    result = evaluate_auto_admission(facts)

    for existing in store.load_robot_auto_decisions(account):
        if (existing.candidate_ref == candidate.ref
                and existing.source_identity == candidate.source_identity
                and existing.mode == facts.autopilot_mode
                and existing.policy_version == result.policy_version):
            return ShadowObservation(facts, result, existing, False)

    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    decision, created = record_auto_decision(
        store,
        trading_account_id=account,
        candidate_ref=candidate.ref,
        pattern=candidate.pattern,
        symbol=candidate.symbol,
        timeframe=candidate.timeframe,
        source_identity=candidate.source_identity,
        snapshot_sha256=candidate.snapshot_sha256,
        facts=facts,
        result=result,
        evaluated_at_ms=now,
    )
    return ShadowObservation(facts, result, decision, created)


def shadow_mode_or_off(mode: str) -> str:
    """Owner control for this slice: only OFF and SHADOW may be set."""
    normalized = str(mode).strip().upper()
    if normalized not in {"OFF", SHADOW_MODE}:
        raise ValueError("only OFF and SHADOW are supported; PAPER_AUTO is not available")
    return normalized
