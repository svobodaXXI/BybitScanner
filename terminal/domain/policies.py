"""Pure admission and quantity policies for Manual Terminal v1."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from enum import Enum

from .models import OrderSide, PositionSide, Quantity
from .states import CommandState, ConnectivityState


def working_volume_usdt(wallet_balance_usdt: Decimal) -> Decimal:
    one_wv = (
        wallet_balance_usdt * Decimal("0.05")
    ).to_integral_value(rounding=ROUND_DOWN)
    if one_wv <= 0:
        raise ValueError("wallet balance is too small for working-volume sizing")
    return one_wv


class TradingAction(str, Enum):
    NEW_ENTRY = "new_entry"
    SCALE_IN = "scale_in"
    NEW_LIMIT = "new_limit"
    REDUCE = "reduce"
    EMERGENCY_CLOSE = "emergency_close"
    CANCEL = "cancel"


@dataclass(frozen=True, slots=True)
class PermissionDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class MarketQuantityDecision:
    submitted_quantity: Quantity
    capped_at_flat: bool


_RISK_REDUCING = frozenset({
    TradingAction.REDUCE,
    TradingAction.EMERGENCY_CLOSE,
    TradingAction.CANCEL,
})


def permission_for(
    connectivity: ConnectivityState,
    action: TradingAction,
    *,
    safely_bounded: bool = False,
) -> PermissionDecision:
    if connectivity is ConnectivityState.ONLINE:
        return PermissionDecision(True, "synchronized online state")

    if connectivity is ConnectivityState.OFFLINE:
        return PermissionDecision(False, "offline state cannot confirm exchange mutation")

    if action in _RISK_REDUCING and safely_bounded:
        return PermissionDecision(True, "risk reduction is bounded by confirmed state")

    return PermissionDecision(False, "new or unbounded exposure requires synchronized online state")


def retry_requires_reconciliation(command_state: CommandState) -> bool:
    """Return whether another submit would be a forbidden blind retry."""

    return command_state in {
        CommandState.SUBMITTING,
        CommandState.ACKNOWLEDGED,
        CommandState.OPEN,
        CommandState.PARTIALLY_FILLED,
        CommandState.CANCEL_PENDING,
        CommandState.UNKNOWN,
        CommandState.RECONCILING,
    }


def cap_market_quantity_at_flat(
    requested: Quantity,
    order_side: OrderSide,
    position_side: PositionSide,
    confirmed_position_quantity: Quantity,
) -> MarketQuantityDecision:
    """Prevent one opposite-side Market action from crossing through FLAT."""

    if position_side is PositionSide.FLAT:
        if confirmed_position_quantity.value != 0:
            raise ValueError("flat position must have zero confirmed quantity")
        return MarketQuantityDecision(requested, False)

    if confirmed_position_quantity.value <= 0:
        raise ValueError("open position must have positive confirmed quantity")

    same_direction = (
        position_side is PositionSide.LONG and order_side is OrderSide.BUY
    ) or (
        position_side is PositionSide.SHORT and order_side is OrderSide.SELL
    )
    if same_direction:
        return MarketQuantityDecision(requested, False)

    capped_value = min(requested.value, confirmed_position_quantity.value)
    return MarketQuantityDecision(
        submitted_quantity=Quantity(capped_value),
        capped_at_flat=requested.value > capped_value,
    )
