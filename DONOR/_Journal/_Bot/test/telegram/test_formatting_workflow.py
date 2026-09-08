from datetime import datetime, timezone
from decimal import Decimal

from app.application.dtos import GetTradeDetailsResult, TradeView, InstrumentView
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.trades.enums import TradeDirection
from app.core.trades.readiness import evaluate_trade_readiness
from app.core.trades.trade import Trade
from app.telegram.formatting import compact_open_trade_text, compact_recent_trade_text, details_text, planned_rr_text


NOW = datetime(2026, 9, 5, 5, 16, 34, tzinfo=timezone.utc)


def make_trade(direction=TradeDirection.LONG, *, stop=None, take=None):
    trade = Trade.open(
        AccountId.generate(), InstrumentId.generate(), direction,
        Price("1019.55"), Quantity("0.01"), NOW, "USDT",
        stop_price=stop, take_profit=take, fees=Money("0.01376318", "USDT"),
    )
    trade.close(Price("1009.28"), datetime(2026, 9, 5, 7, 11, 22, tzinfo=timezone.utc))
    return trade


def test_closed_imported_card_is_clean_localized_and_hides_gross_pnl():
    trade = make_trade()
    instrument = InstrumentView(trade.instrument_id, "ZECUSDT", "ZEC/USDT", "BYBIT", "LINEAR", True)
    required = tuple(
        CustomFieldDefinition.create(code, name, CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, CustomFieldPhase.POST_TRADE, required_for_statistics=True)
        for code, name in (("strategy", "Стратегия"), ("setup", "Сетап"), ("followed_plan", "По плану?"))
    )
    readiness = evaluate_trade_readiness(trade, required_dynamic_fields=required)
    text = details_text(
        GetTradeDetailsResult(TradeView.from_trade(trade), (), instrument, readiness, required),
        timezone_name="Europe/Moscow",
    )

    assert "Инструмент: ZECUSDT" in text
    assert "ZEC/USDT" not in text
    assert "05.09.2026 08:16:34" in text
    assert "05.09.2026 10:11:22" in text
    assert "Комиссии: 0.01376318 USDT" in text
    assert "Gross PnL" not in text
    assert "Net PnL: -0.11646318 USDT" in text
    assert "Готовность: ⚠ НЕ ГОТОВА" in text
    assert "Стратегия: —" in text and "Сетап: —" in text and "По плану?: —" in text
    assert trade.opened_at.hour == 5


def test_planned_rr_supports_long_short_missing_and_invalid_levels():
    assert planned_rr_text(make_trade(stop=Price("1000"), take=Price("1060"))) == "1:2.07"
    short = make_trade(TradeDirection.SHORT, stop=Price("1040"), take=Price("980"))
    assert planned_rr_text(short) == "1:1.93"
    assert planned_rr_text(make_trade(stop=Price("1000"))) == "—"
    assert planned_rr_text(make_trade(stop=Price("1020"), take=Price("1060"))) == "—"


def test_recent_card_uses_symbol_only_compact_pnl_and_localized_status():
    trade = make_trade()
    instrument = InstrumentView(trade.instrument_id, "ZECUSDT", "ZEC/USDT", "BYBIT", "LINEAR", True)

    text = compact_recent_trade_text(trade, instrument, index=1)

    assert text == "1. ZECUSDT\nLONG · ЗАКРЫТА\nNet PnL: -0.1165 USDT"
    assert "ZEC/USDT" not in text
    assert "?" not in text


def test_open_card_has_current_state_without_exit_facts_or_unrealized_pnl():
    trade = Trade.open(
        AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG,
        Price("1019.55"), Quantity("0.01"), NOW, "USDT",
        stop_price=Price("1000"), take_profit=Price("1060"), fees=Money("0.01", "USDT"),
    )
    instrument = InstrumentView(trade.instrument_id, "BTCUSDT", "BTC/USDT", "BYBIT", "LINEAR", True)
    text = details_text(
        GetTradeDetailsResult(TradeView.from_trade(trade), (), instrument, evaluate_trade_readiness(trade), ()),
        timezone_name="UTC",
    )

    assert text.startswith("🟢 СДЕЛКА ОТКРЫТА")
    assert "Количество / текущий объём: 0.01" in text
    assert "Статус: 🟢 ОТКРЫТА" in text
    assert "Выход:" not in text
    assert "Дата/время выхода:" not in text
    assert "Net PnL: — (сделка ещё открыта)" in text
    assert "BTC/USDT" not in text
    assert "ОТКРЫТА" in compact_open_trade_text(trade, instrument)
