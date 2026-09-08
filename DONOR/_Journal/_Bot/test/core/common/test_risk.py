from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from app.core.common.money import Money
from app.core.common.risk import Risk


def test_risk_retains_non_negative_money() -> None:
    risk = Risk(Money("10", "USD"))

    assert risk.amount == Money("10", "USD")
    assert Risk(Money(0, "USD")).amount.amount == Decimal("0")


def test_risk_rejects_negative_money() -> None:
    with pytest.raises(ValueError):
        Risk(Money(-10, "USD"))


def test_risk_requires_money() -> None:
    with pytest.raises(TypeError):
        Risk(Decimal("10"))


def test_risk_is_immutable_and_compares_by_value() -> None:
    risk = Risk(Money(10, "USD"))

    assert risk == Risk(Money("10", "usd"))
    with pytest.raises(FrozenInstanceError):
        risk.amount = Money(20, "USD")

