"""Fail-closed, side-effect-free STOP reentry eligibility for issue #592.

This is a policy primitive, NOT a runtime admission or order-entry path.
The durable attempt ledger, risk accounting and pattern-specific confirmation
must supply authoritative evidence before this can be wired into PAPER_AUTO.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_ATTEMPTS = 3  # one initial entry plus at most two STOP reentries
ALLOW = "ALLOW"
WAIT = "WAIT"
DENY = "DENY"


@dataclass(frozen=True)
class ReentryEvidence:
    """Snapshot from the canonical durable campaign and Robot authority.

    attempts_started includes the initial entry. Missing proof MUST NOT grant
    another entry. `stop_closed` means a filled previous attempt was closed
    by an authoritative STOP execution, not a touched candle or local estimate.
    """

    attempts_started: int
    previous_exit: str | None
    stop_closed: bool
    fresh_confirmed_signal: bool
    same_campaign_and_direction: bool
    campaign_valid: bool
    no_open_or_pending: bool
    robot_ready: bool
    risk_budget_ok: bool


@dataclass(frozen=True)
class ReentryDecision:
    outcome: str
    reason: str


def evaluate_stop_reentry(evidence: ReentryEvidence) -> ReentryDecision:
    """Pure precondition gate; ALLOW is never sufficient to place an order.

    The caller must still perform atomic ledger reservation, freshness,
    canonical Robot Admission, protection and account/daily risk checks.
    """

    count = evidence.attempts_started
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return ReentryDecision(WAIT, "attempt_history_unverified")
    if count >= MAX_ATTEMPTS:
        return ReentryDecision(DENY, "attempt_limit_reached")
    if evidence.previous_exit in {"TAKE", "INVALIDATED"}:
        return ReentryDecision(DENY, "campaign_terminal")
    if evidence.campaign_valid is not True:
        return ReentryDecision(DENY, "campaign_invalid")
    if evidence.previous_exit != "STOP" or evidence.stop_closed is not True:
        return ReentryDecision(WAIT, "stop_execution_unverified")
    if evidence.same_campaign_and_direction is not True:
        return ReentryDecision(WAIT, "campaign_identity_unverified")
    if evidence.fresh_confirmed_signal is not True:
        return ReentryDecision(WAIT, "new_signal_unconfirmed")
    if evidence.no_open_or_pending is not True:
        return ReentryDecision(WAIT, "exposure_or_entry_pending")
    if evidence.robot_ready is not True:
        return ReentryDecision(WAIT, "robot_not_ready")
    if evidence.risk_budget_ok is not True:
        return ReentryDecision(WAIT, "risk_budget_unverified")
    return ReentryDecision(ALLOW, "eligible_for_canonical_admission")
