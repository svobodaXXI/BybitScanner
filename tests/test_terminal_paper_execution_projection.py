import tempfile
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.domain.models import (
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
    Category,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.events import execution_event_from_paper_match
from terminal.paper.matching import match_market_order
from terminal.persistence.sqlite_store import SQLiteStore


def test_paper_execution_updates_durable_position_projection():
    with tempfile.TemporaryDirectory() as temp:
        store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
        try:
            engine = ExecutionEngine(store)

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

            match = match_market_order(
                book,
                side=OrderSide.BUY,
                quantity=Quantity(Decimal("2")),
            )

            event = execution_event_from_paper_match(
                match,
                trading_account_id=TradingAccountId("paper"),
                order_id=OrderId("paper-order-1"),
                order_link_id="paper-link-1",
                exec_id=ExecutionId("paper-exec-1"),
                executed_at_ms=2000,
                fee_rate=Decimal("0.001"),
            )

            result = engine.apply_execution(event)
            assert result.value == "applied"

            key = PositionKey(
                TradingAccountId("paper"),
                Category.LINEAR,
                Symbol("BTCUSDT"),
                0,
            )
            projection = store.get_position_projection(key)

            assert projection is not None
            assert projection.side is PositionSide.LONG
            assert projection.quantity.value == Decimal("2")
            assert projection.average_entry.value == Decimal("101")
            assert projection.engaged_notional.value == Decimal("202")
            assert projection.accumulated_fee == Decimal("0.202")
        finally:
            store.close()
