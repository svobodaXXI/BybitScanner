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
from terminal.paper.executor import PaperMarketExecutor
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

