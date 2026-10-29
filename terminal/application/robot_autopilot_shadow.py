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
source candle or a durable Robot/Autopilot state transition. There is no
age-based expiration; an invalidated idea is rejected and never resumed.
ALLOW and REJECT stay frozen.

Facts come only from authoritative state. A fact without an authoritative
source is reported as such (WAIT with an exact reason), never assumed:
- protection health: the in-process coverage manager when bound, else unknown;
- portfolio policy: owner-approved fixed RO policy and account-scoped PAPER facts.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sqlite3
import time
import threading
from pathlib import Path
from typing import Any, Callable, Mapping

from pattern_robot_integration import is_robot_executable_signal
from robot_candidate_store import approve_candidate, load_candidate
from terminal.application.robot_admission import (
    active_robot_owner_candidate_ids,
    admit_robot_candidate,
    box_plan_source_admission_error,
    box_plan_admission_handle,
    candidate_snapshot_sha256,
    linked_mirror_parent_candidate,
    scanner_candidate_admission_error,
)
from terminal.application.robot_reentry_adapter import automatic_reentry_proposal
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW,
    OUTCOME_WAIT,
    POLICY_VERSION,
    REASON_ALREADY_ADMITTED,
    REASON_REENTRY_THESIS_UNPROVEN,
    RobotAutoAdmissionFacts,
    RobotAutoAdmissionResult,
    daily_loss_gate_facts,
    evaluate_auto_admission,
    record_auto_decision,
)
from terminal.application.paper_daily_equity import (
    MarkPrice, msk_day_start_ms, paper_daily_equity_facts_in_transaction,
)
from terminal.application.robot_portfolio import _source_terminal_identities, collect_portfolio_facts
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    DuplicateIdentity,
    PersistenceError,
    RobotAutoDecisionRecord,
    RobotCandidateRecord,
    ShadowCommitBusy,
    ShadowCommitStale,
    SQLiteStore,
    SHADOW_COMMIT_MAX_ROWS,
)


SOURCE_SCANNER = "SCANNER"  # immutable Wedge / L-shape JSON candidate
SOURCE_BOX_PLAN = "BOX_PLAN"  # immutable BOX_PLAN_ONLY SQLite source
SHADOW_MODE = "SHADOW"
PAPER_AUTO_MODE = "PAPER_AUTO"
_TERMINAL_STATUSES = {"EXPIRED", "INVALIDATED"}
_ACTIVE_STATUSES = ("APPROVED", "OPEN")
# P0: one arrival reevaluates at most this many due WAITs, oldest first, and stops
# at a candidate boundary once the batch has used its owner-thread time budget.
A6_DUE_WAIT_BATCH_LIMIT = 8
A6_DUE_WAIT_BATCH_BUDGET_S = 2.0
_monotonic = time.monotonic
# Fresh runtime mark prices for the daily-loss gate: (marks by symbol, maximum age ms).
DailyMarkProvider = Callable[[], tuple[Mapping[str, MarkPrice], int]]


def _daily_loss_gate(
    store: SQLiteStore, account: TradingAccountId, *, now_ms: int,
    decisions: tuple[RobotAutoDecisionRecord, ...], enabled: bool,
    daily_marks: DailyMarkProvider | None,
) -> dict:
    """PAPER_AUTO daily-loss facts from the caller's admission transaction."""
    marks: Mapping[str, MarkPrice] = {}
    max_age_ms = 0
    if daily_marks is not None:
        try:
            supplied, supplied_age = daily_marks()
            if type(supplied_age) is int and supplied_age >= 0:
                marks, max_age_ms = dict(supplied), supplied_age
        except Exception:
            marks, max_age_ms = {}, 0  # no proven mark -> unavailable for open positions
    equity = paper_daily_equity_facts_in_transaction(
        store, account, as_of_ms=now_ms, marks=marks, max_mark_age_ms=max_age_ms)
    return daily_loss_gate_facts(equity, decisions, enabled=enabled)

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


FreshnessProver = Callable[[str, dict], bool | None]


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
    snapshot: dict


def _candle_ms(timeframe: str) -> int | None:
    text = str(timeframe).strip()
    return int(text) * 60_000 if text.isdecimal() and int(text) > 0 else None


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
        snapshot=dict(snapshot or {}),
    )


def _box_plan_candidate(
    store: SQLiteStore, ref: str, account: TradingAccountId,
    robot_candidates: tuple[RobotCandidateRecord, ...] | None = None,
) -> _Candidate:
    source = store.get_robot_candidate(ref)
    if source is None:
        raise LookupError(f"Box plan source not found: {ref}")
    identity = source.signal_snapshot.get("identity") or {}
    if robot_candidates is None:
        robot_candidates = store.load_robot_candidates_for_box_source(account, source.candidate_id)
    linked = [
        item for item in robot_candidates
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
        snapshot=dict(source.signal_snapshot),
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
    batch: _BatchSnapshot | None = None,
) -> _Candidate:
    if source == SOURCE_SCANNER:
        return _scanner_candidate(store, candidate_ref, candidate_store_dir)
    if source == SOURCE_BOX_PLAN:
        return _box_plan_candidate(store, candidate_ref, account,
                                   None if batch is None else batch.robot_candidates())
    raise ValueError(f"unknown Autopilot source: {source!r}")


def resolve_autopilot_evidence_target(
    store: SQLiteStore, account: TradingAccountId, *, source: str, candidate_ref: str,
    candidate_store_dir: Path | str | None = None,
) -> tuple[str, dict] | None:
    """A8: (symbol, signal snapshot) whose closed candles must be prepared off the owner.

    Read-only. None unless the durable mode is PAPER_AUTO, because OFF and SHADOW
    never consume freshness evidence and must not cause market-data requests.
    """
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != PAPER_AUTO_MODE:
        return None
    candidate = _resolve_candidate(
        store, account, source=source, candidate_ref=str(candidate_ref),
        candidate_store_dir=candidate_store_dir,
    )
    return candidate.symbol.value, dict(candidate.snapshot)


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


def _physical_capital_only(portfolio: dict) -> dict:
    """PAPER_AUTO risk facts: virtual SHADOW reservations are not obligations.

    A SHADOW ALLOW is an immutable audit record of a rehearsal. Its virtual RO
    keeps constraining SHADOW itself, but it must never hold the aggregate cap
    or own a symbol for physical PAPER_AUTO. Only Robot/manual obligations
    remain. Nothing is deleted or rewritten: the audit and the collector still
    report the virtual reservations; this view merely does not count them.
    """
    if portfolio.get("available") is not True:
        return portfolio
    reservations = list(portfolio.get("reservations") or ())
    physical = [row for row in reservations if not str(row.get("identity", "")).startswith("shadow:")]
    isolated_ro = sum(row["ro"] for row in reservations) - sum(row["ro"] for row in physical)
    occupied_ro = sum(row["ro"] for row in physical)
    adjusted = dict(portfolio)
    adjusted.update(
        reservations=physical,
        occupied_ro=occupied_ro,
        occupied_usdt=occupied_ro * adjusted["ro_usdt"],
        owned_symbols=sorted({row["symbol"] for row in physical}),
        isolated_shadow_ro=isolated_ro,
    )
    return adjusted


class _BatchSnapshot:
    """One consistent SHADOW read set for one A6 batch, inside ONE decision transaction.

    BEGIN IMMEDIATE excludes every other writer and SHADOW appends only audit rows,
    so candidates and PAPER rows cannot change under the batch. The audit list and
    the virtual SHADOW reservations are advanced in memory after each append, exactly
    as a fresh ``collect_portfolio_facts`` would see them. Never kept across batches.

    P0 (RUN #3): only the semantically needed history is read, never the whole audit
    or candidate tables. ``decisions`` holds the first and latest decision of every
    idea plus every SHADOW ALLOW (latest lookups, due-WAIT order and reservations are
    unchanged); ``decision_count`` is the real audit size for ``audit_sequence``.
    Candidates exclude only frozen Box plans that nothing refers to, and are portfolio
    views: a full snapshot only across a handoff, which is all the batch reads.
    """

    def __init__(self, store: SQLiteStore, account: TradingAccountId):
        self._store, self._account = store, account
        self.decisions = list(store.load_robot_auto_decision_heads(
            account, keep_mode=SHADOW_MODE, keep_outcome=OUTCOME_ALLOW))
        self.decision_count = store.count_robot_auto_decisions(account)
        self._candidates: tuple[RobotCandidateRecord, ...] | None = None
        self._portfolio: dict | None = None

    def robot_candidates(self) -> tuple[RobotCandidateRecord, ...]:
        if self._candidates is None:
            self._candidates = self._store.load_robot_candidates_for_portfolio(
                self._account, plan_only_status="BOX_PLAN_ONLY")
        return self._candidates

    def portfolio(self) -> dict:
        if self._portfolio is None:
            self._portfolio = collect_portfolio_facts(
                self._store, self._account, robot_candidates=self.robot_candidates(),
                auto_decisions=tuple(self.decisions),
            )
        return self._portfolio

    def appended(self, decision: RobotAutoDecisionRecord, created: bool) -> None:
        if not created:
            return
        self.decisions.append(decision)
        self.decision_count += 1
        if (self._portfolio is not None and decision.mode == SHADOW_MODE
                and decision.outcome == OUTCOME_ALLOW):
            self._portfolio = self._with_shadow_reservation(self._portfolio, decision)

    def _with_shadow_reservation(self, portfolio: dict, decision: RobotAutoDecisionRecord) -> dict:
        """Mirror the collector's SHADOW ALLOW rule for one new unlinked selection."""
        if portfolio.get("available") is not True:
            return portfolio
        ref = decision.candidate_ref
        identity, symbol = "shadow:" + ref, decision.symbol.value
        reservations = list(portfolio.get("reservations") or ())
        previous = next((row for row in reservations if row["identity"] == identity), None)
        if previous is not None and previous["symbol"] == symbol:
            return portfolio  # the collector keeps one reservation per identity
        if previous is not None or any(
                c.status != "BOX_PLAN_ONLY"
                and (c.candidate_id == ref or c.signal_snapshot.get("source_box_candidate_id") == ref)
                for c in self.robot_candidates()):
            # Linked real idea or identity conflict: the collector's full rules decide.
            return collect_portfolio_facts(
                self._store, self._account, robot_candidates=self.robot_candidates(),
                auto_decisions=tuple(self.decisions),
            )
        reservations.append({"identity": identity, "symbol": symbol, "ro": 1})
        occupied_ro = sum(row["ro"] for row in reservations)
        updated = dict(portfolio)
        updated.update(
            occupied_ro=occupied_ro,
            occupied_usdt=occupied_ro * portfolio["ro_usdt"],
            owned_symbols=sorted({*portfolio.get("owned_symbols", ()), symbol}),
            reservations=sorted(reservations, key=lambda row: row["identity"]),
        )
        return updated


def _proven_source_terminal(store: SQLiteStore, account: TradingAccountId, candidate: _Candidate) -> bool:
    if candidate.snapshot_sha256 is None:
        return False
    identities, _status = _source_terminal_identities(store, account)
    return (candidate.ref, candidate.snapshot_sha256) in identities


def _fresh_facts(
    store: SQLiteStore, account: TradingAccountId, *, mode: str, candidate: _Candidate,
    decisions: tuple[RobotAutoDecisionRecord, ...],
    protection_healthy: Callable[[], bool] | None,
    candidate_fresh: FreshnessProver | None = None,
    prior_shadow_allow: RobotAutoDecisionRecord | None = None,
    batch: _BatchSnapshot | None = None,
    now_ms: int | None = None,
    decision_count: int | None = None,
    daily_loss_gate_enabled: bool = True,
    daily_marks: DailyMarkProvider | None = None,
) -> RobotAutoAdmissionFacts:
    portfolio = (collect_portfolio_facts(
        store, account, auto_decisions=decisions,
        robot_candidates=store.load_robot_candidates_for_portfolio(
            account, plan_only_status="BOX_PLAN_ONLY"),
    ) if batch is None
                 else dict(batch.portfolio()))  # the batch copy is never mutated here
    # S3 conversion first: it keeps its fail-closed "exactly one matching reservation" proof.
    portfolio = _without_own_shadow_reservation(portfolio, candidate, prior_shadow_allow)
    if mode == PAPER_AUTO_MODE:
        portfolio = _physical_capital_only(portfolio)
    # A batch holds a reduced decision read set; its count is the real audit size.
    count = (len(decisions) if decision_count is None else decision_count)
    portfolio["audit_sequence"] = (count if batch is None else batch.decision_count) + 1
    runtime = store.get_robot_runtime_state(account)
    try:
        healthy = None if protection_healthy is None else protection_healthy()
        healthy = None if healthy is None else bool(healthy)
    except Exception:
        healthy = None
    fresh: bool | None = None
    if mode == PAPER_AUTO_MODE and candidate_fresh is not None:
        try:
            proven = candidate_fresh(candidate.symbol.value, candidate.snapshot)
        except Exception:
            proven = None  # unprovable freshness is never an implicit ALLOW
        fresh = None if proven is None else bool(proven)
    daily_gate = None
    if mode == PAPER_AUTO_MODE and now_ms is not None:
        daily_gate = _daily_loss_gate(
            store, account, now_ms=now_ms, decisions=decisions,
            enabled=daily_loss_gate_enabled, daily_marks=daily_marks)
    linked_parent = None
    if mode == PAPER_AUTO_MODE and candidate.pattern == "IKIGAI_BOX":
        identity = candidate.snapshot.get("identity") or {}
        direction = str(identity.get("direction", "")) if isinstance(identity, Mapping) else ""
        linked_parent = linked_mirror_parent_candidate(
            store,
            account,
            candidate.symbol,
            direction,
            excluded_candidate_ids=candidate.own_ids,
        )
        if linked_parent is not None:
            # The Box is a subordinate attempt of the already-reserved Wedge
            # campaign, not a second independent Robot idea.
            portfolio["new_reserve_ro"] = 0
    symbol_owned = (
        _symbol_owned(store, account, candidate)
        or candidate.symbol.value in portfolio.get("owned_symbols", [])
    )
    return RobotAutoAdmissionFacts(
        autopilot_mode=mode,
        environment="PAPER",
        robot_mode=runtime.mode if runtime is not None else None,
        robot_recovery_status=runtime.recovery_status if runtime is not None else None,
        candidate_valid=candidate.valid,
        candidate_executable=candidate.executable,
        # No age-based expiry: only a durable source-terminal event for this exact
        # (ref, snapshot) identity proves the snapshot ended; other gates still apply.
        candidate_stale=_proven_source_terminal(store, account, candidate),
        candidate_invalidated=candidate.invalidated,
        already_admitted=candidate.already_admitted,
        reconciliation_clear=(
            runtime is not None and runtime.recovery_status != "RECONCILIATION_REQUIRED"
        ),
        symbol_owned=symbol_owned and linked_parent is None,
        protection_healthy=healthy,
        portfolio_policy_ready=True,
        portfolio_facts=portfolio,
        candidate_fresh=fresh,
        daily_loss_gate=daily_gate,
        linked_mirror_parent_candidate_id=(
            linked_parent.candidate_id if linked_parent is not None else None
        ),
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
    batch: _BatchSnapshot | None = None,
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
    if batch is None:
        batch = _BatchSnapshot(store, account)
    candidate = _resolve_candidate(
        store, account, source=source, candidate_ref=candidate_ref,
        candidate_store_dir=candidate_store_dir, batch=batch,
    )

    now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
    decisions = tuple(batch.decisions)
    existing = _latest_decision(decisions, candidate.ref, candidate.source_identity, state.mode)
    if existing is not None and not _wait_reevaluation_due(
            existing, now, state, store.get_robot_runtime_state(account)):
        frozen_facts = RobotAutoAdmissionFacts(**json.loads(existing.facts_json))
        frozen_result = RobotAutoAdmissionResult(existing.outcome, existing.reason_code,
                                                 existing.policy_version)
        return ShadowObservation(frozen_facts, frozen_result, existing, False)

    facts = _fresh_facts(
        store, account, mode=state.mode, candidate=candidate, decisions=decisions,
        protection_healthy=protection_healthy, batch=batch,
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
    batch.appended(decision, created)
    return ShadowObservation(facts, result, decision, created)


def _auto_reentry_proposal_for_candidate(
    store: SQLiteStore, account: TradingAccountId, *,
    source: str, candidate: _Candidate, now_ms: int,
):
    """Opt-in extension to the existing canonical admission only.

    Older deployments keep exactly their original admission behaviour.
    PAPER only; feature OFF until owner approves completed cross-pattern E2E.
    """
    if os.environ.get("BYBITSCANNER_STOP_REENTRY_AUTO", "").strip() != "1":
        return None
    if source not in {SOURCE_SCANNER, SOURCE_BOX_PLAN} or not candidate.valid:
        raise PersistenceError("unverified source cannot bypass reentry campaign")
    proposal = automatic_reentry_proposal(
        store, account, candidate_id=candidate.ref, symbol=candidate.symbol,
        snapshot=candidate.snapshot, now_ms=now_ms,
    )
    if proposal is None:
        # Never silently continue normal PAPER_AUTO admission while the
        # universal campaign risk fence is explicitly enabled. Unsupported
        # or ambiguous candidates wait, not become untracked first trades.
        raise PersistenceError("candidate has no verified reentry strategy proof")
    return proposal


def admit_paper_auto_candidate(
    store: SQLiteStore, account: TradingAccountId, *, allow_decision_id: str,
    source: str, protection_healthy: Callable[[], bool] | None = None,
    candidate_fresh: FreshnessProver | None = None,
    candidate_store_dir: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
    daily_loss_gate_enabled: bool = True,
    daily_marks: DailyMarkProvider | None = None,
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
        decisions = store.load_robot_auto_decisions_for_admission(
            account, candidate_ref=candidate.ref, source_identity=candidate.source_identity,
            policy_version=POLICY_VERSION, business_date_msk=msk_day_start_ms(now)[0])
        decision_count = store.count_robot_auto_decisions(account)
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
                candidate_fresh=candidate_fresh, prior_shadow_allow=prior,
                now_ms=now, decision_count=decision_count,
                daily_loss_gate_enabled=daily_loss_gate_enabled,
                daily_marks=daily_marks,
            )
            result = evaluate_auto_admission(facts)
            robot_candidate = None
            candidate_created = False
            if result.outcome == OUTCOME_ALLOW:
                try:
                    reentry_plan = _auto_reentry_proposal_for_candidate(
                        store, account, source=source, candidate=candidate,
                        now_ms=now,
                    )
                except PersistenceError:
                    # No candidate was admitted or reserved; keep the audit
                    # observation and let the next fresh signal retry.
                    result = RobotAutoAdmissionResult(
                        OUTCOME_WAIT, REASON_REENTRY_THESIS_UNPROVEN, POLICY_VERSION,
                    )
                else:
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
                        linked_mirror_parent_candidate_id=(
                            facts.linked_mirror_parent_candidate_id
                        ),
                        reentry=reentry_plan,
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


def admit_arrived_auto_candidate(
    store: SQLiteStore, account: TradingAccountId, *, source: str, candidate_ref: str,
    protection_healthy: Callable[[], bool] | None = None,
    candidate_fresh: FreshnessProver | None = None,
    candidate_store_dir: Path | str | None = None,
    clock_ms: Callable[[], int] | None = None,
    daily_loss_gate_enabled: bool = True,
    daily_marks: DailyMarkProvider | None = None,
) -> PaperAutoAdmission | None:
    """A7: evaluate one arrived candidate in PAPER_AUTO and admit it canonically.

    Same policy, same audit and the same ``admit_robot_candidate`` boundary as the
    owner's manual tap; no second execution engine, scheduler or order path. A
    recorded WAIT is re-evaluated under the A6 rule; ALLOW/REJECT stay terminal.
    Returns None unless durable Autopilot state is PAPER_AUTO.
    """
    state = store.get_robot_autopilot_state(account)
    if state is None or state.mode != PAPER_AUTO_MODE:
        return None

    scanner_legacy_ref: str | None = None
    with store.autopilot_decision_transaction():
        state = store.get_robot_autopilot_state(account)
        if state is None or state.mode != PAPER_AUTO_MODE:
            return None
        candidate = _resolve_candidate(
            store, account, source=source, candidate_ref=candidate_ref,
            candidate_store_dir=candidate_store_dir,
        )
        now = clock_ms() if clock_ms is not None else int(time.time() * 1000)
        decisions = store.load_robot_auto_decisions_for_admission(
            account, candidate_ref=candidate.ref, source_identity=candidate.source_identity,
            policy_version=POLICY_VERSION, business_date_msk=msk_day_start_ms(now)[0])
        decision_count = store.count_robot_auto_decisions(account)
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
            return PaperAutoAdmission(facts, result, existing, False, robot_candidate, False)

        facts = _fresh_facts(
            store, account, mode=PAPER_AUTO_MODE, candidate=candidate,
            decisions=decisions, protection_healthy=protection_healthy,
            candidate_fresh=candidate_fresh, now_ms=now, decision_count=decision_count,
            daily_loss_gate_enabled=daily_loss_gate_enabled, daily_marks=daily_marks,
        )
        result = evaluate_auto_admission(facts)
        robot_candidate = None
        candidate_created = False
        if result.outcome == OUTCOME_ALLOW:
            try:
                reentry_plan = _auto_reentry_proposal_for_candidate(
                    store, account, source=source, candidate=candidate,
                    now_ms=now,
                )
            except PersistenceError:
                # No candidate was admitted or reserved; keep the audit
                # observation and let the next fresh signal retry.
                result = RobotAutoAdmissionResult(
                    OUTCOME_WAIT, REASON_REENTRY_THESIS_UNPROVEN, POLICY_VERSION,
                )
            else:
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
                    linked_mirror_parent_candidate_id=(
                        facts.linked_mirror_parent_candidate_id
                    ),
                    reentry=reentry_plan,
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
            facts, result, decision, decision_created, robot_candidate, candidate_created,
        )
        if source == SOURCE_SCANNER and robot_candidate is not None:
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
    arrival = (str(candidate_ref), source)

    def observe(ref: str, ref_source: str, batch: _BatchSnapshot | None) -> ShadowObservation | None:
        return _observe_shadow_candidate_locked(
            store, account, source=ref_source, candidate_ref=ref,
            protection_healthy=protection_healthy,
            candidate_store_dir=candidate_store_dir, clock_ms=lambda: now, batch=batch,
        )

    # A6: this arrival is the only trigger. Earlier still-fresh WAITs that are due go
    # first, oldest evaluation first (First Eligible), at most one bounded batch per
    # arrival from one consistent read set; the rest stay due for the next arrival.
    # Protection/owner work waits at most one batch, never the whole WAIT backlog.
    arrival_error: Exception | None = None
    began = in_arrival = False
    try:
        with store.autopilot_decision_transaction():
            began = True
            state = store.get_robot_autopilot_state(account)
            if state is None or state.mode != SHADOW_MODE:
                return None
            def mark_arrival() -> None:
                nonlocal in_arrival
                in_arrival = True

            result, arrival_error = _run_a6_batch(
                store, account, state, now, arrival, observe, started=_monotonic(),
                on_arrival=mark_arrival)
            if arrival_error is None:
                return result
    except sqlite3.Error as error:
        if in_arrival or not began:
            raise  # busy BEGIN IMMEDIATE: one timeout, nothing written, WAITs stay due
        # The whole batch rolled back; nothing is lost, those WAITs stay due.
        print(
            "[AUTOPILOT SHADOW WAIT BATCH ERROR] "
            f"candidate_ref={arrival[0]} error_class={type(error).__name__}"
        )
        with store.autopilot_decision_transaction():
            return observe(*arrival, None)
    raise arrival_error


def _run_a6_batch(
    store: Any, account: TradingAccountId, state: Any, now: int, arrival: tuple[str, str],
    observe: Callable[..., ShadowObservation | None], *, started: float,
    on_arrival: Callable[[], None] | None = None,
) -> tuple[ShadowObservation | None, Exception | None]:
    """The A6 batch in audit order: due WAITs first, then the arrival. Shared by the owner
    path (inside one decision transaction) and the off-owner snapshot plan."""
    batch = _BatchSnapshot(store, account)
    due = [ref for ref in _due_wait_refs(
        batch.decisions, state, store.get_robot_runtime_state(account), now)
        if ref != arrival]
    for ref in due[:A6_DUE_WAIT_BATCH_LIMIT]:
        # The budget includes the batch reads above; an exhausted budget starts
        # no further WAIT evaluation (candidate boundary: written rows are complete).
        if _monotonic() - started >= A6_DUE_WAIT_BATCH_BUDGET_S:
            break
        try:
            observe(*ref, batch)
        except sqlite3.Error:
            raise
        except Exception as error:  # an old WAIT must never block the arrival
            print(
                "[AUTOPILOT SHADOW WAIT REEVALUATION ERROR] "
                f"candidate_ref={ref[0]} error_class={type(error).__name__}"
            )
    if on_arrival is not None:
        on_arrival()
    try:
        return observe(*arrival, batch), None
    except sqlite3.Error:
        raise
    except Exception as error:  # keep the completed batch, then report
        return None, error


# ---- Variant B (P0 RUN #3): SHADOW is evaluated OFF the owner thread ---------------------
#
# The calling thread (Scanner pass / Box preparation) reads one WAL snapshot on its own
# read-only connection (no write lock), runs the unchanged A6 evaluation there and builds
# the audit rows. The owner only checks Autopilot/Robot-runtime versions and the audit tail
# and writes at most SHADOW_COMMIT_MAX_ROWS rows per call with a short lock wait. Every
# conflict (OFF, STOP, a version or tail change, lock, expiry, protection change) writes
# nothing and the attempt is recomputed or dropped; the owner never evaluates.

SHADOW_COMMIT_LOCK_WAIT_MS = 100
SHADOW_DEFERRED_ATTEMPTS = 3
SHADOW_SNAPSHOT_MAX_AGE_S = 30.0  # a plan older than this (from the snapshot start) is never committed
SHADOW_COMMIT_EXPIRY_S = 1.0  # an owner call dequeued later than this after it was sent does nothing
DEFERRED_COMMITTED = "COMMITTED"
DEFERRED_HANDOVER = "HANDOVER"  # Autopilot is not SHADOW: the existing owner entry decides
DEFERRED_DROPPED = "DROPPED"  # nothing (more) was committed; the arrival has no SHADOW decision
_MIXED = object()


@dataclass(frozen=True, slots=True)
class ShadowChunk:
    """One bounded owner commit: <= SHADOW_COMMIT_MAX_ROWS rows and what they were computed from."""

    account: TradingAccountId
    records: tuple[RobotAutoDecisionRecord, ...]
    expected: tuple  # Autopilot state, Robot runtime state, audit tail at the snapshot
    expires_at: float  # monotonic; an owner that dequeues the call later writes nothing
    protection: Any  # the protection-health value the facts used (re-read on the owner)


@dataclass(frozen=True, slots=True)
class ShadowPlan:
    records: tuple[RobotAutoDecisionRecord, ...]
    expected: tuple
    full: tuple
    protection: Any
    arrival_error: Exception | None


class _RecordingStore:
    """Evaluation store for a snapshot plan: reads pass through, audit appends are recorded."""

    def __init__(self, reader: SQLiteStore, records: list[RobotAutoDecisionRecord]):
        self._reader, self._records = reader, records

    def __getattr__(self, name: str) -> Any:
        return getattr(self._reader, name)

    def append_robot_auto_decision(self, record: RobotAutoDecisionRecord):
        self._records.append(record)
        return record, True


def _normalized_health(provider: Callable[[], bool] | None) -> Any:
    try:
        healthy = None if provider is None else provider()
        return None if healthy is None else bool(healthy)
    except Exception:
        return None


def plan_shadow_observation(
    reader: SQLiteStore, account: TradingAccountId, *, source: str, candidate_ref: str,
    protection_healthy: Callable[[], bool] | None, candidate_store_dir: Path | str | None,
    now_ms: Callable[[], int],
) -> ShadowPlan | None:
    """Evaluate one arrival (and its due WAITs) in a read snapshot; ``None`` unless SHADOW."""
    arrival = (str(candidate_ref), source)
    with reader.read_snapshot():
        state = reader.get_robot_autopilot_state(account)
        if state is None or state.mode != SHADOW_MODE:
            return None
        full = reader.shadow_full_markers(account)
        expected = full[:3]
        # Never earlier than the audit tail: the audit order is (evaluated_at_ms, decision_id).
        now = max(int(now_ms()), int(json.loads(expected[2])[1]))
        records: list[RobotAutoDecisionRecord] = []
        recorder = _RecordingStore(reader, records)

        def observe(ref: str, ref_source: str, batch: _BatchSnapshot | None):
            return _observe_shadow_candidate_locked(
                recorder, account, source=ref_source, candidate_ref=ref,
                protection_healthy=protection_healthy,
                candidate_store_dir=candidate_store_dir, clock_ms=lambda: now, batch=batch,
            )

        _result, arrival_error = _run_a6_batch(
            recorder, account, state, now, arrival, observe, started=_monotonic())
    values = {json.loads(record.facts_json)["protection_healthy"] for record in records}
    protection = (next(iter(values)) if len(values) == 1 else (None if not values else _MIXED))
    return ShadowPlan(tuple(records), tuple(expected), tuple(full), protection, arrival_error)


def commit_shadow_chunk(
    store: SQLiteStore, chunk: ShadowChunk, *, protection_healthy: Callable[[], bool] | None,
    monotonic: Callable[[], float] = time.monotonic, lock_wait_ms: int = SHADOW_COMMIT_LOCK_WAIT_MS,
) -> str:
    """Owner thread: bounded freshness check and audit commit of one chunk. Never evaluates.

    Returns COMMITTED, EXPIRED, STALE, BUSY, CONFLICT or NOT_SHADOW; anything but
    COMMITTED wrote nothing.
    """
    if monotonic() > chunk.expires_at:
        return "EXPIRED"
    if chunk.protection is _MIXED or _normalized_health(protection_healthy) != chunk.protection:
        return "STALE"
    try:
        inserted = store.append_robot_auto_decisions_committed(
            chunk.records, expected=chunk.expected, lock_wait_ms=lock_wait_ms)
    except ShadowCommitBusy:
        return "BUSY"
    except ShadowCommitStale:
        state = store.get_robot_autopilot_state(chunk.account)
        return "NOT_SHADOW" if state is None or state.mode != SHADOW_MODE else "STALE"
    except DuplicateIdentity:
        return "CONFLICT"
    return "COMMITTED" if inserted == len(chunk.records) else "CONFLICT"


class ShadowDeferredObserver:
    """Variant B entry for one runtime: evaluate on the calling thread, commit via the owner.

    One lock serializes evaluations (arrivals keep their order; a second caller waits just as
    it waited in the owner queue). No thread is started. After ``attempts`` failed attempts
    the arrival is dropped with a log line: the owner never runs the evaluation instead.
    """

    def __init__(
        self, database_path: Path | str, account: TradingAccountId,
        commit: Callable[[ShadowChunk], str], *,
        protection_healthy: Callable[[], bool] | None = None,
        candidate_store_dir: Path | str | None = None,
        clock_ms: Callable[[], int] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        attempts: int = SHADOW_DEFERRED_ATTEMPTS,
        snapshot_max_age_s: float = SHADOW_SNAPSHOT_MAX_AGE_S,
        expiry_s: float = SHADOW_COMMIT_EXPIRY_S,
    ) -> None:
        self._path, self._account, self._commit = database_path, account, commit
        self._health, self._dir = protection_healthy, candidate_store_dir
        self._clock = clock_ms if clock_ms is not None else (lambda: int(time.time() * 1000))
        self._monotonic, self._attempts = monotonic, attempts
        self._max_age, self._expiry = snapshot_max_age_s, expiry_s
        self._lock = threading.Lock()
        # Per-process counters (a new process starts at zero): every arrival this observer
        # did not commit is counted as dropped, so a SHADOW run with dropped > 0 is incomplete.
        self._metrics_lock = threading.Lock()
        self._started_at_ms = int(time.time() * 1000)
        self._committed = 0
        self._dropped = 0
        self._last_drop: dict[str, Any] | None = None

    def observe(self, source: str, candidate_ref: str) -> str:
        with self._lock:
            outcome = "RETRY"
            for _ in range(self._attempts):
                try:
                    outcome = self._attempt(source, str(candidate_ref))
                except Exception as error:  # a SHADOW failure never reaches the caller
                    print(
                        "[AUTOPILOT SHADOW ERROR] "
                        f"source={source} candidate_ref={candidate_ref} "
                        f"error_class={type(error).__name__}"
                    )
                    self.record_drop(source, candidate_ref, f"ERROR_{type(error).__name__}")
                    return DEFERRED_DROPPED
                if outcome == DEFERRED_COMMITTED:
                    with self._metrics_lock:
                        self._committed += 1
                    return outcome
                if outcome == DEFERRED_HANDOVER:
                    return outcome
            self.record_drop(source, candidate_ref, f"ATTEMPTS_EXHAUSTED:{outcome}")
            return DEFERRED_DROPPED

    def record_drop(self, source: str, candidate_ref: str, reason: str) -> None:
        """Count one arrival without a SHADOW decision (any thread) and log it."""
        print(
            "[AUTOPILOT SHADOW DEFERRED DROPPED] "
            f"source={source} candidate_ref={candidate_ref} last={reason}"
        )
        with self._metrics_lock:
            self._dropped += 1
            self._last_drop = {
                "reason": reason, "source": source, "candidate_ref": str(candidate_ref),
                "at_ms": int(time.time() * 1000),
            }

    def metrics(self) -> dict[str, Any]:
        """Thread-safe snapshot; never waits for an evaluation or the owner."""
        with self._metrics_lock:
            return {
                "observer_started_at_ms": self._started_at_ms,
                "committed": self._committed,
                "dropped": self._dropped,
                "last_drop": None if self._last_drop is None else dict(self._last_drop),
            }

    def _attempt(self, source: str, candidate_ref: str) -> str:
        started = self._monotonic()
        reader = SQLiteStore.open_reader(self._path)
        try:
            try:
                plan = plan_shadow_observation(
                    reader, self._account, source=source, candidate_ref=candidate_ref,
                    protection_healthy=self._health, candidate_store_dir=self._dir,
                    now_ms=self._clock)
            except sqlite3.Error as error:
                return f"READ_{type(error).__name__}"
            if plan is None:
                return DEFERRED_HANDOVER
            # Everything the facts were computed from, unchanged since the snapshot (checked
            # here, off the owner); the owner re-checks the O(1) subset and the expiry.
            if (self._monotonic() - started > self._max_age
                    or reader.shadow_full_markers(self._account) != plan.full):
                return "STALE"
        finally:
            reader.close()
        rows, done, expected = plan.records, 0, plan.expected
        while done < len(rows):
            chunk_rows = rows[done:done + SHADOW_COMMIT_MAX_ROWS]
            chunk = ShadowChunk(
                self._account, tuple(chunk_rows), expected, self._monotonic() + self._expiry, plan.protection)
            try:
                status = self._commit(chunk)
            except Exception as error:  # e.g. the owner call timed out: its outcome is unknown
                return f"COMMIT_{type(error).__name__}"
            if status == "NOT_SHADOW":
                return DEFERRED_HANDOVER
            if status != "COMMITTED":
                return status
            done += len(chunk_rows)
            count, tail = json.loads(expected[2])
            expected = (expected[0], expected[1], json.dumps(
                [count + len(chunk_rows), max(tail, *(r.evaluated_at_ms for r in chunk_rows))],
                separators=(",", ":")))
        if plan.arrival_error is not None:
            print(
                "[AUTOPILOT SHADOW ERROR] "
                f"source={source} candidate_ref={candidate_ref} "
                f"error_class={type(plan.arrival_error).__name__}"
            )
        return DEFERRED_COMMITTED


def _due_wait_refs(
    decisions: tuple[RobotAutoDecisionRecord, ...] | list[RobotAutoDecisionRecord],
    state: Any, runtime: Any, now_ms: int,
) -> list[tuple[str, str]]:
    """Due WAIT ideas, oldest last evaluation first (ties: arrival order); pure."""
    latest: dict[tuple[str, str], RobotAutoDecisionRecord] = {}
    for item in decisions:
        if item.mode == state.mode and item.policy_version == POLICY_VERSION:
            latest[(item.candidate_ref, item.source_identity)] = item
    due = sorted((last for last in latest.values()
                  if _wait_reevaluation_due(last, now_ms, state, runtime)),
                 key=lambda last: last.evaluated_at_ms)
    refs = [(last.candidate_ref,
             SOURCE_BOX_PLAN if last.pattern == "IKIGAI_BOX" else SOURCE_SCANNER)
            for last in due]
    return list(dict.fromkeys(refs))


def shadow_mode_or_off(mode: str) -> str:
    """Owner control for OFF/SHADOW only; kept for callers that never automate."""
    normalized = str(mode).strip().upper()
    if normalized not in {"OFF", SHADOW_MODE}:
        raise ValueError("only OFF and SHADOW are supported; PAPER_AUTO is not available")
    return normalized


def owner_autopilot_mode(mode: str, *, environment: str, confirm_paper_auto: bool) -> str:
    """A7 owner control. PAPER_AUTO needs an explicit confirmation and a PAPER account.

    Enabling automation is an owner decision, never a side effect of a task, a
    restart or a passing gate; OFF and SHADOW stay available unconditionally.
    """
    normalized = str(mode).strip().upper()
    if normalized in {"OFF", SHADOW_MODE}:
        return normalized
    if normalized != PAPER_AUTO_MODE:
        raise ValueError("unsupported Robot Autopilot mode")
    if str(environment).strip().upper() != "PAPER":
        raise ValueError("PAPER_AUTO is available only for the PAPER account")
    if confirm_paper_auto is not True:
        raise ValueError("PAPER_AUTO requires an explicit owner confirmation")
    return PAPER_AUTO_MODE
