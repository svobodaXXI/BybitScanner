"""MIRROR-INTEGRATION-1: read-only Robot handoff contract.

This module never creates candidates, orders, or position/STOP/TAKE changes.
A future common Robot adapter must separately establish account risk, durable
ownership, execution authority and an owner-approved PAPER acceptance gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from geometry.naked_retest import (
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
    PHASE_RETEST_UNPROVEN,
)
from retest_campaign import CampaignBudget, entry_gate, campaign_exit_intent

STRATEGY_ID = "MIRROR_RETEST"
MODE_OBSERVE_ONLY = "OBSERVE_ONLY"


@dataclass(frozen=True)
class MirrorRobotObservation:
    strategy_id: str
    boundary_id: str
    phase: str
    campaign_direction: str | None
    risk_decision: str
    risk_reason: str
    exit_intent: str | None
    executable: bool = False
    admission_allowed: bool = False
    mode: str = MODE_OBSERVE_ONLY


def observe_for_robot(
    *,
    boundary_id: str,
    state: Mapping[str, Any],
    budget: CampaignBudget | None = None,
    data_reliable: bool = False,
    realized_loss_costs_usdt: Any = None,
    live_pending_worst_case_usdt: Any = None,
    new_attempt_worst_case_usdt: Any = None,
    remaining_net_reward_usdt: Any = None,
) -> MirrorRobotObservation:
    """Present research policy to the Robot boundary without any execution path.

    A policy ALLOW is *not* Robot admission: R0/account authorization,
    symbol ownership, fills, protective orders and durability are unproven.
    """
    if not isinstance(boundary_id, str) or not boundary_id.strip():
        raise ValueError("nonempty boundary_id required")
    if not isinstance(state, Mapping) or state.get("boundary_id") != boundary_id:
        raise ValueError("state/boundary mismatch")
    phase = state.get("phase")
    if phase not in {PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN, PHASE_RETEST_UNPROVEN}:
        raise ValueError("unsupported campaign phase")
    breakout = state.get("breakout")
    if not isinstance(breakout, Mapping):
        raise ValueError("missing breakout evidence")
    direction = breakout.get("campaign_direction")
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("invalid campaign direction")

    risk_decision, risk_reason = "WAIT", "robot_execution_not_authorized"
    if phase == PHASE_CAMPAIGN_ACTIVE and budget is not None:
        result = entry_gate(
            budget,
            campaign_phase=phase,
            data_reliable=data_reliable is True and state.get("data_blocked") is False,
            realized_loss_costs_usdt=realized_loss_costs_usdt,
            live_pending_worst_case_usdt=live_pending_worst_case_usdt,
            new_attempt_worst_case_usdt=new_attempt_worst_case_usdt,
            remaining_net_reward_usdt=remaining_net_reward_usdt,
        )
        risk_decision, risk_reason = result.decision, result.reason
    elif phase != PHASE_CAMPAIGN_ACTIVE:
        risk_decision, risk_reason = "DENY", "campaign_terminal"
    return MirrorRobotObservation(
        strategy_id=STRATEGY_ID,
        boundary_id=boundary_id,
        phase=phase,
        campaign_direction=direction,
        risk_decision=risk_decision,
        risk_reason=risk_reason,
        exit_intent=campaign_exit_intent(phase),
    )
