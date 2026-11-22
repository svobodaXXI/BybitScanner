"""Pure PAPER-only first-attempt Box planning; no admission or execution.

Proposed LIMITs are not fills. The caller supplies frozen Fibonacci levels,
rounded prices, quantities, fees and tick size. No endpoint or risk budget is
invented. See IKIGAI_BOX_STRATEGY_SPEC.md's experimental fixed-grid STOP policy.
Actual protection, slice TAKEs, re-arm and second-attempt lifecycle are out of scope.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from terminal.application.normalization import (
    normalize_limit_price,
    require_positive_decimal,
)
from terminal.domain.models import OrderSide


class IkigaiBoxPlanRejected(ValueError):
    """The frozen Box fails a mandatory admissibility gate (grid, limits, RR/STOP)."""


@dataclass(frozen=True, slots=True)
class PlannedExposure:
    """Hypothetical fills at proposed prices; fees on both entry and exit."""

    quantity: Decimal
    average_entry: Decimal
    net_target_profit: Decimal
    net_stop_loss: Decimal
    reward_risk: Decimal


@dataclass(frozen=True, slots=True)
class IkigaiBoxPaperPlan:
    direction: str
    limit_prices: tuple[Decimal, ...]
    limit_quantities: tuple[Decimal, ...]
    frozen_f1: Decimal
    frozen_f1618: Decimal
    take_price: Decimal
    grid_spacing: Decimal
    stop_price: Decimal
    stop_basis: str
    full_position: PlannedExposure
    slices: tuple[PlannedExposure, ...]
    # Bounds for any subset/fraction of the proposed quantities at these prices.
    # These exclude slippage, funding and actual execution uncertainty.
    partial_fill_loss_upper_bound: Decimal
    minimum_partial_fill_rr: Decimal
    environment: str = field(default="PAPER", init=False)
    execution_authorized: bool = field(default=False, init=False)


def _fee(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value < 1:
        raise ValueError(f"{name} must be an explicit finite Decimal rate in [0, 1)")
    return value



def approved_first_grid(
    *, direction: str, frozen_f1: Decimal, frozen_f1618: Decimal,
    tick_size: Decimal,
) -> tuple[tuple[Decimal, ...], Decimal]:
    """Owner-approved equal-step first grid and one common TAKE; no orders.

    The Fibonacci anchors stay frozen, while executable prices are normalized
    to the instrument tick grid. P1 and TAKE round toward the entry side. The
    common grid step rounds outward to the next whole tick so all four LIMITs
    remain exactly equally spaced and P4 stays strictly beyond F(1.618).
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError("direction must be LONG or SHORT")
    for name, value in (
        ("F(1.0)", frozen_f1),
        ("F(1.618)", frozen_f1618),
        ("tick size", tick_size),
    ):
        require_positive_decimal(value, name)
    displacement = frozen_f1618 - frozen_f1
    if (direction == "LONG" and displacement >= 0) or (
        direction == "SHORT" and displacement <= 0
    ):
        raise ValueError("frozen Fibonacci levels contradict the trade direction")

    entry_side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
    raw_p1 = frozen_f1 + Decimal("0.75") * displacement
    p1 = normalize_limit_price(raw_p1, tick_size, entry_side)

    raw_step = abs(displacement) / Decimal("10")
    step = normalize_limit_price(raw_step, tick_size, OrderSide.SELL)
    signed_step = -step if direction == "LONG" else step
    prices = tuple(p1 + index * signed_step for index in range(4))

    raw_take = frozen_f1 + Decimal("0.10") * displacement
    take = normalize_limit_price(raw_take, tick_size, entry_side)

    if any(value <= 0 or value % tick_size != 0 for value in (*prices, take)):
        raise ValueError("approved first grid/TAKE cannot be tick-normalized")
    if any(prices[index] - prices[index - 1] != signed_step for index in (1, 2, 3)):
        raise ValueError("approved first grid cannot preserve equal tick spacing")
    if (
        (direction == "LONG" and prices[3] >= frozen_f1618)
        or (direction == "SHORT" and prices[3] <= frozen_f1618)
    ):
        raise ValueError("approved first grid cannot place P4 beyond F(1.618)")
    return prices, take


def plan_ikigai_box(
    *,
    direction: str,
    limit_prices: Sequence[Decimal],
    limit_quantities: Sequence[Decimal],
    working_quantity: Decimal,
    frozen_f1: Decimal,
    frozen_f1618: Decimal,
    tick_size: Decimal,
    entry_fee_rate: Decimal,
    target_fee_rate: Decimal,
    stop_fee_rate: Decimal,
    structural_stop: Decimal | None = None,
    take_price: Decimal | None = None,
) -> IkigaiBoxPaperPlan:
    """Validate a supplied first grid and freeze one fee-aware STOP beyond P4.

    Quantities are each 1/4 of the supplied working coin quantity. P1 uses the
    existing BUY-floor / SELL-ceil tick policy. Other prices must already be
    tick-aligned and equally spaced; none are moved. A structural STOP is a
    final protective price, including any caller-chosen buffer. Prefer it only
    when tick-aligned, beyond P4 and RR-compliant; otherwise use the risk cap.

    With d=+1 LONG/-1 SHORT, average E, target T, stop S:
      reward/unit = d*(T-E) - E*entry_fee - T*target_fee
      risk/unit   = d*(E-S) + E*entry_fee + S*stop_fee
    Solve risk=reward/2, round TOWARD entry to retain RR >= 2, and reject if no
    positive tick beyond P4 works. Partial fills never reprice the returned STOP.
    """
    if direction not in ("LONG", "SHORT"):
        raise ValueError("direction must be LONG or SHORT")
    prices, quantities = tuple(limit_prices), tuple(limit_quantities)
    if len(prices) != 4 or len(quantities) != 4:
        raise ValueError("exactly four LIMIT prices and quantities are required")
    for name, value in (
        ("working quantity", working_quantity), ("F(1.0)", frozen_f1),
        ("F(1.618)", frozen_f1618), ("tick size", tick_size),
    ):
        require_positive_decimal(value, name)
    for value in prices:
        require_positive_decimal(value, "LIMIT price")
        if value % tick_size:
            raise ValueError("proposed LIMIT prices must already be tick-aligned")
    for value in quantities:
        require_positive_decimal(value, "LIMIT quantity")
        if value * 4 != working_quantity:
            raise ValueError("each LIMIT quantity must be exactly 1/4 working quantity")
    target = frozen_f1 if take_price is None else take_price
    require_positive_decimal(target, "TAKE price")
    if target % tick_size:
        raise ValueError("TAKE price must be tick-aligned")
    entry_fee = _fee(entry_fee_rate, "entry fee")
    target_fee = _fee(target_fee_rate, "target fee")
    stop_fee = _fee(stop_fee_rate, "STOP fee")
    if structural_stop is not None:
        require_positive_decimal(structural_stop, "structural STOP")

    sign = Decimal(1 if direction == "LONG" else -1)
    side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL
    if sign * (frozen_f1 - frozen_f1618) <= 0:
        raise ValueError("frozen Fibonacci levels contradict the trade direction")
    expected_first = normalize_limit_price(
        frozen_f1 + Decimal("0.75") * (frozen_f1618 - frozen_f1), tick_size, side,
    )
    if prices[0] != expected_first:
        raise ValueError("P1 must equal the tick-normalized 75% Fibonacci anchor")
    step = prices[1] - prices[0]
    if sign * step >= 0 or any(prices[i] - prices[i - 1] != step for i in (2, 3)):
        raise ValueError("LIMITs must be equally spaced in adverse fill order")
    if sign * (prices[3] - frozen_f1618) >= 0:
        raise ValueError("P4 must be strictly beyond F(1.618)")
    if any(sign * (target - price) <= 0 for price in prices):
        raise ValueError("TAKE must be on the profitable side of every LIMIT")

    total = sum(quantities, Decimal(0))
    average = sum((p * q for p, q in zip(prices, quantities)), Decimal(0)) / total
    reward = sign * (target - average) - average * entry_fee - target * target_fee
    if reward <= 0:
        raise ValueError("fees leave no positive full-grid target profit")

    def risk_at(stop: Decimal) -> Decimal:
        return sign * (average - stop) + average * entry_fee + stop * stop_fee

    def acceptable(stop: Decimal) -> bool:
        return (
            stop > 0 and stop % tick_size == 0
            and sign * (prices[3] - stop) > 0
            and 0 < risk_at(stop) and 2 * risk_at(stop) <= reward
        )

    if structural_stop is not None and acceptable(structural_stop):
        stop, basis = structural_stop, "STRUCTURAL"
    else:
        bound = (reward / 2 - average * (sign + entry_fee)) / (stop_fee - sign)
        if direction == "LONG":
            bound = max(bound, tick_size)
        if bound <= 0:
            raise ValueError("no positive ratio-compliant STOP beyond P4")
        stop_side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY
        stop = normalize_limit_price(bound, tick_size, stop_side)
        if not acceptable(stop):
            raise ValueError("no tick-aligned STOP beyond P4 satisfies net RR >= 2")
        basis = "FULL_GRID_RR_CAP"

    def exposure(price: Decimal, quantity: Decimal) -> PlannedExposure:
        profit = quantity * (
            sign * (target - price) - price * entry_fee - target * target_fee
        )
        loss = quantity * (sign * (price - stop) + price * entry_fee + stop * stop_fee)
        return PlannedExposure(quantity, price, profit, loss, profit / loss)

    full = exposure(average, total)
    slices = tuple(exposure(p, q) for p, q in zip(prices, quantities))
    return IkigaiBoxPaperPlan(
        direction=direction, limit_prices=prices, limit_quantities=quantities,
        frozen_f1=frozen_f1, frozen_f1618=frozen_f1618, take_price=target, grid_spacing=abs(step),
        stop_price=stop, stop_basis=basis, full_position=full, slices=slices,
        partial_fill_loss_upper_bound=sum((s.net_stop_loss for s in slices), Decimal(0)),
        minimum_partial_fill_rr=min(s.reward_risk for s in slices),
    )


@dataclass(frozen=True, slots=True)
class BoxRiskAssessment:
    """Pre-entry reservation for the entire proposed PAPER grid, in quote USDT."""

    planned_stop_loss: Decimal
    adverse_execution_allowance: Decimal
    reserved_loss: Decimal
    maximum_allowed_loss: Decimal
    allowed: bool


def assess_first_grid_risk(
    plan: IkigaiBoxPaperPlan,
    *,
    maximum_allowed_loss_usdt: Decimal,
    adverse_stop_slippage_per_unit: Decimal,
    additional_cost_allowance_usdt: Decimal,
) -> BoxRiskAssessment:
    """Fail closed on missing budget/buffers; never authorize an order.

    Reserve risk for ALL four proposed entries even when only P1 might fill.
    The caller must supply a separately approved monetary loss ceiling, an
    adverse STOP price-movement allowance per coin and a monetary allowance
    for incremental exit fees, funding and other costs. This is a bounded
    scenario, not a guarantee against a worse market execution. Actual fills
    and remaining entry orders need separate durable runtime reconciliation.
    """
    if not isinstance(plan, IkigaiBoxPaperPlan) or plan.environment != "PAPER":
        raise ValueError("a PAPER Box plan is required")

    def decimal(name: str, value: Decimal, *, positive: bool = False) -> Decimal:
        if (
            not isinstance(value, Decimal) or not value.is_finite()
            or (value <= 0 if positive else value < 0)
        ):
            raise ValueError(f"{name} must be an explicit finite Decimal "
                             f"{'greater than zero' if positive else 'not below zero'}")
        return value

    ceiling = decimal("maximum allowed loss", maximum_allowed_loss_usdt, positive=True)
    slippage = decimal("adverse STOP slippage per unit", adverse_stop_slippage_per_unit)
    extra = decimal("additional cost allowance", additional_cost_allowance_usdt)
    total_quantity = sum(plan.limit_quantities, Decimal(0))
    planned = plan.partial_fill_loss_upper_bound
    allowance = total_quantity * slippage + extra
    reserved = planned + allowance
    if not reserved.is_finite() or reserved < 0:
        raise ValueError("Box reserved loss is invalid")
    return BoxRiskAssessment(
        planned_stop_loss=planned,
        adverse_execution_allowance=allowance,
        reserved_loss=reserved,
        maximum_allowed_loss=ceiling,
        allowed=reserved <= ceiling,
    )


def plan_approved_first_ikigai_box(
    *, direction: str, working_quantity: Decimal,
    frozen_f1: Decimal, frozen_f1618: Decimal, tick_size: Decimal,
    entry_fee_rate: Decimal, target_fee_rate: Decimal,
    stop_fee_rate: Decimal, structural_stop: Decimal | None = None,
) -> IkigaiBoxPaperPlan:
    """Plan the approved first-attempt geometry; still no order authorization."""
    prices, take = approved_first_grid(
        direction=direction, frozen_f1=frozen_f1,
        frozen_f1618=frozen_f1618, tick_size=tick_size,
    )
    require_positive_decimal(working_quantity, "working quantity")
    each = working_quantity / Decimal(4)
    return plan_ikigai_box(
        direction=direction, limit_prices=prices,
        limit_quantities=(each,) * 4, working_quantity=working_quantity,
        frozen_f1=frozen_f1, frozen_f1618=frozen_f1618,
        tick_size=tick_size, entry_fee_rate=entry_fee_rate,
        target_fee_rate=target_fee_rate, stop_fee_rate=stop_fee_rate,
        structural_stop=structural_stop, take_price=take,
    )


@dataclass(frozen=True, slots=True)
class BoxReversalEntryPreview:
    """Hypothetical single entry at second-leg exhaustion, never an order."""

    direction: str
    assumed_entry: Decimal
    structural_stop: Decimal
    frozen_take: Decimal
    quantity: Decimal
    net_target_profit: Decimal
    reserved_loss: Decimal
    maximum_allowed_loss: Decimal
    allowed: bool
    reason: str
    execution_authorized: bool = field(default=False, init=False)


def assess_box_reversal_entry(
    plan: IkigaiBoxPaperPlan,
    *,
    entry_price: Decimal,
    second_extreme: Decimal,
    quantity: Decimal,
    qty_step: Decimal,
    tick_size: Decimal,
    stop_buffer_ticks: int,
    entry_fee_rate: Decimal,
    target_fee_rate: Decimal,
    stop_fee_rate: Decimal,
    adverse_entry_per_unit: Decimal,
    adverse_target_per_unit: Decimal,
    adverse_stop_per_unit: Decimal,
    additional_cost_allowance_usdt: Decimal,
    maximum_allowed_loss_usdt: Decimal,
) -> BoxReversalEntryPreview:
    """Bound one alternative Box entry with the original frozen TAKE.

    Research caller supplies causal second-impulse extreme and hypothetical
    entry from absorption, reclaim or first pullback. This function does NOT
    attest the host identity, completeness, timestamps, reversal or a fill.
    It never alters the approved four-slot grid or its protection. No sizing
    increase, target move, or STOP tightening to rescue rejected economics.
    Adverse prices include fees on actual scenario notionals; the additional
    cost allowance is charged once in each mutually exclusive exit scenario.
    This is not a guarantee against execution outside the supplied bounds.
    """
    if not isinstance(plan, IkigaiBoxPaperPlan) or plan.direction not in ("LONG", "SHORT"):
        raise ValueError("an existing Box plan is required")
    for name, value in (
        ("entry", entry_price), ("second extreme", second_extreme),
        ("quantity", quantity), ("quantity step", qty_step),
        ("tick", tick_size), ("frozen TAKE", plan.take_price),
        ("maximum loss", maximum_allowed_loss_usdt),
    ):
        require_positive_decimal(value, name)
    if type(stop_buffer_ticks) is not int or stop_buffer_ticks < 1:
        raise ValueError("STOP requires an explicit positive tick buffer")
    if any(p % tick_size for p in (entry_price, second_extreme, plan.take_price)):
        raise ValueError("entry, extreme and frozen TAKE must be tick-aligned")
    if quantity % qty_step or quantity > sum(plan.limit_quantities, Decimal(0)):
        raise ValueError("quantity must fit the original grid quantity and step")
    for value in (
        adverse_entry_per_unit, adverse_target_per_unit, adverse_stop_per_unit,
        additional_cost_allowance_usdt,
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise ValueError("execution and cost allowances must be finite non-negative Decimal")
    entry_fee = _fee(entry_fee_rate, "entry fee")
    target_fee = _fee(target_fee_rate, "target fee")
    stop_fee = _fee(stop_fee_rate, "STOP fee")
    sign = Decimal(1 if plan.direction == "LONG" else -1)
    target = plan.take_price
    if sign * (entry_price - second_extreme) < 0 or sign * (target - entry_price) <= 0:
        raise ValueError("entry must be between second extreme and frozen TAKE")
    stop = second_extreme - sign * tick_size * stop_buffer_ticks
    entry_fill = entry_price + sign * adverse_entry_per_unit
    target_fill = target - sign * adverse_target_per_unit
    stop_fill = stop - sign * adverse_stop_per_unit
    for name, value in (
        ("structural STOP", stop), ("entry scenario", entry_fill),
        ("target scenario", target_fill), ("STOP scenario", stop_fill),
    ):
        require_positive_decimal(value, name)
    reward = quantity * (
        sign * (target_fill - entry_fill) - entry_fill * entry_fee
        - target_fill * target_fee
    ) - additional_cost_allowance_usdt
    loss = quantity * (
        sign * (entry_fill - stop_fill) + entry_fill * entry_fee
        + stop_fill * stop_fee
    ) + additional_cost_allowance_usdt
    if not reward.is_finite() or not loss.is_finite() or loss <= 0:
        raise ValueError("invalid alternative entry economics")
    if loss > maximum_allowed_loss_usdt:
        reason = "RISK_BUDGET_EXCEEDED"
    elif reward < 2 * loss:
        reason = "NET_RR_BELOW_2"
    else:
        reason = "HYPOTHETICAL_ECONOMICS_OK"
    return BoxReversalEntryPreview(
        direction=plan.direction, assumed_entry=entry_price,
        structural_stop=stop, frozen_take=target, quantity=quantity,
        net_target_profit=reward, reserved_loss=loss,
        maximum_allowed_loss=maximum_allowed_loss_usdt,
        allowed=reason == "HYPOTHETICAL_ECONOMICS_OK", reason=reason,
    )
