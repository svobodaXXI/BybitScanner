from app.core.trades.enums import (
    EntryMethod,
    ExitMethod,
    TradeDirection,
    TradeSide,
    TradeStatus,
    TradingType,
)


def test_trade_status_values() -> None:
    assert {item.value for item in TradeStatus} == {
        "DRAFT",
        "PLANNED",
        "OPEN",
        "CLOSED",
        "CANCELLED",
    }


def test_trade_direction_values() -> None:
    assert {item.value for item in TradeDirection} == {"LONG", "SHORT", "NEUTRAL"}


def test_trade_side_values() -> None:
    assert {item.value for item in TradeSide} == {"BUY", "SELL"}


def test_trading_type_values() -> None:
    assert {item.value for item in TradingType} == {
        "SINGLE_INSTRUMENT",
        "SPREAD",
        "FUNDING",
    }


def test_entry_method_values() -> None:
    assert {item.value for item in EntryMethod} == {"MARKET", "LIMIT"}


def test_exit_method_values() -> None:
    assert {item.value for item in ExitMethod} == {"MARKET", "LIMIT"}

