from datetime import datetime, timedelta, timezone

import pytest

from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_id import ExecutionId
from app.core.trades.execution_side import ExecutionSide
from app.core.trades.trade_id import TradeId


EXECUTED_AT = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def make_fact(**changes: object) -> ExecutionFact:
    values: dict[str, object] = {
        "exchange": " bybit ",
        "account_id": AccountId.generate(),
        "instrument_id": InstrumentId.generate(),
        "external_execution_id": "exec-123",
        "external_order_id": "order-456",
        "position_id": "position-789",
        "side": ExecutionSide.BUY,
        "quantity": Quantity("2.5"),
        "price": Price("100.25"),
        "fee": Money("1.50", "USD"),
        "executed_at": EXECUTED_AT,
    }
    values.update(changes)
    return ExecutionFact(**values)  # type: ignore[arg-type]


def make_execution(**changes: object) -> Execution:
    values: dict[str, object] = {
        "execution_id": ExecutionId.generate(),
        "account_id": AccountId.generate(),
        "instrument_id": InstrumentId.generate(),
        "side": ExecutionSide.BUY,
        "quantity": Quantity("2.5"),
        "price": Price("100.25"),
        "fee": Money("1.50", "USD"),
        "executed_at": EXECUTED_AT,
        "exchange": " bybit ",
    }
    values.update(changes)
    return Execution(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize("side", [ExecutionSide.BUY, ExecutionSide.SELL])
def test_execution_creation_supports_buy_sell(side: ExecutionSide) -> None:
    execution = make_execution(side=side)

    assert execution.side is side
    assert execution.exchange == "BYBIT"
    assert execution.quantity == Quantity("2.5")
    assert execution.price == Price("100.25")
    assert execution.fee == Money("1.50", "USD")
    assert execution.executed_at == EXECUTED_AT


def test_execution_can_be_unlinked_or_linked_to_trade() -> None:
    unlinked = make_execution()
    linked = make_execution(trade_id=TradeId.generate())

    assert unlinked.trade_id is None
    assert isinstance(linked.trade_id, TradeId)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", Quantity(0)),
        ("executed_at", datetime(2026, 1, 1, 10)),
        ("fee", Money("-0.01", "USD")),
        ("exchange", "  "),
    ],
)
def test_execution_rejects_invalid_data(field: str, value: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        make_execution(**{field: value})


def test_execution_normalizes_aware_timestamp_to_utc() -> None:
    execution = make_execution(
        executed_at=datetime(2026, 1, 1, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    )

    assert execution.executed_at == EXECUTED_AT


def test_execution_preserves_external_ids_separately_from_internal_id() -> None:
    execution = make_execution(
        external_execution_id="exchange-fill-1",
        external_order_id="exchange-order-2",
        position_id="broker-position-3",
    )

    assert execution.external_execution_id == "exchange-fill-1"
    assert execution.external_order_id == "exchange-order-2"
    assert execution.position_id == "broker-position-3"
    assert str(execution.execution_id) != execution.external_execution_id


def test_execution_from_fact_preserves_facts_and_generates_internal_id() -> None:
    fact = make_fact()
    execution = Execution.from_fact(fact)

    assert isinstance(execution.execution_id, ExecutionId)
    assert execution.trade_id is None
    assert execution.exchange == fact.exchange
    assert execution.account_id == fact.account_id
    assert execution.instrument_id == fact.instrument_id
    assert execution.side is fact.side
    assert execution.quantity == fact.quantity
    assert execution.price == fact.price
    assert execution.fee == fact.fee
    assert execution.executed_at == fact.executed_at
    assert execution.external_execution_id == fact.external_execution_id
    assert execution.external_order_id == fact.external_order_id
    assert execution.position_id == fact.position_id
