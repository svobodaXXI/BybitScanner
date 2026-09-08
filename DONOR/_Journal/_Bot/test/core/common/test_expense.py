from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.expense import Expense
from app.core.common.money import Money


def test_expense_preserves_positive_and_negative_economic_signs() -> None:
    positive = Expense(Money("25", "USD"))
    negative = Expense(Money("-25", "USD"))

    assert positive.amount.amount == Decimal("25")
    assert negative.amount.amount == Decimal("-25")


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_expense_rejects_non_finite_amount(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Expense(Money(value, "USD"))


def test_expense_allows_zero_and_requires_money() -> None:
    assert Expense(Money(0, "USD")).amount.amount == Decimal("0")
    with pytest.raises(TypeError):
        Expense(Decimal("25"))


def test_expense_is_immutable_and_compares_by_value() -> None:
    expense = Expense(Money(25, "USD"))

    assert expense == Expense(Money("25", "usd"))
    with pytest.raises(FrozenInstanceError):
        expense.amount = Money(30, "USD")

