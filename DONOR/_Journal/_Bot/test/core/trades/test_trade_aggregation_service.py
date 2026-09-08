from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_id import ExecutionId
from app.core.trades.execution_side import ExecutionSide
from app.core.trades.trade_aggregation_service import TradeAggregationService
from app.core.trades.trade_id import TradeId


BASE_TIME = datetime(2026, 1, 1, 10, tzinfo=timezone.utc)


def make_context() -> tuple[AccountId, InstrumentId]:
    return AccountId.generate(), InstrumentId.generate()


def make_execution(
    account_id: AccountId,
    instrument_id: InstrumentId,
    side: ExecutionSide,
    quantity: str,
    price: str,
    *,
    fee: str = "0",
    external_execution_id: str | None = None,
    executed_at: datetime = BASE_TIME,
    trade_id: TradeId | None = None,
) -> Execution:
    return Execution(
        execution_id=ExecutionId.generate(),
        account_id=account_id,
        instrument_id=instrument_id,
        side=side,
        quantity=Quantity(quantity),
        price=Price(price),
        fee=Money(fee, "USDT"),
        executed_at=executed_at,
        exchange="TEST",
        trade_id=trade_id,
        external_execution_id=external_execution_id,
    )


def make_fact(
    account_id: AccountId,
    instrument_id: InstrumentId,
    side: ExecutionSide,
    quantity: str,
    price: str,
    *,
    external_execution_id: str | None = None,
) -> ExecutionFact:
    return ExecutionFact(
        exchange="TEST",
        account_id=account_id,
        instrument_id=instrument_id,
        side=side,
        quantity=Quantity(quantity),
        price=Price(price),
        fee=Money(0, "USDT"),
        executed_at=BASE_TIME,
        external_execution_id=external_execution_id,
    )


def test_first_buy_opens_long_and_first_sell_opens_short() -> None:
    service = TradeAggregationService()
    long_account, long_instrument = make_context()
    short_account, short_instrument = make_context()

    long_aggregate = service.apply(make_execution(long_account, long_instrument, ExecutionSide.BUY, "1", "100"))
    short_aggregate = service.apply(make_execution(short_account, short_instrument, ExecutionSide.SELL, "2", "200"))

    assert long_aggregate.direction is TradeDirection.LONG
    assert short_aggregate.direction is TradeDirection.SHORT
    assert long_aggregate.open_quantity == Quantity(1)
    assert short_aggregate.open_quantity == Quantity(2)
    assert long_aggregate.average_entry == Price(100)
    assert short_aggregate.status is TradeStatus.OPEN


def test_long_scale_in_uses_decimal_weighted_average() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "110"))

    assert aggregate.average_entry == Price("105")
    assert aggregate.open_quantity == Quantity(2)
    assert aggregate.realized_gross_pnl == Money(0, "USDT")


def test_short_scale_in_uses_decimal_weighted_average() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "1", "100"))
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "3", "120"))

    assert aggregate.direction is TradeDirection.SHORT
    assert aggregate.average_entry == Price("115")
    assert aggregate.open_quantity == Quantity(4)


@pytest.mark.parametrize(
    ("direction_side", "close_side", "entry", "close", "expected"),
    [
        (ExecutionSide.BUY, ExecutionSide.SELL, "100", "110", "5"),
        (ExecutionSide.SELL, ExecutionSide.BUY, "100", "90", "5"),
    ],
)
def test_partial_close_preserves_average_and_realizes_gross_pnl(
    direction_side: ExecutionSide,
    close_side: ExecutionSide,
    entry: str,
    close: str,
    expected: str,
) -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, direction_side, "2", entry))
    aggregate = service.apply(make_execution(account_id, instrument_id, close_side, "0.5", close))

    assert aggregate.status is TradeStatus.OPEN
    assert aggregate.open_quantity == Quantity("1.5")
    assert aggregate.average_entry == Price(entry)
    assert aggregate.realized_quantity == Quantity("0.5")
    assert aggregate.realized_gross_pnl == Money(expected, "USDT")


@pytest.mark.parametrize(
    ("open_side", "close_side", "entry", "close"),
    [
        (ExecutionSide.BUY, ExecutionSide.SELL, "100", "110"),
        (ExecutionSide.SELL, ExecutionSide.BUY, "100", "90"),
    ],
)
def test_full_close_sets_closed_and_uses_final_execution_timestamp(
    open_side: ExecutionSide,
    close_side: ExecutionSide,
    entry: str,
    close: str,
) -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()
    close_time = BASE_TIME + timedelta(minutes=5)

    service.apply(make_execution(account_id, instrument_id, open_side, "2", entry))
    aggregate = service.apply(
        make_execution(account_id, instrument_id, close_side, "2", close, executed_at=close_time)
    )

    assert aggregate.status is TradeStatus.CLOSED
    assert aggregate.open_quantity == Quantity(0)
    assert aggregate.realized_quantity == Quantity(2)
    assert aggregate.realized_gross_pnl == Money(20, "USDT")
    assert aggregate.closed_at == close_time


def test_multiple_partial_closes_accumulate_pnl() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "2", "100"))
    service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "0.5", "110"))
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "1.5", "120"))

    assert aggregate.status is TradeStatus.CLOSED
    assert aggregate.realized_gross_pnl == Money(35, "USDT")


def test_fees_accumulate_and_net_pnl_follows_trade_expense_convention() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100", fee="1"))
    aggregate = service.apply(
        make_execution(account_id, instrument_id, ExecutionSide.SELL, "1", "110", fee="2")
    )

    assert aggregate.total_fees == Money(3, "USDT")
    assert aggregate.realized_gross_pnl == Money(10, "USDT")
    assert aggregate.net_realized_pnl == Money(7, "USDT")

    aggregate = service.add_expense(account_id, instrument_id, Expense(Money(2, "USDT")))
    assert aggregate.net_realized_pnl == Money(9, "USDT")


def test_over_close_is_rejected_without_reversal_or_state_change() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))

    with pytest.raises(ValueError, match="exceeds open quantity"):
        service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "2", "110"))

    assert aggregate.direction is TradeDirection.LONG
    assert aggregate.open_quantity == Quantity(1)
    assert aggregate.execution_count == 1


def test_duplicate_external_execution_is_ignored_without_double_counting() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()
    first = make_execution(
        account_id, instrument_id, ExecutionSide.BUY, "1", "100", fee="1", external_execution_id="fill-1"
    )
    second = make_execution(
        account_id, instrument_id, ExecutionSide.BUY, "1", "100", fee="1", external_execution_id="fill-1"
    )

    aggregate = service.apply(first)
    assert service.is_duplicate(second)
    same_aggregate = service.apply(second)

    assert same_aggregate is aggregate
    assert aggregate.open_quantity == Quantity(1)
    assert aggregate.total_fees == Money(1, "USDT")
    assert aggregate.execution_count == 1
    assert aggregate.realized_gross_pnl == Money(0, "USDT")


def test_missing_external_id_is_not_deduplicated() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))

    assert aggregate.execution_count == 2
    assert aggregate.open_quantity == Quantity(2)


def test_execution_links_are_controlled_to_the_aggregate_trade_id() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))
    service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "1", "110"))

    assert all(execution.trade_id == aggregate.trade_id for execution in aggregate.executions)
    assert aggregate.applied_execution_ids == tuple(execution.execution_id for execution in aggregate.executions)


def test_multiple_contexts_are_independent_and_new_trade_starts_after_close() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()
    other_account, other_instrument = make_context()

    first = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "100"))
    other = service.apply(make_execution(other_account, other_instrument, ExecutionSide.SELL, "2", "200"))
    service.apply(make_execution(account_id, instrument_id, ExecutionSide.SELL, "1", "110"))
    replacement = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "1", "90"))

    assert other.direction is TradeDirection.SHORT
    assert other.open_quantity == Quantity(2)
    assert replacement.trade_id != first.trade_id
    assert replacement.status is TradeStatus.OPEN
    assert len(service.all()) == 3


def test_no_float_arithmetic_leaks_into_weighted_average() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "3", "0.1"))
    aggregate = service.apply(make_execution(account_id, instrument_id, ExecutionSide.BUY, "7", "0.2"))

    assert aggregate.average_entry.value == Decimal("0.17")


def test_apply_fact_uses_real_execution_conversion() -> None:
    service = TradeAggregationService()
    account_id, instrument_id = make_context()

    aggregate = service.apply_fact(
        make_fact(account_id, instrument_id, ExecutionSide.BUY, "1", "100", external_execution_id="fact-1")
    )

    assert aggregate.execution_count == 1
    assert aggregate.executions[0].external_execution_id == "fact-1"
