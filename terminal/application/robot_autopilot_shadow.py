"""Autopilot SHADOW "First Eligible" observer (issue #446, slice A1).

SHADOW evaluates each Scanner Robot candidate once, at the moment it actually arrives
(Wedge / L-shape JSON handoff, or a frozen Ikigai Box plan), with the existing
Stage A policy, and appends the result to the existing immutable audit. It is
read-only for every trading object. The dormant S3 helper can convert a prior
immutable SHADOW ALLOW through canonical Robot admission, but it is not wired
to runtime and the owner mode control still cannot enable PAPER_AUTO.

First Eligible: there is no ranking and no batch window. Candidates are
evaluated in arrival order, one by one; the audit order is that order.

A6 bounded WAIT reevaluation: there is no scheduler or polling. Only the existing
observer / S3 calls may evaluate a recorded WAIT again, and only on a newly closed
source candle or a durable Robot/Autopilot state transition while the idea is
still fresh. A stale or invalidated idea gets one terminal REJECT and is never
resumed; ALLOW and REJECT stay frozen.

Facts come only from authoritative state. A fact without an authoritative
source is reported as such (WAIT with an exact reason), never assumed:
- protection health: the in-process coverage manager when bound, else unknown;
- portfolio policy: owner-approved fixed RO policy and account-scoped PAPER facts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Any, Callable

from pattern_robot_integration import is_robot_executable_signal
from robot_candidate_store import approve_candidate, load_candidate
from terminal.application.robot_admission import (
    active_robot_owner_candidate_ids,
    admit_robot_candidate,
    box_plan_source_admission_error,
    box_plan_admission_handle,
    candidate_snapshot_sha256,
    scanner_candidate_admission_error,
)
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW,
    OUTCOME_WAIT,
    POLICY_VERSION,
    REASON_ALREADY_ADMITTED,
    RobotAutoAdmissionFacts,
    RobotAutoAdmissionResult,
    evaluate_auto_admission,
    record_auto_decision,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    PersistenceError,
    RobotAutoDecisionRecord,
    RobotCandidateRecord,
    SQLiteStore,
)


SOURCE_SCANNER = "SCANNER"  # immutable Wedge / L-shape JSON candidate
SOURCE_BOX_PLAN = "BOX_PLAN"  # immutable BOX_PLAN_ONLY SQLite source
SHADOW_MODE = "SHADOW"
PAPER_AUTO_MODE = "PAPER_AUTO"
_TERMINAL_STATUSES = {"EXPIRED", "INVALIDATED"}
_ACTIVE_STATUSES = ("APPROVED", "OPEN")
# A6, PROVISIONAL (no owner-approved value yet): an idea stays fresh for this many
# closed source candles after its first audited evaluation. 2 candles outlast one
# 60 s S2 ingress-health window on a 1m source; +1 margin. Not a trading parameter.
WAIT_REEVALUATION_CANDLES = 3


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    facts: RobotAutoAdmissionFacts
    result: RobotAutoAdmissionResult
    decision: RobotAutoDecisionRecord
    created: bool


@dataclass(frozen=True, slots=True)
class PaperAutoAdmission:
    facts: RobotAutoAdmissionFacts
    result: RobotAutoAdmissionResult
    decision: RobotAutoDecisionRecord
    decision_created: bool
    candidate: RobotCandidateRecord | None
    candidate_created: bool


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


def _candle_ms(timeframe: str) -> int | None:
    text = str(timeframe).strip()
    return int(text) * 60_000 if text.isdecimal() and int(text) > 0 else None


def _candidate_stale(
    decisions: tuple[RobotAutoDecisionRecord, ...], candidate_ref: str,
    source_identity: str, timeframe: str, now_ms: int,
) -> bool:
    """Age of one immutable idea since its first audited evaluation, in any mode."""
    first = min((item.evaluated_at_ms for item in decisions
                 if item.candidate_ref == candidate_ref
                 and item.source_identity == source_identity), default=None)
    if first is None:
        return False  # first evaluation happens at arrival, the decision time
    candle = _candle_ms(timeframe)
    if candle is None:
        return True  # freshness cannot be proven without a source candle
    return now_ms // candle - first // candle > WAIT_REEVALUATION_CANDLES


def _latest_decision(
    decisions: tuple[RobotAutoDecisionRecord, ...], candidate_ref: str,
    source_identity: str, mode: str,
) -> RobotAutoDecisionRecord | None:
    matching = [item for item in decisions
                if item.candidate_ref == candidate_ref
                and item.source_identity == source_identity
                and item.mode == mode and item.policy_version == POLICY_VERSION]
    return matching[-1] if matching else None  # ordered by evaluation time


def _wait_reevaluation_due(
    last: RobotAutoDecisionRecord, now_ms: int, *state_records: Any,
) -> bool:
    """True only for a WAIT with a new closed source candle or a state transition."""
    if last.outcome != OUTCOME_WAIT or last.reason_code == REASON_ALREADY_ADMITTED:
        return False
    if now_ms <= last.evaluated_at_ms:
        return False
    candle = _candle_ms(last.timeframe)
    if candle is not None and now_ms // candle > last.evaluated_at_ms // candle:
        return True
    # Durable Robot runtime / Autopilot rows change only on real transitions.
    return any(record is not None
               and last.evaluated_at_ms < record.updated_at_ms <= now_ms
               for record in state_records)


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
    snapshot_sha = candidate_snapshot_sha256(snapshot)
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


def _resolve_candidate(
    store: SQLiteStore, account: TradingAccountId, *, source: str,
    candidate_ref: str, candidate_store_dir: Path | str | None,
) -> _Candidate:
    if source == SOURCE_SCANNER:
        return _scanner_candidate(store, candidate_ref, candidate_store_dir)
    if source == SOURCE_BOX_PLAN:
        return _box_plan_candidate(store, candidate_ref, account)
    raise ValueError(f"unknown Autopilot source: {source!r}")


def _without_own_shadow_reservation(
    portfolio: dict, candidate: _Candidate, prior_allow: RobotAutoDecisionRecord | None,
) -> dict:
    """Convert one matching virtual SHADOW RO instead of spending it twice."""
    if prior_allow is None or candidate.already_admitted or portfolio.get("available") is not True:
        return portfolio
    identity = "shadow:" + candidate.ref
    reservations = list(portfolio.get("reservations") or ())
    own = [row for row in reservations if row.get("identity") == identity]
    if len(own) != 1:
        adjusted = dict(portfolio)
        adjusted.update(
            available=False,
            data_error="matching SHADOW capital reservation is unavailable",
        )
        return adjusted
    kept = [row for row in reservations if row.get("identity") != identity]
    occupied_ro = sum(row["ro"] for row in kept)
    adjusted = dict(portfolio)
    adjusted.update(
        reservations=kept,
        occupied_ro=occupied_ro,
        occupied_usdt=occupied_ro * adjusted["ro_usdt"],
        owned_symbols=sorted({row["symbol"] for row in kept}),
    )
    return adjusted


def _fresh_facts(
    store: SQLiteStore, account: TradingAccountId, *, mode: str, candidate: _Candidate,
    decisions: tuple[RobotAutoDecisionRecord, ...],
    protection_healthy: Callable[[], bool] | None, now_ms: int,
    prior_shadow_allow: RobotAutoDecisionRecord | None = None,
) -> RobotAutoAdmissionFacts:
    portfolio = collect_portfolio_facts(store, account)
    portfolio = _without_own_shadow_reservation(portfolio, candidate, prior_shadow_allow)
    portfolio["audit_sequence"] = len(decisions) + 1
    runtime = store.get_robot_runtime_state(account)
    try:
        healthy = None if protection_healthy is None else protection_healthy()
        healthy = None if healthy is None else bool(healthy)
    except Exception:
        healthy = None
    return RobotAutoAdmissionFacts(
        autopilot_mode=mode,
        environment="PAPER",
        robot_mode=runtime.mode if runtime is not None else None,
        robot_recovery_status=runtime.recovery_status if runtime is not None else None,
        candidate_valid=candidate.valid,
        candidate_executable=candidate.executable,
        candidate_stale=_candidate_stale(
            decisions, candidate.ref, candidate.source_identity, candidate.timeframe, now_ms,
        ),
        candidate_invalidated=candidate.invalidated,
        already_admitted=candidate.already_admitted,
        reconciliation_clear=(
            runtime is not None and runtime.recovery_status != "RECONCILIATION_REQUIRED"
        ),
        symbol_owned=(_symbol_owned(store, account, candidate)
                      or candidate.symbol.value in portfolio.get("owned_symbols", [])),
        protection_healthy=healthy,
        portfolio_policy_ready=True,
        portfolio_facts=portfolio,
    )


def _observe_shadow_candidate_locked(
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
    A candidate already decided for the same immutable snapshot is not written again,
    except a WAIT that is due for its bounded A6 reevaluation.
    """
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != SHADOW_MODE:
        return None
    candidate = _resolve_candidate(
        store, account, source=source, candidate_ref=candidate_ref,
        candidate_store_dir=candidate_store_dir,
    )

    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    decisions = store.load_robot_auto_decisions(account)
    existing = _latest_decision(decisions, candidate.ref, candidate.source_identity, state.mode)
    if existing is not None and not _wait_reevaluation_due(
            existing, now, state, store.get_robot_runtime_state(account)):
        frozen_facts = RobotAutoAdmissionFacts(**json.loads(existing.facts_json))
        frozen_result = RobotAutoAdmissionResult(existing.outcome, existing.reason_code,
                                                 existing.policy_version)
        return ShadowObservation(frozen_facts, frozen_result, existing, False)

    facts = _fresh_facts(
        store, account, mode=state.mode, candidate=candidate, decisions=decisions,
        protection_healthy=protection_healthy, now_ms=now,
    )
    result = evaluate_auto_admission(facts)

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


def admit_paper_auto_candidate(
    store: SQLiteStore, account: TradingAccountId, *, allow_decision_id: str,
    source: str, protection_healthy: Callable[[], bool] | None = None,
    candidate_store_dir: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> PaperAutoAdmission | None:
    """Recheck one immutable SHADOW ALLOW and use canonical Robot admission.

    This S3 boundary is intentionally not connected to runtime mode controls.
    The A3 BEGIN IMMEDIATE transaction owns the fresh capital/runtime/ownership/
    protection snapshot, canonical candidate creation and immutable audit append.
    """
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != PAPER_AUTO_MODE:
        return None

    admission: PaperAutoAdmission
    scanner_legacy_ref: str | None = None
    with store.autopilot_decision_transaction():
        state = store.get_robot_autopilot_state(account)
        if state is None or state.mode != PAPER_AUTO_MODE:
            return None
        prior = store.get_robot_auto_decision(allow_decision_id)
        if (
            prior is None
            or prior.trading_account_id != account
            or prior.mode != SHADOW_MODE
            or prior.outcome != OUTCOME_ALLOW
            or prior.policy_version != POLICY_VERSION
        ):
            raise PersistenceError("a matching immutable SHADOW ALLOW is required")

        candidate = _resolve_candidate(
            store, account, source=source, candidate_ref=prior.candidate_ref,
            candidate_store_dir=candidate_store_dir,
        )
        if (
            candidate.source_identity != prior.source_identity
            or candidate.snapshot_sha256 != prior.snapshot_sha256
        ):
            raise PersistenceError("SHADOW ALLOW immutable candidate identity changed")

        now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
        decisions = store.load_robot_auto_decisions(account)
        existing = _latest_decision(
            decisions, candidate.ref, candidate.source_identity, PAPER_AUTO_MODE,
        )
        if existing is not None and not _wait_reevaluation_due(
                existing, now, state, store.get_robot_runtime_state(account)):
            facts = RobotAutoAdmissionFacts(**json.loads(existing.facts_json))
            result = RobotAutoAdmissionResult(
                existing.outcome, existing.reason_code, existing.policy_version,
            )
            robot_candidate = (
                store.get_robot_candidate(existing.resulting_candidate_id)
                if existing.resulting_candidate_id is not None else None
            )
            if result.outcome == OUTCOME_ALLOW and robot_candidate is None:
                raise PersistenceError("PAPER_AUTO audit lost its canonical candidate")
            admission = PaperAutoAdmission(
                facts, result, existing, False, robot_candidate, False,
            )
        else:
            facts = _fresh_facts(
                store, account, mode=PAPER_AUTO_MODE, candidate=candidate,
                decisions=decisions, protection_healthy=protection_healthy,
                now_ms=now, prior_shadow_allow=prior,
            )
            result = evaluate_auto_admission(facts)
            robot_candidate = None
            candidate_created = False
            if result.outcome == OUTCOME_ALLOW:
                admission_ref = (
                    candidate.ref if source == SOURCE_SCANNER
                    else box_plan_admission_handle(candidate.ref)
                )
                robot_candidate, candidate_created = admit_robot_candidate(
                    admission_ref,
                    store_dir=candidate_store_dir,
                    clock_ms=lambda: now,
                    transaction_store=store,
                    expected_snapshot_sha256=candidate.snapshot_sha256,
                    mark_legacy_approved=False,
                )
            decision, decision_created = record_auto_decision(
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
                resulting_candidate_id=(
                    robot_candidate.candidate_id if robot_candidate is not None else None
                ),
            )
            admission = PaperAutoAdmission(
                facts, result, decision, decision_created,
                robot_candidate, candidate_created,
            )
        if source == SOURCE_SCANNER and admission.candidate is not None:
            scanner_legacy_ref = candidate.ref

    if scanner_legacy_ref is not None:
        approve_candidate(
            scanner_legacy_ref,
            approval={"source": PAPER_AUTO_MODE, "decision_id": admission.decision.decision_id},
            store_dir=candidate_store_dir,
        )
    return admission


def observe_shadow_candidate(
    store: SQLiteStore, account: TradingAccountId, *, source: str,
    candidate_ref: str, protection_healthy: Callable[[], bool] | None = None,
    candidate_store_dir: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
) -> ShadowObservation | None:
    # OFF/PAPER_AUTO: one mode read, no callback, collector or write transaction.
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != SHADOW_MODE:
        return None
    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)

    def observe(ref: str, ref_source: str) -> ShadowObservation | None:
        with store.autopilot_decision_transaction():
            return _observe_shadow_candidate_locked(
                store, account, source=ref_source, candidate_ref=ref,
                protection_healthy=protection_healthy,
                candidate_store_dir=candidate_store_dir, clock_ms=lambda: now,
            )

    # A6: this arrival is the only trigger. Earlier still-fresh WAITs that are due
    # go first, in arrival order (First Eligible); each in its own short transaction.
    arrival = (str(candidate_ref), source)
    observation, observed = None, False
    for due in _due_wait_refs(store, account, state, now):
        if due == arrival:
            observation, observed = observe(*due), True
            continue
        try:
            observe(*due)
        except Exception as error:  # an old WAIT must never block the arrival
            print(
                "[AUTOPILOT SHADOW WAIT REEVALUATION ERROR] "
                f"candidate_ref={due[0]} error_class={type(error).__name__}"
            )
    return observation if observed else observe(*arrival)


def _due_wait_refs(
    store: SQLiteStore, account: TradingAccountId, state: Any, now_ms: int,
) -> list[tuple[str, str]]:
    """Fresh WAIT ideas due for reevaluation, oldest arrival first; read-only."""
    decisions = store.load_robot_auto_decisions(account)
    runtime = store.get_robot_runtime_state(account)
    latest: dict[tuple[str, str], RobotAutoDecisionRecord] = {}
    for item in decisions:
        if item.mode == state.mode and item.policy_version == POLICY_VERSION:
            latest[(item.candidate_ref, item.source_identity)] = item
    return [
        (last.candidate_ref,
         SOURCE_BOX_PLAN if last.pattern == "IKIGAI_BOX" else SOURCE_SCANNER)
        for last in latest.values()
        if _wait_reevaluation_due(last, now_ms, state, runtime)
        and not _candidate_stale(
            decisions, last.candidate_ref, last.source_identity, last.timeframe, now_ms)
    ]


def shadow_mode_or_off(mode: str) -> str:
    """Owner control for this slice: only OFF and SHADOW may be set."""
    normalized = str(mode).strip().upper()
    if normalized not in {"OFF", SHADOW_MODE}:
        raise ValueError("only OFF and SHADOW are supported; PAPER_AUTO is not available")
    return normalized
