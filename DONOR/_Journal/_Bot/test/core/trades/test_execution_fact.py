from datetime import datetime
from decimal import Decimal

import pytest

from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.trades.enums import TradeDirection
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_side import ExecutionSide

from .test_execution import EXECUTED_AT, make_fact


@pytest.mark.parametrize("side", [ExecutionSide.BUY, ExecutionSide.SELL])
def test_execution_fact_supports_buy_and_sell(side: ExecutionSide) -> None:
    fact = make_fact(side=side)

    assert fact.side is side
    assert fact.exchange == "BYBIT"


def test_execution_fact_allows_missing_external_execution_id_for_manual_ingestion() -> None:
    fact = make_fact(external_execution_id=None)

    assert fact.external_execution_id is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Quantity(0)),
        ("executed_at", datetime(2026, 1, 1, 10)),
        ("fee", Money("-0.01", "USD")),
        ("exchange", ""),
        ("external_execution_id", " "),
    ],
)
def test_execution_fact_rejects_invalid_data(field: str, value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        make_fact(**{field: value})


def test_execution_fact_has_no_trade_direction_side() -> None:
    assert not isinstance(ExecutionSide.BUY, TradeDirection)


def test_execution_fact_normalizes_timezone_to_utc() -> None:
    fact = make_fact(executed_at=EXECUTED_AT)

    assert fact.executed_at == EXECUTED_AT


def test_execution_fact_preserves_decimal_values_and_normalizes_external_identity() -> None:
    fact = make_fact(external_execution_id="  fill-123  ", price=Price("100.25"), quantity=Quantity("2.5"))
    assert fact.price.value == Decimal("100.25")
    assert fact.quantity.value == Decimal("2.5")
    assert fact.fee.amount == Decimal("1.50")
    assert fact.external_execution_id == "fill-123"
