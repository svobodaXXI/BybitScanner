from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.quantity import Quantity


def test_quantity_converts_decimal_and_allows_zero() -> None:
    assert Quantity("10.5").value == Decimal("10.5")
    assert Quantity(0).value == Decimal("0")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_quantity_rejects_non_finite_value(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Quantity(value)


def test_quantity_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        Quantity("-1")


def test_quantity_arithmetic() -> None:
    quantity = Quantity("10")

    assert quantity + Quantity("2.5") == Quantity("12.5")
    assert quantity - Quantity("2.5") == Quantity("7.5")
    assert quantity * Decimal("2") == Quantity("20")
    assert Decimal("2") * quantity == Quantity("20")
    assert quantity / Decimal("4") == Quantity("2.5")


def test_quantity_subtraction_cannot_produce_negative_value() -> None:
    with pytest.raises(ValueError):
        Quantity(1) - Quantity(2)


def test_quantity_is_immutable_and_compares_by_value() -> None:
    quantity = Quantity(10)

    assert quantity == Quantity("10")
    with pytest.raises(FrozenInstanceError):
        quantity.value = Decimal("20")

