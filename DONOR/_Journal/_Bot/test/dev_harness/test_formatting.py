from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.dev_harness.formatting import format_expenses, format_trade, format_trade_list


def make_trade() -> Trade:
    return Trade.open(
        AccountId.generate(),
        InstrumentId.generate(),
        TradeDirection.LONG,
        Price(100),
        Quantity(2),
        datetime(2026, 1, 1, 10, tzinfo=timezone.utc),
        "USDT",
    )


def test_formatting_shows_domain_values_and_signed_expenses() -> None:
    trade = make_trade()
    trade.add_fee(Money(2, "USDT"))
    trade.add_expense(Expense(Money(5, "USDT")))
    trade.add_expense(Expense(Money(-1, "USDT")))
    trade.close(Price(110), datetime(2026, 1, 1, 11, tzinfo=timezone.utc))

    text = format_trade(trade, "BTCUSDT")

    assert "Инструмент: BTCUSDT" in text
    assert "Валовая прибыль: +20 USDT" in text
    assert "Чистая прибыль: +22 USDT" in text
    assert "Комиссии: -2 USDT" in text
    assert "+5 USDT" in text
    assert "-1 USDT" in text
    assert "Итог с учётом знака: +4 USDT" in text


def test_open_trade_format_uses_zero_fee_and_optional_placeholders() -> None:
    text = format_trade(make_trade(), "BTCUSDT")

    assert "Комиссии: 0 USDT" in text
    assert "Риск: —" in text
    assert "Валовая прибыль: —" in text
    assert "Чистая прибыль: —" in text


def test_format_expenses_empty_state_is_explicit() -> None:
    text = format_expenses((), "USDT")

    assert "Расходы:\n—" in text
    assert "Итог с учётом знака: 0 USDT" in text


def test_trade_list_shows_open_and_closed_trades() -> None:
    open_trade = make_trade()
    closed_trade = make_trade()
    closed_trade.close(Price(110), datetime(2026, 1, 1, 11, tzinfo=timezone.utc))

    text = format_trade_list(((open_trade, "BTCUSDT"), (closed_trade, "ETHUSDT")))

    assert "ОТКРЫТА\nBTCUSDT | LONG | Вход 100 | Кол-во 2" in text
    assert "ЗАКРЫТА\nETHUSDT | LONG | Чистая прибыль +20 USDT" in text
