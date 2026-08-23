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
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.events import execution_event_from_paper_match
from terminal.paper.matching import match_market_order
from terminal.persistence.sqlite_store import ExecutionApplyResult, SQLiteStore


def test_duplicate_paper_execution_is_applied_exactly_once():
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
                    PriceLevel(Price(Decimal("100")), Quantity(Decimal("2"))),
                ),
                health=BookHealth.READY,
                received_at_ms=1000,
                available_depth=1,
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

            first = engine.apply_execution(event)
            second = engine.apply_execution(event)

            assert first is ExecutionApplyResult.APPLIED
            assert second is ExecutionApplyResult.DUPLICATE

            projection = store.get_position_projection(
                PositionKey(
                    TradingAccountId("paper"),
                    Category.LINEAR,
                    Symbol("BTCUSDT"),
                    0,
                )
            )

            assert projection is not None
            assert projection.quantity.value == Decimal("2")
            assert projection.accumulated_fee == Decimal("0.200")
            assert len(store.load_executions()) == 1
        finally:
            store.close()
