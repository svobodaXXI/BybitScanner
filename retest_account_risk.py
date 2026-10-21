"""MIRROR RETEST R0: account-level risk limit and frozen campaign R0 (pure calculation).

RETEST-3 rule 11 / plan section 5: ``R0 = min(account risk limit, 0.5 * net idea potential)``
(``retest_campaign.freeze_campaign_r0``). This module supplies the missing
``account risk limit`` from facts the existing Robot already publishes, and adds
no new account-risk percentage:

* the only loss-denominated account gate is the PAPER daily-loss gate
  (``robot_autopilot.daily_loss_gate_facts``): it blocks at ``block_pct`` of the
  00:00 MSK baseline equity. The distance to that block is the account's loss
  headroom;
* what is already committed (worst-case loss to STOP of open positions and
  pending entries) is subtracted from it.

Pure functions over plain mappings: no database, runtime, order or network
access. Any unknown, malformed or non-finite input yields WAIT (fail-closed);
an exhausted limit yields DENY. Nothing here is Robot admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

from retest_campaign import DECISION_DENY, DECISION_WAIT, freeze_campaign_r0

DECISION_OK = "OK"
HUNDRED = Decimal(100)


@dataclass(frozen=True)
class AccountRiskLimit:
    decision: str            # OK | WAIT | DENY
    reason: str
    limit_usdt: Decimal | None = None
    headroom_usdt: Decimal | None = None
    committed_usdt: Decimal | None = None


@dataclass(frozen=True)
class FrozenR0:
    decision: str            # OK | WAIT | DENY
    reason: str
    r0_usdt: float | None = None
    account_limit: AccountRiskLimit | None = None


def _decimal(value: Any) -> Decimal | None:
    """Finite Decimal from str/int/Decimal, else None (bool and float are not accepted)."""

    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        return None
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def position_worst_case_loss_usdt(
    *, direction: Any, quantity: Any, entry_price: Any, stop_price: Any, fee_rate: Any,
) -> Decimal | None:
    """Worst-case loss to STOP incl. both-side fees: ``q * (|entry - stop| + fee * (entry + stop))``.

    Returns None (unknown) for a missing protective stop, a stop on the wrong side
    of the entry, or any non-positive / malformed input.
    """

    qty, entry, stop, fee = (_decimal(item) for item in (quantity, entry_price, stop_price, fee_rate))
    if direction not in {"LONG", "SHORT"} or None in (qty, entry, stop, fee):
        return None
    if not (qty > 0 and entry > 0 and stop > 0 and fee >= 0):
        return None
    if (direction == "LONG" and stop >= entry) or (direction == "SHORT" and stop <= entry):
        return None
    return qty * (abs(entry - stop) + fee * (entry + stop))


def daily_loss_headroom_usdt(daily_gate: Any) -> tuple[str, str, Decimal | None]:
    """Loss left before the daily-loss gate blocks: ``adjusted_equity - baseline * (1 + block_pct/100)``.

    ``daily_gate`` is the ``daily_loss_gate`` mapping of Autopilot decision facts. Returns
    ``(decision, reason, headroom)``.
    """

    if not isinstance(daily_gate, Mapping):
        return DECISION_WAIT, "daily_gate_unavailable", None
    if daily_gate.get("enabled") is not True:
        return DECISION_WAIT, "daily_gate_disabled", None
    if daily_gate.get("latched") is True:
        return DECISION_DENY, "daily_loss_latched", None
    if daily_gate.get("data_available") is not True:
        return DECISION_WAIT, "daily_gate_data_unavailable", None
    if daily_gate.get("latched") is not False:
        return DECISION_WAIT, "daily_loss_latch_unknown", None
    baseline = _decimal(daily_gate.get("baseline_equity_usdt"))
    equity = _decimal(daily_gate.get("current_adjusted_equity_usdt"))
    block_pct = _decimal(daily_gate.get("block_pct"))
    if baseline is None or equity is None or block_pct is None:
        return DECISION_WAIT, "daily_gate_values_unknown", None
    if baseline <= 0 or equity <= 0 or not (Decimal(-100) < block_pct < 0):
        return DECISION_WAIT, "daily_gate_values_invalid", None
    headroom = equity - baseline * (1 + block_pct / HUNDRED)
    if headroom <= 0:
        return DECISION_DENY, "daily_loss_headroom_exhausted", None
    return DECISION_OK, "headroom", headroom


def account_risk_limit(
    *, daily_gate: Any, committed_worst_case_usdt: Iterable[Any] | None,
) -> AccountRiskLimit:
    """Available account risk budget after current obligations.

    ``committed_worst_case_usdt`` lists the worst-case loss (USDT, >= 0) of every open
    position and pending entry of the account; ``None`` or any unknown item means the
    commitments are unproven -> WAIT. Unrealized loss is already inside the gate's
    adjusted equity, so subtracting the full worst case is deliberately conservative.
    """

    decision, reason, headroom = daily_loss_headroom_usdt(daily_gate)
    if decision != DECISION_OK:
        return AccountRiskLimit(decision, reason)
    if committed_worst_case_usdt is None:
        return AccountRiskLimit(DECISION_WAIT, "obligations_unknown", headroom_usdt=headroom)
    total = Decimal(0)
    for item in committed_worst_case_usdt:
        amount = _decimal(item)
        if amount is None:
            return AccountRiskLimit(DECISION_WAIT, "obligation_unknown", headroom_usdt=headroom)
        if amount < 0:
            return AccountRiskLimit(DECISION_WAIT, "obligation_invalid", headroom_usdt=headroom)
        total += amount
    available = headroom - total
    if available <= 0:
        return AccountRiskLimit(
            DECISION_DENY, "account_risk_exhausted", headroom_usdt=headroom, committed_usdt=total,
        )
    return AccountRiskLimit(DECISION_OK, "available", available, headroom, total)


def freeze_r0(
    *, idea_potential_net_usdt: Any, daily_gate: Any, committed_worst_case_usdt: Iterable[Any] | None,
) -> FrozenR0:
    """Freeze ``R0 = min(account risk limit, 0.5 * net idea potential)`` before the first attempt."""

    limit = account_risk_limit(
        daily_gate=daily_gate, committed_worst_case_usdt=committed_worst_case_usdt,
    )
    if limit.decision != DECISION_OK:
        return FrozenR0(limit.decision, limit.reason, None, limit)
    potential = _decimal(idea_potential_net_usdt)
    if potential is None:
        return FrozenR0(DECISION_WAIT, "idea_potential_unknown", None, limit)
    if potential <= 0:
        return FrozenR0(DECISION_DENY, "no_net_potential", None, limit)
    r0 = freeze_campaign_r0(
        idea_potential_net_usdt=float(potential), account_risk_limit_usdt=float(limit.limit_usdt),
    )
    if r0 is None:
        return FrozenR0(DECISION_WAIT, "r0_not_computable", None, limit)
    return FrozenR0(DECISION_OK, "frozen", r0, limit)
