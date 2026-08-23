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


def test_paper_market_executor_closes_long_and_realizes_pnl():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            account = TradingAccountId("paper")
            symbol = Symbol("BTCUSDT")
            engine = ExecutionEngine(store)

            entry_book = NormalizedOrderBook(
                symbol=symbol,
                bids=(
                    PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("2"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=1,
            )

            executor = PaperMarketExecutor(
                BookProvider(entry_book),
                engine,
                max_book_age_ms=5000,
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 2000,
            )

            executor.execute(
                trading_account_id=account,
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=Quantity(Decimal("2")),
                order_link_id="entry-link",
                order_id=OrderId("entry-order"),
                exec_id=ExecutionId("entry-exec"),
            )

            exit_book = NormalizedOrderBook(
                symbol=symbol,
                bids=(
                    PriceLevel(Price(Decimal("110")), Quantity(Decimal("2"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("111")), Quantity(Decimal("5"))),
                ),
                health=BookHealth.READY,
                received_at_ms=3000,
                available_depth=1,
            )

            executor.book_provider = BookProvider(exit_book)
            executor.clock_ms = lambda: 4000

            executor.execute(
                trading_account_id=account,
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=Quantity(Decimal("2")),
                order_link_id="exit-link",
                order_id=OrderId("exit-order"),
                exec_id=ExecutionId("exit-exec"),
            )

            projection = store.get_position_projection(
                PositionKey(account, Category.LINEAR, symbol, 0)
            )

            assert projection is not None
            assert projection.side is PositionSide.FLAT
            assert projection.quantity.value == Decimal("0")
            assert projection.average_entry is None
            assert projection.realized_pnl == Decimal("20")
            assert projection.accumulated_fee == Decimal("0.420")
            assert projection.engaged_notional.value == Decimal("0")
        finally:
            store.close()


