"""Authoritative PnL replay for exchange-backed journal trades."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.core.common.money import Money
from app.core.common.quantity import Quantity

from .enums import ExecutionSide, TradeDirection, TradePnLSource, TradeStatus
from .execution import Execution


PERSISTENCE_QUANTUM = Decimal("0.000000000000000001")


def _persisted_decimal(value: Decimal) -> Decimal:
    """Apply the Numeric(38,18) persistence policy without a broad tolerance."""
    with localcontext() as context:
        context.prec = max(60, len(value.as_tuple().digits) + 20)
        return value.quantize(PERSISTENCE_QUANTUM, rounding=ROUND_HALF_EVEN)


@dataclass(frozen=True, slots=True)
class ExecutionReplayResult:
    """Chronological position replay independent from the snapshot model."""

    first_direction: TradeDirection
    final_direction: TradeDirection | None
    status: TradeStatus
    open_quantity: Quantity
    realized_quantity: Quantity
    gross_pnl: Money
    fees: Money


def replay_executions(executions: tuple[Execution, ...] | list[Execution]) -> ExecutionReplayResult:
    """Replay fills, including partial closes and residual reversals.

    A reversal is one exchange fill.  Its close portion realizes PnL against
    the current weighted entry and its residual portion opens the opposite
    position.  The fee remains one authoritative exchange fee and is counted
    exactly once.
    """
    ordered = tuple(sorted(executions, key=lambda item: (item.executed_at, str(item.execution_id))))
    if not ordered:
        raise ValueError("execution replay requires at least one execution")

    account_id = ordered[0].account_id
    instrument_id = ordered[0].instrument_id
    currency = ordered[0].fee.currency
    position = Decimal("0")
    average_entry = Decimal("0")
    direction: TradeDirection | None = None
    first_direction: TradeDirection | None = None
    gross = Decimal("0")
    fees = Decimal("0")
    realized = Decimal("0")

    for execution in ordered:
        if execution.account_id != account_id or execution.instrument_id != instrument_id:
            raise ValueError("execution replay contains mixed account or instrument facts")
        if execution.fee.currency != currency:
            raise ValueError("execution replay contains mixed fee currencies")
        fees += execution.fee.amount

        if position == 0:
            direction = TradeDirection.LONG if execution.side is ExecutionSide.BUY else TradeDirection.SHORT
            first_direction = first_direction or direction
            position = execution.quantity.value
            average_entry = execution.price.value
            continue

        opening_side = (
            execution.side is ExecutionSide.BUY
            if direction is TradeDirection.LONG
            else execution.side is ExecutionSide.SELL
        )
        if opening_side:
            new_position = position + execution.quantity.value
            average_entry = (average_entry * position + execution.price.value * execution.quantity.value) / new_position
            position = new_position
            continue

        close_quantity = min(position, execution.quantity.value)
        if direction is TradeDirection.LONG:
            gross += (execution.price.value - average_entry) * close_quantity
        else:
            gross += (average_entry - execution.price.value) * close_quantity
        realized += close_quantity
        residual = execution.quantity.value - close_quantity
        position -= close_quantity
        if residual > 0:
            direction = TradeDirection.SHORT if direction is TradeDirection.LONG else TradeDirection.LONG
            position = residual
            average_entry = execution.price.value
        elif position == 0:
            direction = None
            average_entry = Decimal("0")

    if first_direction is None:
        raise ValueError("execution replay could not determine direction")
    status = TradeStatus.OPEN if position > 0 else TradeStatus.CLOSED
    return ExecutionReplayResult(
        first_direction=first_direction,
        final_direction=direction,
        status=status,
        open_quantity=Quantity(position),
        realized_quantity=Quantity(realized),
        gross_pnl=Money(gross, currency),
        fees=Money(fees, currency),
    )


def validate_execution_replay(trade, executions: tuple[Execution, ...] | list[Execution]) -> ExecutionReplayResult:
    """Validate persisted economic fields against canonical executions."""
    if trade.pnl_source is not TradePnLSource.EXECUTION_REPLAY:
        raise ValueError("execution replay validation requires EXECUTION_REPLAY provenance")
    result = replay_executions(executions)
    if trade.direction is not result.first_direction:
        raise ValueError("persisted direction does not match execution replay")
    if trade.status is not result.status:
        raise ValueError("persisted status does not match execution replay")
    expected_quantity = result.open_quantity if result.status is TradeStatus.OPEN else result.realized_quantity
    if _persisted_decimal(trade.quantity.value) != _persisted_decimal(expected_quantity.value):
        raise ValueError("persisted quantity does not match execution replay")
    if trade.fees.currency != result.fees.currency or _persisted_decimal(trade.fees.amount) != _persisted_decimal(result.fees.amount):
        raise ValueError("persisted fees do not match execution replay")
    if result.status is TradeStatus.CLOSED:
        if trade.gross_pnl is None or trade.net_pnl is None:
            raise ValueError("closed EXECUTION_REPLAY trade lacks PnL")
        if trade.gross_pnl.currency != result.gross_pnl.currency or _persisted_decimal(trade.gross_pnl.amount) != _persisted_decimal(result.gross_pnl.amount):
            raise ValueError("persisted gross PnL does not match execution replay")
        expected_net = result.gross_pnl - result.fees
        for expense in trade.expenses:
            expected_net += expense.amount
        if trade.net_pnl.currency != expected_net.currency or _persisted_decimal(trade.net_pnl.amount) != _persisted_decimal(expected_net.amount):
            raise ValueError("persisted net PnL does not match execution replay")
    return result
