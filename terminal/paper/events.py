"""Translate deterministic PAPER matches into normalized execution evidence."""

from __future__ import annotations

from decimal import Decimal

from terminal.domain.models import (
    Category,
    ExecutionId,
    OrderId,
    TradingAccountId,
)
from terminal.exchange.events import ExecutionEvent
from terminal.paper.matching import PaperMarketMatch


def execution_event_from_paper_match(
    match: PaperMarketMatch,
    *,
    trading_account_id: TradingAccountId,
    order_id: OrderId,
    order_link_id: str,
    exec_id: ExecutionId,
    executed_at_ms: int,
    fee_rate: Decimal,
) -> ExecutionEvent:
    if fee_rate < 0:
        raise ValueError("fee_rate must not be negative")
    if executed_at_ms < 0:
        raise ValueError("executed_at_ms must not be negative")

    execution_value = match.vwap.value * match.filled_quantity.value
    execution_fee = execution_value * fee_rate

    return ExecutionEvent(
        trading_account_id=trading_account_id,
        category=Category.LINEAR,
        symbol=match.symbol.value,
        exec_id=exec_id,
        order_id=order_id,
        order_link_id=order_link_id,
        side=match.side,
        execution_price=match.vwap.value,
        execution_quantity=match.filled_quantity.value,
        execution_fee=execution_fee,
        execution_value=execution_value,
        is_maker=False,
        executed_at_ms=executed_at_ms,
        sequence=None,
    )
