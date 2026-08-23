import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

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
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.executor import PaperBookStale, PaperMarketExecutor
from terminal.persistence.sqlite_store import SQLiteStore


class BookProvider:
    def __init__(self, book):
        self.book = book

    def get_book(self, symbol):
        return self.book if self.book.symbol == symbol else None


def test_paper_market_executor_rejects_stale_ready_book():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            book = NormalizedOrderBook(
                symbol=Symbol("BTCUSDT"),
                bids=(
                    PriceLevel(Price(Decimal("99")), Quantity(Decimal("5"))),
                ),
                asks=(
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("5"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=1,
            )

            executor = PaperMarketExecutor(
                BookProvider(book),
                ExecutionEngine(store),
                max_book_age_ms=500,
                fee_rate=Decimal("0.001"),
                clock_ms=lambda: 2000,
            )

            with pytest.raises(PaperBookStale):
                executor.execute(
                    trading_account_id=TradingAccountId("paper"),
                    symbol=Symbol("BTCUSDT"),
                    side=OrderSide.BUY,
                    quantity=Quantity(Decimal("1")),
                    order_link_id="paper-link-1",
                    order_id=OrderId("paper-order-1"),
                    exec_id=ExecutionId("paper-exec-1"),
                )

            assert store.load_executions() == ()
        finally:
            store.close()
