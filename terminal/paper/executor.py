"""Backend PAPER Market execution using normalized L2 and durable projections."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable

from terminal.application.execution_engine import ExecutionEngine
from terminal.domain.models import (
    ExecutionId,
    OrderId,
    OrderSide,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.exchange.events import ExecutionEvent
from terminal.market_data.book_provider import MarketBookProvider
from terminal.paper.events import execution_event_from_paper_match
from terminal.paper.matching import PaperMarketMatch, match_market_order
from terminal.persistence.sqlite_store import ExecutionApplyResult


class PaperBookStale(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaperMarketExecutionResult:
    match: PaperMarketMatch
    execution_event: ExecutionEvent
    apply_result: ExecutionApplyResult
    order_id: OrderId
    exec_id: ExecutionId


@dataclass(slots=True)
class PaperMarketExecutor:
    book_provider: MarketBookProvider
    execution_engine: ExecutionEngine
    max_book_age_ms: int
    fee_rate: Decimal = Decimal("0.0006")
    clock_ms: Callable[[], int] = lambda: 0

    def __post_init__(self) -> None:
        if self.max_book_age_ms < 0:
            raise ValueError("max_book_age_ms must not be negative")

    def execute(
        self,
        *,
        trading_account_id: TradingAccountId,
        symbol: Symbol,
        side: OrderSide,
        quantity: Quantity,
        order_link_id: str,
        order_id: OrderId,
        exec_id: ExecutionId,
    ) -> PaperMarketExecutionResult:
        book = self.book_provider.get_book(symbol)
        if book is None:
            raise RuntimeError("normalized book is unavailable")
        if book.symbol != symbol:
            raise ValueError("normalized book symbol does not match request")

        now_ms = self.clock_ms()
        age_ms = now_ms - book.received_at_ms
        if age_ms < 0:
            raise PaperBookStale("normalized book timestamp is in the future")
        if age_ms > self.max_book_age_ms:
            raise PaperBookStale(
                f"normalized book is stale: age={age_ms}ms max={self.max_book_age_ms}ms"
            )

        match = match_market_order(
            book,
            side=side,
            quantity=quantity,
        )

        event = execution_event_from_paper_match(
            match,
            trading_account_id=trading_account_id,
            order_id=order_id,
            order_link_id=order_link_id,
            exec_id=exec_id,
            executed_at_ms=now_ms,
            fee_rate=self.fee_rate,
        )

        apply_result = self.execution_engine.apply_execution(event)

        return PaperMarketExecutionResult(
            match=match,
            execution_event=event,
            apply_result=apply_result,
            order_id=order_id,
            exec_id=exec_id,
        )
