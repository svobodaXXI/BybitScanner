from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.money import Money


def test_money_converts_amount_and_normalizes_currency() -> None:
    money = Money("100.25", " usd ")

    assert money.amount == Decimal("100.25")
    assert money.currency == "USD"


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_money_rejects_non_finite_amount(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Money(value, "USD")


def test_money_rejects_empty_currency() -> None:
    with pytest.raises(ValueError):
        Money(100, "  ")


def test_money_allows_negative_amount() -> None:
    assert Money(-25, "USD").amount == Decimal("-25")


def test_money_addition_and_subtraction_require_same_currency() -> None:
    assert Money(100, "USD") + Money(50, "usd") == Money(150, "USD")
    assert Money(100, "USD") - Money(50, "USD") == Money(50, "USD")

    with pytest.raises(ValueError):
        Money(100, "USD") + Money(50, "RUB")
    with pytest.raises(ValueError):
        Money(100, "USD") - Money(50, "RUB")


def test_money_multiplication_and_division() -> None:
    money = Money("10", "USD")

    assert money * Decimal("2.5") == Money("25", "USD")
    assert Decimal("2.5") * money == Money("25", "USD")
    assert money / Decimal("4") == Money("2.5", "USD")


def test_money_is_immutable_and_compares_by_value() -> None:
    money = Money(100, "USD")

    assert money == Money("100", "usd")
    with pytest.raises(FrozenInstanceError):
        money.amount = Decimal("200")

