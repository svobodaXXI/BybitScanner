"""Offline research policy for one H-016 RETEST CAMPAIGN (MIRROR RETEST-2/3).

Owner decisions over ``geometry.naked_retest`` phases:

5. attempts are unlimited, but every new exposure must pass the campaign
   budget of DOCUMENTS/RETEST_BOX_CHAIN_IMPLEMENTATION_PLAN.md section 5::

       realized_loss_costs + worst_case(live + pending + new)
           <= min(R0, 0.5 * P_remaining_net(t))

   realized profits never restore spent risk and the cap only shrinks;
   unreliable data blocks any admission (RETEST-3 rule 2);
R0 (RETEST-3 rule 3) follows from the idea's own net potential and the
   account risk limit, is frozen before the first attempt and never restored;
6. 25% TAKE at the Box/L-shape standard target, 75% at the first retest; after
   a confirmed 25% TAKE the remainder STOP is placed where the whole trade's
   net PnL stays >= 0 after fees, funding, slippage and safe tick rounding,
   with continuous protection (RETEST-3 rule 4);
7. the first proven retest closes the remainder; overshoot is not traded;
8. after the retest only an independent confirmed signal with its own risk may
   start a new campaign; there is never an automatic reversal.

This module returns decisions, intents and one price proposal only. It
submits nothing and owns no position state: execution, fills, STOP/TAKE
placement, reconciliation and account/daily gates stay with the existing
Robot. Every money/price input is caller-supplied evidence; no risk number
is chosen here. No runtime module imports it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
import math
from typing import Any

from geometry.naked_retest import (
    CAMPAIGN_LONG,
    CAMPAIGN_SHORT,
    PHASE_CAMPAIGN_ACTIVE,
    PHASE_RETEST_PROVEN,
)


PARTIAL_TAKE_FRACTION = 0.25
RETEST_REMAINDER_FRACTION = 0.75
REMAINING_REWARD_SHARE = 0.5

DECISION_ALLOW = "ALLOW"
DECISION_DENY = "DENY"
DECISION_WAIT = "WAIT"

EXIT_CLOSE_REMAINDER = "CLOSE_REMAINDER"
STOP_NET_BREAK_EVEN = "NET_BREAK_EVEN_STOP"
STOP_KEEP_CURRENT = "KEEP_CURRENT_STOP"


class RetestCampaignError(ValueError):
    """Raised when an input is present but cannot be trusted."""


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


def freeze_campaign_r0(*, idea_potential_net_usdt: Any, account_risk_limit_usdt: Any) -> float | None:
    """R0 from the idea's after-cost potential and the account risk limit.

    ``min(account_risk_limit, 0.5 * idea_potential_net)`` — the plan cap at the
    first attempt. Both inputs come from the caller (account policy and the
    frozen idea target); unknown or non-positive inputs return None, meaning no
    campaign may open.
    """

    potential = _usdt(idea_potential_net_usdt, "idea_potential_net_usdt")
    limit = _usdt(account_risk_limit_usdt, "account_risk_limit_usdt")
    if potential is None or limit is None or potential <= 0 or limit <= 0:
        return None
    return min(limit, REMAINING_REWARD_SHARE * potential)


def open_campaign_budget(r0_usdt: Any) -> CampaignBudget:
    r0 = _usdt(r0_usdt, "r0_usdt")
    if r0 is None or r0 <= 0:
        raise RetestCampaignError("R0 must be a positive finite USDT amount")
    return CampaignBudget(r0, r0)


def entry_gate(
    budget: CampaignBudget,
    *,
    campaign_phase: str,
    data_reliable: Any,
    realized_loss_costs_usdt: Any,
    live_pending_worst_case_usdt: Any,
    new_attempt_worst_case_usdt: Any,
    remaining_net_reward_usdt: Any,
) -> GateResult:
    """Admit one more attempt of the same campaign, or not.

    ``data_reliable`` must be exactly True (e.g. ``not state["data_blocked"]``
    with trusted market/fill evidence); anything else, or any unknown amount,
    means ``WAIT`` with the budget unchanged. Only an active campaign accepts
    attempts: after the retest or an overshoot there is no entry (rules 7, 8).
    """

    if campaign_phase != PHASE_CAMPAIGN_ACTIVE:
        return GateResult(DECISION_DENY, "campaign_not_active", budget)
    if data_reliable is not True:
        return GateResult(DECISION_WAIT, "data_unreliable", budget)
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


@dataclass(frozen=True)
class RemainderStopPlan:
    decision: str
    reason: str
    stop_price: Decimal | None = None
    worst_case_net_pnl_usdt: Decimal | None = None


def _dec(value: Any, field: str, *, positive: bool = False, non_negative: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise RetestCampaignError(f"{field} must be a finite Decimal")
    if positive and value <= 0:
        raise RetestCampaignError(f"{field} must be positive")
    if non_negative and value < 0:
        raise RetestCampaignError(f"{field} must be non-negative")
    return value


def _trade_net_pnl(direction, qty, entry, entry_fees, partial_qty, partial_price, partial_fees,
                   funding, fee_rate, slippage, stop):
    """Worst-case whole-trade net PnL if the remainder exits at ``stop``."""

    remainder = qty - partial_qty
    if direction == CAMPAIGN_LONG:
        fill = stop - slippage
        gross = partial_qty * (partial_price - entry) + remainder * (fill - entry)
    else:
        fill = stop + slippage
        gross = partial_qty * (entry - partial_price) + remainder * (entry - fill)
    return gross - entry_fees - partial_fees - funding - fee_rate * remainder * fill


def net_break_even_remainder_stop(
    *,
    campaign_direction: str,
    partial_take_confirmed: Any,
    protection_preserved: Any,
    current_stop_price: Decimal | None,
    mark_price: Decimal,
    entry_qty: Decimal,
    entry_avg_price: Decimal,
    entry_fees_usdt: Decimal,
    partial_qty: Decimal,
    partial_avg_price: Decimal,
    partial_fees_usdt: Decimal,
    funding_usdt: Decimal,
    remainder_exit_fee_rate: Decimal,
    slippage_price: Decimal,
    tick_size: Decimal,
) -> RemainderStopPlan:
    """Rule 6 (RETEST-3 rule 4): remainder STOP keeping whole-trade net PnL >= 0.

    LONG solves ``q1*(P1-E) + q2*(S-s-E) - fees - funding - r*q2*(S-s) >= 0``
    for S and rounds up to the tick; SHORT mirrors and rounds down. ``funding``
    is the net funding cost already paid plus any caller reserve; ``slippage``
    is the caller's adverse exit allowance. The proposal is returned only when
    it is placeable on the protective side of ``mark_price`` and tighter than
    the current STOP; otherwise the current, still-active protection is kept.
    """

    if partial_take_confirmed is not True:
        return RemainderStopPlan(STOP_KEEP_CURRENT, "partial_take_not_confirmed")
    if protection_preserved is not True or current_stop_price is None:
        return RemainderStopPlan(STOP_KEEP_CURRENT, "protection_not_preserved")
    if campaign_direction not in (CAMPAIGN_LONG, CAMPAIGN_SHORT):
        raise RetestCampaignError(f"unknown campaign direction: {campaign_direction!r}")

    current = _dec(current_stop_price, "current_stop_price", positive=True)
    mark = _dec(mark_price, "mark_price", positive=True)
    qty = _dec(entry_qty, "entry_qty", positive=True)
    entry = _dec(entry_avg_price, "entry_avg_price", positive=True)
    entry_fees = _dec(entry_fees_usdt, "entry_fees_usdt", non_negative=True)
    q1 = _dec(partial_qty, "partial_qty", positive=True)
    p1 = _dec(partial_avg_price, "partial_avg_price", positive=True)
    partial_fees = _dec(partial_fees_usdt, "partial_fees_usdt", non_negative=True)
    funding = _dec(funding_usdt, "funding_usdt")
    fee_rate = _dec(remainder_exit_fee_rate, "remainder_exit_fee_rate", non_negative=True)
    slippage = _dec(slippage_price, "slippage_price", non_negative=True)
    tick = _dec(tick_size, "tick_size", positive=True)
    if q1 >= qty:
        raise RetestCampaignError("partial_qty must leave a remainder")
    if fee_rate >= 1:
        raise RetestCampaignError("remainder_exit_fee_rate must be below 1")

    q2 = qty - q1
    costs = entry_fees + partial_fees + funding
    if campaign_direction == CAMPAIGN_LONG:
        raw = slippage + (q2 * entry + costs - q1 * (p1 - entry)) / (q2 * (1 - fee_rate))
        stop = (raw / tick).to_integral_value(rounding=ROUND_CEILING) * tick
        placeable = stop < mark
        tighter = stop > current
    else:
        raw = (q2 * entry - costs + q1 * (entry - p1)) / (q2 * (1 + fee_rate)) - slippage
        stop = (raw / tick).to_integral_value(rounding=ROUND_FLOOR) * tick
        placeable = stop > mark
        tighter = stop < current
    if stop <= 0:
        return RemainderStopPlan(STOP_KEEP_CURRENT, "no_positive_break_even_price")
    net = _trade_net_pnl(campaign_direction, qty, entry, entry_fees, q1, p1, partial_fees,
                         funding, fee_rate, slippage, stop)
    if net < 0:  # defensive: rounding is directional, so this must not happen
        raise RetestCampaignError("rounded break-even STOP does not keep net PnL >= 0")
    if not placeable:
        return RemainderStopPlan(STOP_KEEP_CURRENT, "break_even_not_placeable_vs_mark", stop, net)
    if not tighter:
        return RemainderStopPlan(STOP_KEEP_CURRENT, "current_stop_already_tighter", stop, net)
    return RemainderStopPlan(STOP_NET_BREAK_EVEN, "net_pnl_non_negative", stop, net)


def campaign_exit_intent(campaign_phase: str) -> str | None:
    """Rule 7: a proven first retest closes the remainder; nothing else is implied.

    No reversal intent exists (rule 8). ``RETEST_UNPROVEN`` stops new attempts
    but its remainder handling is not owner-defined, so no intent is returned.
    """

    return EXIT_CLOSE_REMAINDER if campaign_phase == PHASE_RETEST_PROVEN else None
