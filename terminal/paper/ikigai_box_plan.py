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
    if any(sign * (frozen_f1 - price) <= 0 for price in prices):
        raise ValueError("F(1.0) must be on the profitable side of every LIMIT")

    total = sum(quantities, Decimal(0))
    average = sum((p * q for p, q in zip(prices, quantities)), Decimal(0)) / total
    reward = sign * (frozen_f1 - average) - average * entry_fee - frozen_f1 * target_fee
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
            sign * (frozen_f1 - price) - price * entry_fee - frozen_f1 * target_fee
        )
        loss = quantity * (sign * (price - stop) + price * entry_fee + stop * stop_fee)
        return PlannedExposure(quantity, price, profit, loss, profit / loss)

    full = exposure(average, total)
    slices = tuple(exposure(p, q) for p, q in zip(prices, quantities))
    return IkigaiBoxPaperPlan(
        direction=direction, limit_prices=prices, limit_quantities=quantities,
        frozen_f1=frozen_f1, frozen_f1618=frozen_f1618, grid_spacing=abs(step),
        stop_price=stop, stop_basis=basis, full_position=full, slices=slices,
        partial_fill_loss_upper_bound=sum((s.net_stop_loss for s in slices), Decimal(0)),
        minimum_partial_fill_rr=min(s.reward_risk for s in slices),
    )
