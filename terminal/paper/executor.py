"""Backend PAPER Market execution using normalized L2 and durable projections."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
from typing import Callable

from terminal.application.execution_engine import ExecutionEngine
from terminal.domain.models import (
    ExecutionId,
    OrderId,
    OrderSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.exchange.events import ExecutionEvent
from terminal.market_data.book_provider import MarketBookProvider
from terminal.paper.events import execution_event_from_paper_match
from terminal.paper.matching import (
    PaperLimitMatch,
    PaperMarketMatch,
    match_limit_order,
    match_market_order,
)
from terminal.persistence.sqlite_store import (
    ExecutionApplyResult,
    PaperLimitOrderRecord,
)
from terminal.market_data.models import NormalizedOrderBook


class PaperBookStale(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PaperMarketExecutionResult:
    match: PaperMarketMatch
    execution_event: ExecutionEvent
    apply_result: ExecutionApplyResult
    order_id: OrderId
    exec_id: ExecutionId


@dataclass(frozen=True, slots=True)
class PaperLimitExecutionResult:
    match: PaperLimitMatch
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


@dataclass(slots=True)
class PaperLimitExecutor:
    execution_engine: ExecutionEngine
    fee_rate: Decimal = Decimal("0.0006")
    clock_ms: Callable[[], int] = lambda: 0

    def __post_init__(self) -> None:
        if self.fee_rate < 0:
            raise ValueError("fee_rate must not be negative")

    def execute(
        self,
        *,
        order: PaperLimitOrderRecord,
        book: NormalizedOrderBook,
        match_event_id: str,
    ) -> PaperLimitExecutionResult | None:
        if order.status not in {"open", "partially_filled"}:
            raise ValueError("PAPER limit must be active")
        if book.symbol != order.symbol:
            raise ValueError("normalized book symbol does not match PAPER limit")
        if not match_event_id.strip():
            raise ValueError("match_event_id must not be empty")

        remaining = order.quantity - order.filled_quantity
        if remaining <= 0:
            raise ValueError("active PAPER limit has no remaining quantity")

        match = match_limit_order(
            book,
            side=order.side,
            limit_price=Price(order.price),
            remaining_quantity=Quantity(remaining),
        )
        if match is None:
            return None
        if match.filled_quantity.value > remaining:
            raise ValueError("PAPER limit match exceeds remaining quantity")

        digest = hashlib.sha256(
            f"{order.order_id.value}\0{match_event_id}".encode("utf-8")
        ).hexdigest()
        exec_id = ExecutionId(f"paper-limit-{digest}")
        now_ms = self.clock_ms()
        event = execution_event_from_paper_match(
            match,
            trading_account_id=order.trading_account_id,
            order_id=order.order_id,
            order_link_id=order.order_link_id,
            exec_id=exec_id,
            executed_at_ms=now_ms,
            fee_rate=self.fee_rate,
            is_maker=True,
        )
        apply_result = self.execution_engine.apply_paper_limit_execution(
            event,
            updated_at_ms=now_ms,
        )
        return PaperLimitExecutionResult(
            match=match,
            execution_event=event,
            apply_result=apply_result,
            order_id=order.order_id,
            exec_id=exec_id,
        )
