"""Offline research policy for one H-016 RETEST CAMPAIGN (MIRROR RETEST-2).

Owner decisions 2026-10-19 over ``geometry.naked_retest`` phases:

5. attempts are unlimited, but every new exposure must pass the campaign
   budget of DOCUMENTS/RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md section 5::

       realized_loss_costs + worst_case(live + pending + new)
           <= min(R0, 0.5 * P_remaining_net(t))

   realized profits never restore spent risk and the cap only shrinks;
6. 25% TAKE at the Box/L-shape standard target, 75% at the first retest; after
   a confirmed partial TAKE the remainder STOP moves to fee-inclusive
   break-even only while protection is preserved;
7. the first proven retest closes the remainder; overshoot is not traded;
8. after the retest only an independent confirmed signal with its own risk may
   start a new campaign; there is never an automatic reversal.

This module returns decisions and intents only. It computes no prices, fees,
quantities or orders and owns no position state: execution, fills, STOP/TAKE,
reconciliation and account/daily gates stay with the existing Robot. No
runtime module imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN


PARTIAL_TAKE_FRACTION = 0.25
RETEST_REMAINDER_FRACTION = 0.75
REMAINING_REWARD_SHARE = 0.5

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_WAIT = "WAIT"

EXIT_CLOSE_REMAINDER = "CLOSE_REMAINDER"
STOP_FEE_INCLUSIVE_BREAK_EVEN = "FEE_INCLUSIVE_BREAK_EVEN"
STOP_KEEP_CURRENT = "KEEP_CURRENT_STOP"


class RetestCampaignError(ValueError):
    """Raised when a budget input is present but cannot be trusted."""


def _usdt(value: Any, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise RetestCampaignError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise RetestCampaignError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        return None
    return number


@dataclass(frozen=True)
class CampaignBudget:
    """``R0`` frozen before the first entry and the running cap (never grows)."""

    r0_usdt: float
    cap_usdt: float


@dataclass(frozen=True)
class GateResult:
    decision: str
    reason: str
    budget: CampaignBudget


def open_campaign_budget(r0_usdt: Any) -> CampaignBudget:
    r0 = _usdt(r0_usdt, "r0_usdt")
    if r0 is None or r0 <= 0:
        raise RetestCampaignError("R0 must be a positive finite USDT amount")
    return CampaignBudget(r0, r0)


def entry_gate(
    budget: CampaignBudget,
    *,
    campaign_phase: str,
    realized_loss_costs_usdt: Any,
    live_pending_worst_case_usdt: Any,
    new_attempt_worst_case_usdt: Any,
    remaining_net_reward_usdt: Any,
) -> GateResult:
    """Admit one more attempt of the same campaign, or not.

    Any unknown (None / non-finite) input means ``WAIT`` with the budget
    unchanged. Only an active campaign accepts attempts: after the retest,
    an overshoot, or invalidation there is no entry (rules 7 and 8).
    """

    if campaign_phase != PHASE_CAMPAIGN_ACTIVE:
        return GateResult(DECISION_DENY, "campaign_not_active", budget)
    values = {
        "realized_loss_costs_usdt": _usdt(realized_loss_costs_usdt, "realized_loss_costs_usdt"),
        "live_pending_worst_case_usdt": _usdt(live_pending_worst_case_usdt, "live_pending_worst_case_usdt"),
        "new_attempt_worst_case_usdt": _usdt(new_attempt_worst_case_usdt, "new_attempt_worst_case_usdt"),
        "remaining_net_reward_usdt": _usdt(remaining_net_reward_usdt, "remaining_net_reward_usdt"),
    }
    unknown = sorted(name for name, value in values.items() if value is None)
    if unknown:
        return GateResult(DECISION_WAIT, "unknown:" + ",".join(unknown), budget)
    for name in ("realized_loss_costs_usdt", "live_pending_worst_case_usdt", "new_attempt_worst_case_usdt"):
        if values[name] < 0:
            raise RetestCampaignError(f"{name} must be a non-negative loss amount")

    reward = values["remaining_net_reward_usdt"]
    if reward <= 0:
        shrunk = CampaignBudget(budget.r0_usdt, min(budget.cap_usdt, 0.0))
        return GateResult(DECISION_DENY, "no_remaining_net_reward", shrunk)

    cap = min(budget.cap_usdt, budget.r0_usdt, REMAINING_REWARD_SHARE * reward)
    shrunk = CampaignBudget(budget.r0_usdt, cap)
    exposure = (
        values["realized_loss_costs_usdt"]
        + values["live_pending_worst_case_usdt"]
        + values["new_attempt_worst_case_usdt"]
    )
    if exposure <= cap:
        return GateResult(DECISION_ALLOW, "within_campaign_budget", shrunk)
    return GateResult(DECISION_DENY, "campaign_budget_exceeded", shrunk)


def remainder_stop_policy(*, partial_take_confirmed: Any, protection_preserved: Any) -> str:
    """Rule 6: fee-inclusive BE only after a confirmed partial TAKE with protection kept."""

    if partial_take_confirmed is True and protection_preserved is True:
        return STOP_FEE_INCLUSIVE_BREAK_EVEN
    return STOP_KEEP_CURRENT


def campaign_exit_intent(campaign_phase: str) -> str | None:
    """Rule 7: a proven first retest closes the remainder; nothing else is implied.

    No reversal intent exists (rule 8). ``RETEST_UNPROVEN`` and
    ``LEVEL_INVALIDATED`` stop new attempts but their remainder handling is
    not owner-defined, so no intent is returned for them.
    """

    return EXIT_CLOSE_REMAINDER if campaign_phase == PHASE_RETEST_PROVEN else None
