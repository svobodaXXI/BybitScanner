from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.percentage import Percentage


def test_percentage_is_stored_in_percentage_points() -> None:
    assert Percentage(1).value == Decimal("1")
    assert Percentage(25).value == Decimal("25")
    assert Percentage(100).value == Decimal("100")
    assert Percentage(150).value == Decimal("150")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_percentage_rejects_non_finite_value(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Percentage(value)


def test_percentage_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        Percentage(-1)


def test_percentage_converts_to_and_from_ratio() -> None:
    assert Percentage(1).to_ratio() == Decimal("0.01")
    assert Percentage(25).to_ratio() == Decimal("0.25")
    assert Percentage(100).to_ratio() == Decimal("1")
    assert Percentage.from_ratio(Decimal("0.25")) == Percentage(25)


def test_percentage_is_immutable_and_compares_by_value() -> None:
    percentage = Percentage("25")

    assert percentage == Percentage(25)
    with pytest.raises(FrozenInstanceError):
        percentage.value = Decimal("50")

