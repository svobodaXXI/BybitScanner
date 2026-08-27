from decimal import Decimal

import pytest

from terminal.domain.models import OrderSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.matching import (
    PaperBookUnavailable,
    PaperInsufficientLiquidity,
    match_limit_order,
    match_market_order,
)


def _book(*, health=BookHealth.READY):
    return NormalizedOrderBook(
        symbol=Symbol("BTCUSDT"),
        bids=(
            PriceLevel(Price(Decimal("99")), Quantity(Decimal("2"))),
            PriceLevel(Price(Decimal("98")), Quantity(Decimal("3"))),
        ),
        asks=(
            PriceLevel(Price(Decimal("101")), Quantity(Decimal("1"))),
            PriceLevel(Price(Decimal("102")), Quantity(Decimal("2"))),
        ),
        health=health,
        received_at_ms=1,
        available_depth=2,
    )


def test_market_buy_walks_asks_and_calculates_vwap():
    result = match_market_order(
        _book(),
        side=OrderSide.BUY,
        quantity=Quantity(Decimal("2")),
    )

    assert result.filled_quantity.value == Decimal("2")
    assert result.vwap.value == Decimal("101.5")
    assert [fill.price.value for fill in result.fills] == [
        Decimal("101"),
        Decimal("102"),
    ]
    assert [fill.quantity.value for fill in result.fills] == [
        Decimal("1"),
        Decimal("1"),
    ]


def test_market_sell_walks_bids():
    result = match_market_order(
        _book(),
        side=OrderSide.SELL,
        quantity=Quantity(Decimal("3")),
    )

    assert result.filled_quantity.value == Decimal("3")
    assert result.vwap.value == Decimal("98.66666666666666666666666667")


def test_market_rejects_unhealthy_book():
    with pytest.raises(PaperBookUnavailable):
        match_market_order(
            _book(health=BookHealth.STALE),
            side=OrderSide.BUY,
            quantity=Quantity(Decimal("1")),
        )


def test_market_rejects_insufficient_liquidity():
    with pytest.raises(PaperInsufficientLiquidity):
        match_market_order(
            _book(),
            side=OrderSide.BUY,
            quantity=Quantity(Decimal("4")),
        )


def test_limit_buy_walks_only_asks_at_or_below_cap():
    result = match_limit_order(
        _book(),
        side=OrderSide.BUY,
        limit_price=Price(Decimal("102")),
        remaining_quantity=Quantity(Decimal("2.5")),
    )

    assert result is not None
    assert result.fully_filled is True
    assert result.filled_quantity.value == Decimal("2.5")
    assert result.remaining_quantity.value == Decimal("0.0")
    assert result.vwap.value == Decimal("101.6")
    assert [fill.price.value for fill in result.fills] == [
        Decimal("101"),
        Decimal("102"),
    ]


def test_limit_sell_walks_only_bids_at_or_above_floor():
    result = match_limit_order(
        _book(),
        side=OrderSide.SELL,
        limit_price=Price(Decimal("98")),
        remaining_quantity=Quantity(Decimal("4")),
    )

    assert result is not None
    assert result.fully_filled is True
    assert result.filled_quantity.value == Decimal("4")
    assert result.remaining_quantity.value == Decimal("0")
    assert [fill.price.value for fill in result.fills] == [
        Decimal("99"),
        Decimal("98"),
    ]


def test_limit_returns_partial_fill_when_eligible_liquidity_is_insufficient():
    result = match_limit_order(
        _book(),
        side=OrderSide.BUY,
        limit_price=Price(Decimal("101")),
        remaining_quantity=Quantity(Decimal("3")),
    )

    assert result is not None
    assert result.fully_filled is False
    assert result.filled_quantity.value == Decimal("1")
    assert result.remaining_quantity.value == Decimal("2")
    assert [fill.price.value for fill in result.fills] == [Decimal("101")]


@pytest.mark.parametrize(
    ("side", "limit_price"),
    [
        (OrderSide.BUY, "100"),
        (OrderSide.SELL, "100"),
    ],
)
def test_limit_returns_no_match_before_market_reaches_price(side, limit_price):
    assert match_limit_order(
        _book(),
        side=side,
        limit_price=Price(Decimal(limit_price)),
        remaining_quantity=Quantity(Decimal("1")),
    ) is None
