from decimal import Decimal

from terminal.domain.models import ExecutionId, OrderId, OrderSide, Price, Quantity, Symbol, TradingAccountId
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.events import execution_event_from_paper_match
from terminal.paper.matching import match_market_order


def test_paper_match_converts_to_execution_event_with_fee():
    book = NormalizedOrderBook(
        symbol=Symbol("BTCUSDT"),
        bids=(
            PriceLevel(Price(Decimal("99")), Quantity(Decimal("2"))),
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

    assert event.symbol == "BTCUSDT"
    assert event.side is OrderSide.BUY
    assert event.execution_price == Decimal("101")
    assert event.execution_quantity == Decimal("2")
    assert event.execution_value == Decimal("202")
    assert event.execution_fee == Decimal("0.202")
    assert event.is_maker is False
    assert event.executed_at_ms == 2000
