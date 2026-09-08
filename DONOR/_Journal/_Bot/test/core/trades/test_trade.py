from datetime import datetime, timedelta, timezone

import pytest

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


OPENED_AT = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)


def make_trade(
    direction: TradeDirection = TradeDirection.LONG,
    *,
    quantity: Quantity | None = None,
) -> Trade:
    return Trade.open(
        AccountId.generate(),
        InstrumentId.generate(),
        direction,
        Price("100"),
        quantity or Quantity("2"),
        OPENED_AT,
        "usd",
    )


@pytest.mark.parametrize("direction", [TradeDirection.LONG, TradeDirection.SHORT])
def test_trade_open_creates_valid_open_trade(direction: TradeDirection) -> None:
    trade = make_trade(direction)

    assert isinstance(trade.trade_id, TradeId)
    assert trade.direction is direction
    assert trade.status is TradeStatus.OPEN
    assert trade.opened_at == OPENED_AT
    assert trade.closed_at is None
    assert trade.exit_price is None
    assert trade.gross_pnl is None
    assert trade.net_pnl is None
    assert trade.quantity == Quantity("2")
    assert trade.fees == Money(0, "USD")


def test_trade_open_supports_stop_risk_fees_and_initial_expenses() -> None:
    trade = Trade.open(
        AccountId.generate(),
        InstrumentId.generate(),
        TradeDirection.LONG,
        Price("100"),
        Quantity("2"),
        OPENED_AT,
        "USD",
        stop_price=Price("95"),
        risk=Risk(Money("10", "USD")),
        fees=Money("3", "USD"),
        expenses=(Expense(Money("5", "USD")),),
    )

    assert trade.stop_price == Price("95")
    assert trade.risk == Risk(Money("10", "USD"))
    assert trade.fees == Money("3", "USD")
    assert trade.expenses == (Expense(Money("5", "USD")),)


def test_trade_open_rejects_zero_quantity() -> None:
    with pytest.raises(ValueError):
        make_trade(quantity=Quantity(0))


def test_trade_open_rejects_naive_opened_at() -> None:
    with pytest.raises(ValueError):
        Trade.open(
            AccountId.generate(),
            InstrumentId.generate(),
            TradeDirection.LONG,
            Price(100),
            Quantity(1),
            datetime(2026, 1, 1, 10),
            "USD",
        )


@pytest.mark.parametrize(
    ("direction", "exit_price", "expected_gross"),
    [
        (TradeDirection.LONG, "110", "20"),
        (TradeDirection.LONG, "90", "-20"),
        (TradeDirection.SHORT, "90", "20"),
        (TradeDirection.SHORT, "110", "-20"),
    ],
)
def test_trade_close_calculates_long_and_short_gross_pnl(
    direction: TradeDirection,
    exit_price: str,
    expected_gross: str,
) -> None:
    trade = make_trade(direction)

    result = trade.close(Price(exit_price), OPENED_AT + timedelta(hours=1))

    assert result is trade
    assert trade.status is TradeStatus.CLOSED
    assert trade.closed_at == OPENED_AT + timedelta(hours=1)
    assert trade.exit_price == Price(exit_price)
    assert trade.gross_pnl == Money(expected_gross, "USD")
    assert trade.net_pnl == Money(expected_gross, "USD")


def test_trade_net_pnl_applies_fees_and_positive_expense() -> None:
    trade = make_trade()
    trade.add_fee(Money("10", "USD"))
    trade.add_expense(Expense(Money("25", "USD")))

    trade.close(Price("110"), OPENED_AT + timedelta(minutes=5))

    assert trade.gross_pnl == Money("20", "USD")
    assert trade.net_pnl == Money("35", "USD")


def test_trade_net_pnl_applies_negative_expense() -> None:
    trade = make_trade()
    trade.add_fee(Money("10", "USD"))
    trade.add_expense(Expense(Money("-25", "USD")))

    trade.close(Price("110"), OPENED_AT + timedelta(minutes=5))

    assert trade.net_pnl == Money("-15", "USD")


def test_trade_net_pnl_sums_multiple_expenses() -> None:
    trade = make_trade()
    trade.add_expense(Expense(Money("25", "USD")))
    trade.add_expense(Expense(Money("-5", "USD")))

    trade.close(Price("110"), OPENED_AT + timedelta(minutes=5))

    assert trade.net_pnl == Money("40", "USD")


def test_trade_rejects_negative_fee_and_currency_mismatches() -> None:
    trade = make_trade()

    with pytest.raises(ValueError):
        trade.add_fee(Money("-1", "USD"))
    with pytest.raises(ValueError):
        trade.add_fee(Money("1", "RUB"))
    with pytest.raises(ValueError):
        trade.add_expense(Expense(Money("1", "RUB")))


def test_trade_close_rejects_naive_or_early_timestamp() -> None:
    trade = make_trade()

    with pytest.raises(ValueError):
        trade.close(Price("110"), datetime(2026, 1, 1, 11))
    with pytest.raises(ValueError):
        trade.close(Price("110"), OPENED_AT - timedelta(seconds=1))


def test_trade_can_only_be_closed_once() -> None:
    trade = make_trade()
    trade.close(Price("110"), OPENED_AT + timedelta(hours=1))

    with pytest.raises(ValueError):
        trade.close(Price("120"), OPENED_AT + timedelta(hours=2))


def test_trade_rejects_neutral_direction_for_phase_one_pnl() -> None:
    trade = make_trade(TradeDirection.NEUTRAL)

    with pytest.raises(ValueError):
        trade.close(Price("110"), OPENED_AT + timedelta(hours=1))


def test_trade_normalizes_aware_timestamps_to_utc() -> None:
    opened_at = datetime(2026, 1, 1, 13, 0, tzinfo=timezone(timedelta(hours=3)))
    trade = Trade.open(
        AccountId.generate(),
        InstrumentId.generate(),
        TradeDirection.LONG,
        Price(100),
        Quantity(1),
        opened_at,
        "USD",
    )

    assert trade.opened_at == datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)

