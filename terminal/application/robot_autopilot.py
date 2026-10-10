"""Read-only Robot Autopilot policy and durable decision audit helpers.

Stage A intentionally has no admission or order mutation path. It evaluates
caller-supplied authoritative facts, then may append an immutable audit record.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    RobotAutoDecisionRecord,
    SQLiteStore,
)


POLICY_VERSION = "robot-autopilot-shadow-v0.3"

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
    portfolio = facts.portfolio_facts
    if not portfolio or portfolio.get("available") is not True:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
    occupied = portfolio.get("occupied_ro")
    if type(occupied) is not int or occupied < 0:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_DATA_UNAVAILABLE)
    if occupied + 1 > 19:
        return RobotAutoAdmissionResult(OUTCOME_WAIT, REASON_PORTFOLIO_AGGREGATE_CAP)
    return RobotAutoAdmissionResult(OUTCOME_ALLOW, REASON_ELIGIBLE)


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
