import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.application.dtos import GetTradeDetailsResult, InstrumentView, TradeView
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.telegram.bot import notify_new_trades
from app.telegram.config import TelegramSettings


NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


def _trade():
    return Trade.open(
        AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG,
        Price("100"), Quantity("0.25"), NOW, "USDT",
    )


class BotFake:
    def __init__(self, *, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("Telegram transport unavailable")
        self.sent.append((args, kwargs))


class RuntimeFake:
    def __init__(self, trade):
        self.trade = trade
        self.instrument = InstrumentView(trade.instrument_id, "ZECUSDT", "ZEC", "BYBIT", "LINEAR", True)
        self.requested = []

    async def get_trade_details(self, command):
        self.requested.append(command.trade_id)
        return GetTradeDetailsResult(TradeView.from_trade(self.trade), (), self.instrument)


def test_new_trade_notification_routes_exact_trade_id_and_has_safe_buttons():
    trade = _trade()
    runtime = RuntimeFake(trade)
    bot = BotFake()
    summary = SimpleNamespace(created_trade_ids=(str(trade.trade_id),))

    asyncio.run(notify_new_trades(bot, runtime, TelegramSettings("token", 123, "db", trade.account_id), summary))

    assert runtime.requested == [trade.trade_id]
    assert len(bot.sent) == 1
    args, kwargs = bot.sent[0]
    assert args[0] == 123
    assert "ZECUSDT" in args[1]
    callbacks = [button.callback_data for row in kwargs["reply_markup"].inline_keyboard for button in row]
    assert callbacks == [f"edit:{trade.trade_id}", "open_trades"]
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)


def test_notification_transport_failure_does_not_raise_or_change_persistence_path():
    trade = _trade()
    runtime = RuntimeFake(trade)
    bot = BotFake(fail=True)
    summary = SimpleNamespace(created_trade_ids=(str(trade.trade_id),))

    asyncio.run(notify_new_trades(bot, runtime, TelegramSettings("token", 123, "db", trade.account_id), summary))

    assert runtime.requested == [trade.trade_id]
    assert bot.sent == []


def test_empty_created_trade_list_sends_nothing():
    bot = BotFake()
    asyncio.run(notify_new_trades(
        bot, RuntimeFake(_trade()), TelegramSettings("token", 123, "db", AccountId.generate()),
        SimpleNamespace(created_trade_ids=()),
    ))
    assert bot.sent == []
