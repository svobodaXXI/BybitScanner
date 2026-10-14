"""Read-only Robot Autopilot policy and durable decision audit helpers.

Stage A intentionally has no admission or order mutation path. It evaluates
caller-supplied authoritative facts, then may append an immutable audit record.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from decimal import Decimal
import hashlib
import json
from typing import Any, Mapping, Sequence

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    RobotAutoDecisionRecord,
    SQLiteStore,
)


POLICY_VERSION = "robot-autopilot-shadow-v0.4"

OUTCOME_ALLOW = "ALLOW"
OUTCOME_WAIT = "WAIT"
OUTCOME_REJECT = "REJECT"

REASON_ELIGIBLE = "ELIGIBLE"
REASON_AUTOPILOT_OFF = "AUTOPILOT_OFF"
REASON_AUTOPILOT_MODE_INVALID = "AUTOPILOT_MODE_INVALID"
REASON_LIVE_NOT_ALLOWED = "LIVE_NOT_ALLOWED"
REASON_CANDIDATE_INVALID = "CANDIDATE_INVALID"
REASON_CANDIDATE_NOT_EXECUTABLE = "CANDIDATE_NOT_EXECUTABLE"
REASON_CANDIDATE_STALE = "CANDIDATE_STALE"
REASON_CANDIDATE_FRESHNESS_UNKNOWN = "CANDIDATE_FRESHNESS_UNKNOWN"
REASON_CANDIDATE_INVALIDATED = "CANDIDATE_INVALIDATED"
REASON_ALREADY_ADMITTED = "ALREADY_ADMITTED"
REASON_ROBOT_NOT_READY = "ROBOT_NOT_READY"
REASON_RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
REASON_SYMBOL_OWNED = "SYMBOL_OWNED"
REASON_PROTECTION_UNHEALTHY = "PROTECTION_UNHEALTHY"
REASON_PROTECTION_HEALTH_UNKNOWN = "PROTECTION_HEALTH_UNKNOWN"
REASON_PORTFOLIO_POLICY_UNSET = "PORTFOLIO_POLICY_UNSET"
REASON_PORTFOLIO_DATA_UNAVAILABLE = "PORTFOLIO_DATA_UNAVAILABLE"
REASON_PORTFOLIO_AGGREGATE_CAP = "PORTFOLIO_AGGREGATE_CAP"
REASON_DAILY_EQUITY_UNAVAILABLE = "DAILY_EQUITY_UNAVAILABLE"
REASON_DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"

# AUTOPILOT-DAILY-GATE-1 (owner decision): PAPER_AUTO daily-loss gate on the proven
# 00:00 MSK equity baseline. Block at <= -10%; once blocked, resume only strictly
# above -7% (hysteresis). A new MSK business day starts unblocked.
DAILY_LOSS_BLOCK_PCT = Decimal("-10")
DAILY_LOSS_RESUME_PCT = Decimal("-7")
# The ONLY way to disable the gate: this exact value in the PAPER runtime's environment
# (owner debugging of PAPER strategies). Anything else, including unset, keeps it on.
DAILY_LOSS_GATE_ENV = "BYBITSCANNER_PAPER_DAILY_LOSS_GATE"
DAILY_LOSS_GATE_DISABLED_VALUE = "DISABLED_FOR_PAPER_DEBUG"


@dataclass(frozen=True, slots=True)
class RobotAutoAdmissionFacts:
    autopilot_mode: str
    environment: str
    robot_mode: str | None
    robot_recovery_status: str | None
    candidate_valid: bool
    candidate_executable: bool
    candidate_stale: bool
    candidate_invalidated: bool
    already_admitted: bool
    reconciliation_clear: bool
    symbol_owned: bool
    # None: no authoritative protection-health source -> WAIT, never assumed healthy.
    protection_healthy: bool | None
    portfolio_policy_ready: bool
    portfolio_facts: dict | None = None
    # A7, PAPER_AUTO only. True/False only from authoritative evidence that the
    # idea is still live; None means it could not be proven -> WAIT, never ALLOW.
    candidate_fresh: bool | None = None
    # PAPER_AUTO only: daily-loss gate facts computed in the admission transaction
    # (see ``daily_loss_gate_facts``). None in PAPER_AUTO -> WAIT, never ALLOW.
    daily_loss_gate: dict | None = None


@dataclass(frozen=True, slots=True)
class RobotAutoAdmissionResult:
    outcome: str
    reason_code: str
    policy_version: str = POLICY_VERSION


def evaluate_auto_admission(
    facts: RobotAutoAdmissionFacts,
) -> RobotAutoAdmissionResult:
    """Pure deterministic pre-admission policy; never mutates candidate/runtime state."""

    if facts.autopilot_mode not in {"OFF", "SHADOW", "PAPER_AUTO"}:
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_AUTOPILOT_MODE_INVALID)
    if facts.autopilot_mode == "OFF":
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_AUTOPILOT_OFF)
    if facts.environment != "PAPER":
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_LIVE_NOT_ALLOWED)
    if not facts.candidate_valid:
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_CANDIDATE_INVALID)
    if not facts.candidate_executable:
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_CANDIDATE_NOT_EXECUTABLE)
    if facts.candidate_stale:
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_CANDIDATE_STALE)
    if facts.candidate_invalidated:
        return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_CANDIDATE_INVALIDATED)
    if facts.autopilot_mode == "PAPER_AUTO":
        # Read-only SHADOW stays observational; only a real automatic admission
        # has to prove, from authoritative evidence, that the idea is still live.
        if facts.candidate_fresh is None:
            return RobotAutoAdmissionResult(
                OUTCOME_WAIT, REASON_CANDIDATE_FRESHNESS_UNKNOWN)
        if not facts.candidate_fresh:
            return RobotAutoAdmissionResult(OUTCOME_REJECT, REASON_CANDIDATE_STALE)
    if facts.already_admitted:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_ALREADY_ADMITTED)
    if facts.robot_mode != "ROBOT_RUNNING" or facts.robot_recovery_status != "READY":
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_ROBOT_NOT_READY)
    if not facts.reconciliation_clear:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_RECONCILIATION_REQUIRED)
    if facts.symbol_owned:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_SYMBOL_OWNED)
    if facts.protection_healthy is None:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PROTECTION_HEALTH_UNKNOWN)
    if not facts.protection_healthy:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PROTECTION_UNHEALTHY)
    if not facts.portfolio_policy_ready:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_POLICY_UNSET)
    if facts.autopilot_mode == "PAPER_AUTO":
        # Account-level daily-loss gate after every candidate/Robot/protection gate (a
        # dead idea stays REJECT): always audited, enforced unless the owner explicitly
        # disabled it for PAPER debugging. Disabled skips only this gate.
        gate = facts.daily_loss_gate
        if not isinstance(gate, dict) or not isinstance(gate.get("enabled"), bool):
            return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_DAILY_EQUITY_UNAVAILABLE)
        if gate["enabled"]:
            if gate.get("latched") is None:
                return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_DAILY_EQUITY_UNAVAILABLE)
            if gate["latched"]:
                return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_DAILY_LOSS_LIMIT)
    portfolio = facts.portfolio_facts
    if not portfolio or portfolio.get("available") is not True:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
    occupied = portfolio.get("occupied_ro")
    if type(occupied) is not int or occupied < 0:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
    if occupied + 1 > 19:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
    return RobotAutoAdmissionResult(OUTCOME_ALLOW, REASON_ELIGIBLE)


def daily_loss_gate_enabled(environ: Mapping[str, str]) -> bool:
    """True unless the PAPER environment carries the exact owner disable value."""
    return environ.get(DAILY_LOSS_GATE_ENV) != DAILY_LOSS_GATE_DISABLED_VALUE


def _previous_latch(decisions: Sequence[Any], business_date: str) -> bool | None:
    """Latch of the newest audited PAPER_AUTO observation of the same MSK business day.

    The audit is append-only and written in the same BEGIN IMMEDIATE transaction as
    every gate evaluation, so this survives restarts and serializes concurrent
    admissions. A row that cannot be read is a contradiction -> raises.
    """
    for decision in reversed(decisions):
        if decision.mode != "PAPER_AUTO":
            continue
        gate = json.loads(decision.facts_json or "{}").get("daily_loss_gate")
        if not isinstance(gate, dict) or gate.get("business_date_msk") != business_date:
            continue
        latched = gate.get("latched")
        if latched is None:
            continue  # an unavailable observation carries no latch information
        if not isinstance(latched, bool):
            raise ValueError("audited daily-loss latch is malformed")
        return latched
    return None


def daily_loss_gate_facts(
    equity: Any, decisions: Sequence[Any], *, enabled: bool,
) -> dict:
    """Audit-ready gate facts from fresh ``PaperDailyEquityFacts``.

    ``latched`` is True (blocked), False (open) or None (no proven daily equity and no
    same-day latch). Same-day blocked stays blocked while unavailable.
    """
    previous = _previous_latch(decisions, equity.business_date_msk)
    pct = equity.daily_change_pct
    if not equity.data_available or not isinstance(pct, Decimal):
        latched = True if previous is True else None
        transition = None
    elif pct <= DAILY_LOSS_BLOCK_PCT:
        latched = True
        transition = "BLOCKED" if previous is not True else None
    elif previous is True and pct <= DAILY_LOSS_RESUME_PCT:
        latched, transition = True, None
    else:
        latched = False
        transition = "RESUMED" if previous is True else None

    def text(value):
        return None if value is None else str(value)

    return {
        "enabled": bool(enabled),
        "business_date_msk": equity.business_date_msk,
        "day_start_ms": equity.day_start_ms,
        "as_of_ms": equity.as_of_ms,
        "baseline_equity_usdt": text(equity.baseline_equity_usdt),
        "current_adjusted_equity_usdt": text(equity.current_adjusted_equity_usdt),
        "daily_change_usdt": text(equity.daily_change_usdt),
        "daily_change_pct": text(pct),
        "data_available": bool(equity.data_available),
        "unavailability_reason": equity.unavailability_reason,
        "funding_model": equity.funding_model,
        "block_pct": str(DAILY_LOSS_BLOCK_PCT),
        "resume_pct": str(DAILY_LOSS_RESUME_PCT),
        "previous_latched": previous,
        "latched": latched,
        "transition": transition,
    }


def record_auto_decision(
    store: SQLiteStore,
    *,
    trading_account_id: TradingAccountId,
    candidate_ref: str,
    pattern: str,
    symbol: Symbol,
    timeframe: str,
    source_identity: str,
    snapshot_sha256: str | None,
    facts: RobotAutoAdmissionFacts,
    result: RobotAutoAdmissionResult,
    evaluated_at_ms: int,
    resulting_candidate_id: str | None = None,
) -> tuple[RobotAutoDecisionRecord, bool]:
    """Append one immutable SHADOW/PAPER_AUTO policy decision.

    This helper deliberately has no import of Robot admission/execution modules.
    A resulting candidate id is accepted only from the caller's canonical transaction.
    """

    if facts.autopilot_mode not in {"SHADOW", "PAPER_AUTO"}:
        raise ValueError("OFF decisions are not written to the Autopilot audit")
    if result.policy_version != POLICY_VERSION:
        raise ValueError("unsupported Robot Autopilot policy version")
    identity = "\0".join(
        (
            trading_account_id.value,
            candidate_ref,
            source_identity,
            facts.autopilot_mode,
            result.policy_version,
            str(evaluated_at_ms),
        )
    )
    decision_id = "auto-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    record = RobotAutoDecisionRecord(
        decision_id=decision_id,
        trading_account_id=trading_account_id,
        candidate_ref=candidate_ref,
        pattern=pattern,
        symbol=symbol,
        timeframe=str(timeframe).strip(),
        source_identity=source_identity,
        snapshot_sha256=snapshot_sha256,
        mode=facts.autopilot_mode,
        policy_version=result.policy_version,
        outcome=result.outcome,
        reason_code=result.reason_code,
        evaluated_at_ms=evaluated_at_ms,
        resulting_candidate_id=resulting_candidate_id,
        facts_json=json.dumps(asdict(facts), sort_keys=True, separators=(",", ":")),
    )
    return store.append_robot_auto_decision(record)
