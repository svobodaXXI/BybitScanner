from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.dev_harness.config import is_authorized
from app.dev_harness.state import InMemoryTradeStore


def make_trade() -> Trade:
    return Trade.open(
        AccountId.generate(),
        InstrumentId.generate(),
        TradeDirection.LONG,
        Price(100),
        Quantity(1),
        datetime.now(timezone.utc),
        "USDT",
    )


def test_store_supports_multiple_trades_and_lookup_by_trade_id() -> None:
    store = InMemoryTradeStore()
    first = make_trade()
    second = make_trade()

    store.add(first, "BTCUSDT")
    store.add(second, "ETHUSDT")
    assert store.get(first.trade_id) is first
    assert store.get_by_string(str(second.trade_id)) is second
    assert store.open() == sorted((first, second), key=lambda trade: (trade.opened_at, str(trade.trade_id)))
    assert len(store.all()) == 2
    assert store.symbol_for(first) == "BTCUSDT"


def test_store_keeps_closed_trades() -> None:
    store = InMemoryTradeStore()
    trade = make_trade()
    trade.close(Price(110), datetime.now(timezone.utc))
    store.add(trade, "BTCUSDT")

    assert store.get(trade.trade_id) is trade
    assert store.all() == [trade]


def test_authorization_helper_requires_exact_configured_user() -> None:
    assert is_authorized(123, 123)
    assert not is_authorized(124, 123)
    assert not is_authorized(123, None)
