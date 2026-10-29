"""Pure campaign transition for STOP reentry across Box, Wedge and MIRROR.

Not a persistence or order executor. Call only inside the canonical durable
single-writer Robot transaction after reconciling the previous STOP execution.
A new signal may have a different pattern but must preserve campaign thesis,
direction and frozen ownership identity. Admission still applies separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from terminal.application.stop_reentry_setup import LogicalSetup, qualify_logical_reentry

MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Attempt:
    candidate_id: str
    confirmed_stop_execution_id: str | None
    realized_loss_cost_usdt: Decimal


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    symbol: str
    direction: str
    frozen_risk_budget_usdt: Decimal
    attempts: tuple[Attempt, ...]


@dataclass(frozen=True)
class Transition:
    outcome: str
    reason: str
    campaign: Campaign


def propose_stop_retry(
    campaign: Campaign, *,
    candidate_id: str,
    symbol: str,
    direction: str,
    setup: LogicalSetup | None,
    prior_stop_execution_id: str | None,
    stop_proven_in_ledger: bool,
    no_open_or_pending: bool,
    robot_ready: bool,
    new_worst_case_loss_usdt: Decimal,
) -> Transition:
    """Produce a candidate reservation proposal, never submit an order.

    The caller must atomically persist the returned campaign with optimistic
    revision fencing, then pass the candidate through normal Robot Admission.
    `prior_stop_execution_id` must be validated against durable executions by
    the caller; this function enforces consistency with the campaign snapshot.
    """
    if not campaign.attempts or not campaign.campaign_id or not campaign.symbol:
        return Transition("WAIT", "campaign_history_unverified", campaign)
    if not candidate_id or not isinstance(candidate_id, str):
        return Transition("WAIT", "candidate_identity_missing", campaign)
    if any(a.candidate_id == candidate_id for a in campaign.attempts):
        return Transition("DUPLICATE", "candidate_already_reserved", campaign)
    if len(campaign.attempts) >= MAX_ATTEMPTS:
        return Transition("DENY", "retry_limit", campaign)
    if symbol != campaign.symbol or direction != campaign.direction:
        return Transition("DENY", "campaign_identity_mismatch", campaign)
    if no_open_or_pending is not True:
        return Transition("WAIT", "exposure_or_pending_entry", campaign)
    if robot_ready is not True:
        return Transition("WAIT", "robot_not_ready", campaign)
    if not isinstance(setup, LogicalSetup):
        return Transition("WAIT", "new_setup_proof_unavailable", campaign)
    last = campaign.attempts[-1]
    if (setup.signal_id != candidate_id
            or setup.previous_signal_id != last.candidate_id
            or setup.direction != direction
            or setup.campaign_direction != campaign.direction):
        return Transition("WAIT", "campaign_setup_lineage_unverified", campaign)
    qualified = qualify_logical_reentry(setup)
    if qualified.outcome != "ALLOW":
        return Transition(qualified.outcome, qualified.reason, campaign)
    if (
        not isinstance(prior_stop_execution_id, str)
        or not prior_stop_execution_id
        or last.confirmed_stop_execution_id != prior_stop_execution_id
        or stop_proven_in_ledger is not True
    ):
        return Transition("WAIT", "last_stop_unproven", campaign)
    if not isinstance(new_worst_case_loss_usdt, Decimal):
        return Transition("WAIT", "risk_not_proven", campaign)
    if not new_worst_case_loss_usdt.is_finite() or new_worst_case_loss_usdt <= 0:
        return Transition("WAIT", "risk_not_proven", campaign)
    budget = campaign.frozen_risk_budget_usdt
    if not isinstance(budget, Decimal) or not budget.is_finite() or budget <= 0:
        return Transition("WAIT", "campaign_budget_unproven", campaign)
    spent = Decimal("0")
    for attempt in campaign.attempts:
        amount = attempt.realized_loss_cost_usdt
        if not isinstance(amount, Decimal) or not amount.is_finite() or amount < 0:
            return Transition("WAIT", "prior_loss_unproven", campaign)
        spent += amount
    if spent + new_worst_case_loss_usdt > budget:
        return Transition("DENY", "cumulative_risk_exceeded", campaign)
    proposed = Campaign(
        campaign_id=campaign.campaign_id,
        symbol=campaign.symbol,
        direction=campaign.direction,
        frozen_risk_budget_usdt=campaign.frozen_risk_budget_usdt,
        attempts=campaign.attempts + (
            Attempt(candidate_id, None, Decimal("0")),
        ),
    )
    return Transition("ALLOW", "requires_atomic_reservation_and_admission", proposed)
