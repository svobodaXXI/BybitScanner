import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.domain.models import (
    Category,
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperLimitExecutor, PaperMarketExecutor
from terminal.persistence.sqlite_store import SQLiteStore


class BookProvider:
    def __init__(self, book):
        self.book = book

    def get_book(self, symbol):
        return self.book if self.book.symbol == symbol else None


def test_paper_market_executor_creates_durable_long_position():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            book = NormalizedOrderBook(
                symbol=Symbol("BTCUSDT"),
                bids=(
                    PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("1"))),
                    PriceLevel(Price(Decimal("102")), Quantity(Decimal("1"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=2,
            )

            executor = PaperMarketExecutor(
                BookProvider(book),
                ExecutionEngine(store),
                max_book_age_ms=5000,
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 2000,
            )

            result = executor.execute(
                trading_account_id=TradingAccountId("paper"),
                symbol=Symbol("BTCUSDT"),
                side=OrderSide.BUY,
                quantity=Quantity(Decimal("2")),
                order_link_id="paper-link-1",
                order_id=OrderId("paper-order-1"),
                exec_id=ExecutionId("paper-exec-1"),
            )

            assert result.match.vwap.value == Decimal("101")
            assert result.apply_result.value == "applied"

            projection = store.get_position_projection(
                PositionKey(
                    TradingAccountId("paper"),
                    Category.LINEAR,
                    Symbol("BTCUSDT"),
                    0,
                )
            )

            assert projection is not None
            assert projection.side is PositionSide.LONG
            assert projection.quantity.value == Decimal("2")
            assert projection.average_entry.value == Decimal("101")
            assert projection.engaged_notional.value == Decimal("202")
            assert projection.accumulated_fee == Decimal("0.202")
        finally:
            store.close()


def _limit_book(*, ask_price: str, ask_quantity: str) -> NormalizedOrderBook:
    return NormalizedOrderBook(
        symbol=Symbol("BTCUSDT"),
        bids=(PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),),
        asks=(
            PriceLevel(
                Price(Decimal(ask_price)),
                Quantity(Decimal(ask_quantity)),
            ),
        ),
        health=BookHealth.READY,
        received_at_ms=1000,
        available_depth=1,
    )


def _create_limit(store: SQLiteStore, *, quantity: str = "3"):
    order, created = store.create_paper_limit(
        client_action_id="create-limit-1",
        request_fingerprint="limit-fingerprint-1",
        order_id=OrderId("paper-limit-1"),
        order_link_id="paper-limit-link-1",
        trading_account_id=TradingAccountId("paper"),
        symbol=Symbol("BTCUSDT"),
        side=OrderSide.BUY,
        price=Decimal("101"),
        quantity=Decimal(quantity),
        created_at_ms=900,
    )
    assert created is True
    return order


def test_paper_limit_executor_no_cross_makes_no_persistence_mutation():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            order = _create_limit(store)
            result = PaperLimitExecutor(
                ExecutionEngine(store), clock_ms=lambda: 2000,
            ).execute(
                order=order,
                book=_limit_book(ask_price="102", ask_quantity="5"),
                match_event_id="book-update-1",
            )

            persisted = store.get_paper_limit(order.order_id.value)
            assert result is None
            assert persisted is not None
            assert persisted.filled_quantity == Decimal("0")
            assert persisted.status == "open"
            assert store.get_position_projection(PositionKey(
                TradingAccountId("paper"), Category.LINEAR,
                Symbol("BTCUSDT"), 0,
            )) is None
        finally:
            store.close()


def test_paper_limit_executor_applies_partial_actual_quantity():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            order = _create_limit(store, quantity="3")
            result = PaperLimitExecutor(
                ExecutionEngine(store),
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 2000,
            ).execute(
                order=order,
                book=_limit_book(ask_price="100", ask_quantity="1"),
                match_event_id="book-update-partial",
            )

            assert result is not None
            assert result.execution_event.execution_quantity == Decimal("1")
            assert result.execution_event.execution_price == Decimal("100")
            assert result.execution_event.is_maker is True
            assert result.execution_event.execution_fee == Decimal("0.100")
            persisted = store.get_paper_limit(order.order_id.value)
            assert persisted is not None
            assert persisted.filled_quantity == Decimal("1")
            assert persisted.status == "partially_filled"
            projection = store.get_position_projection(PositionKey(
                TradingAccountId("paper"), Category.LINEAR,
                Symbol("BTCUSDT"), 0,
            ))
            assert projection is not None
            assert projection.quantity.value == Decimal("1")
        finally:
            store.close()


def test_paper_limit_executor_applies_full_actual_quantity():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            order = _create_limit(store, quantity="2")
            result = PaperLimitExecutor(
                ExecutionEngine(store), clock_ms=lambda: 2000,
            ).execute(
                order=order,
                book=_limit_book(ask_price="100", ask_quantity="5"),
                match_event_id="book-update-full",
            )

            assert result is not None
            assert result.execution_event.execution_quantity == Decimal("2")
            persisted = store.get_paper_limit(order.order_id.value)
            assert persisted is not None
            assert persisted.filled_quantity == Decimal("2")
            assert persisted.status == "filled"
            assert store.load_active_paper_limits(Symbol("BTCUSDT")) == ()
        finally:
            store.close()

