from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.price import Price


def test_price_converts_decimal_and_allows_zero() -> None:
    assert Price("123.45").value == Decimal("123.45")
    assert Price(0).value == Decimal("0")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_price_rejects_non_finite_value(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Price(value)


def test_price_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        Price("-0.01")


def test_price_arithmetic() -> None:
    first = Price("100.50")
    second = Price("40.25")

    assert first - second == Decimal("60.25")
    assert first + Decimal("2.5") == Price("103.00")
    assert first - Decimal("2.5") == Price("98.00")


def test_price_comparison_and_immutability() -> None:
    price = Price(100)

    assert price == Price("100")
    assert Price(99) < price <= Price(100) < Price(101)
    with pytest.raises(FrozenInstanceError):
        price.value = Decimal("200")

