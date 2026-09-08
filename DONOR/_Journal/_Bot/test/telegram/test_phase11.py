import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from aiogram import Dispatcher

from app.application.use_cases._common import view
from app.application.dtos import GetTradeDetailsResult
from app.application.statistics.models import PerformanceSummary
from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition, CustomFieldOption, CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.statistics.ids import CustomFieldDefinitionId
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.telegram.bot import create_dispatcher
from app.telegram.composition import JournalApplication
from app.telegram.config import TelegramSettings
from app.telegram.formatting import compact_statistics_text, details_text
from app.telegram.handlers import unique_exact_active_instrument
from app.telegram.keyboards import choice_keyboard, instrument_selection_keyboard, main_menu_keyboard, stats_period_keyboard, trade_detail_keyboard


NOW = datetime(2026, 9, 3, 12, tzinfo=timezone.utc)


class RuntimeStub(JournalApplication):
    def __init__(self):
        pass


def settings(*, dev_mode=False):
    return TelegramSettings("token-is-never-logged", 123, "postgresql+asyncpg://db", AccountId.generate(), dev_mode)


def make_trade(closed=False):
    trade = Trade.open(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, Price(100), Quantity(1), NOW, "USDT")
    if closed:
        trade.close(Price(110), NOW.replace(hour=13))
    return trade


def test_quick_working_main_menu_has_daily_telegram_actions_and_hides_lab_by_default():
    callbacks = [button.callback_data for row in main_menu_keyboard().inline_keyboard for button in row]
    assert "current" not in callbacks
    assert "open_trades" in callbacks
    assert callbacks == ["new_trade", "open_trades", "attention", "statistics", "settings", "recent_trades"]
    assert "execution_lab" not in callbacks
    dev_callbacks = [button.callback_data for row in main_menu_keyboard(dev_mode=True).inline_keyboard for button in row]
    assert "development" in dev_callbacks


def test_quick_working_main_menu_never_depends_on_mini_app():
    markup = main_menu_keyboard(webapp_url="https://journal.example/miniapp")
    buttons = [button for row in markup.inline_keyboard for button in row]
    assert all(button.web_app is None for button in buttons)
    assert all(button.callback_data != "all_trades" for button in buttons)


def test_selected_trade_actions_differ_for_open_and_closed():
    open_callbacks = [button.callback_data for row in trade_detail_keyboard(view(make_trade())).inline_keyboard for button in row]
    closed_callbacks = [button.callback_data for row in trade_detail_keyboard(view(make_trade(closed=True))).inline_keyboard for button in row]
    assert any(item.startswith("close:") for item in open_callbacks)
    assert not any(item.startswith("close:") for item in closed_callbacks)
    assert any(item.startswith("enrich:") for item in closed_callbacks)
    assert not any("Обновить" in item for item in open_callbacks + closed_callbacks)


def test_dynamic_choice_keyboard_uses_catalog_options_and_safe_option_identity():
    field = CustomFieldDefinition.create("trade_quality_test", "Trade quality", CustomFieldValueType.CHOICE, CustomFieldSource.MANUAL, CustomFieldPhase.OPEN, required=True, created_at=NOW)
    options = tuple(CustomFieldOption.create(field.id, code, code.upper()) for code in ("a", "b", "c"))
    keyboard = choice_keyboard(options)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.text for button in buttons[:3]] == ["A", "B", "C"]
    assert [button.callback_data for button in buttons[:3]] == [f"field_option:{item.id}" for item in options]


def test_instrument_selection_keyboard_uses_short_symbols_and_internal_ids():
    from app.application.dtos import InstrumentView

    instrument_id = InstrumentId.generate()
    keyboard = instrument_selection_keyboard((InstrumentView(instrument_id, "BTCUSDT", "Bitcoin / Tether", "BYBIT", "SPOT", True),))
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert buttons[0].text == "BTCUSDT"
    assert buttons[0].callback_data == f"instrument:{instrument_id}"
    assert "UUID" not in buttons[0].text


def test_telegram_instrument_search_auto_selects_only_unique_exact_active_symbol():
    from app.application.dtos import InstrumentView

    exact = InstrumentView(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR", True)
    dated = InstrumentView(InstrumentId.generate(), "BTCUSDT-11SEP26", "Future", "BYBIT", "LINEAR", True)
    inactive = InstrumentView(InstrumentId.generate(), "BTCUSDT", "Old", "BYBIT", "LINEAR", False)
    assert unique_exact_active_instrument((exact, dated, inactive), "btcusdt") is exact
    assert unique_exact_active_instrument((exact, inactive), "BTCUSDT") is exact
    assert unique_exact_active_instrument((exact, InstrumentView(InstrumentId.generate(), "BTCUSDT", "Duplicate", "BYBIT", "LINEAR", True)), "BTCUSDT") is None
    assert unique_exact_active_instrument((exact, dated), "BTC") is None


def test_production_dispatcher_composition_smoke_without_network():
    dispatcher = create_dispatcher(RuntimeStub(), settings())
    assert isinstance(dispatcher, Dispatcher)
    assert len(dispatcher.sub_routers) == 1


def test_phase11_imports_are_separated_from_orm_handlers():
    import inspect
    from app.telegram import handlers

    source = inspect.getsource(handlers).lower()
    assert "sqlalchemy" not in source
    assert "asyncsession" not in source
    assert "miniapp_" not in source


def test_new_trade_uses_catalog_search_and_never_prompts_for_uuid():
    import inspect
    from app.telegram import handlers

    source = inspect.getsource(handlers)
    assert "Введите тикер, символ или название инструмента." in source
    assert "Введите ID инструмента (UUID)." not in source
    assert "SearchInstrumentsCommand" in source


def test_production_fresh_detail_path_keeps_trade_dto_out_of_fsm_and_uses_selected_id_only():
    import inspect
    from app.telegram import handlers

    source = inspect.getsource(handlers)
    assert "selected_trade_id" in source
    assert "trade_dto" not in source.lower()
    assert "InstrumentId(data[\"selected_instrument_id\"])" in source


def test_mutations_return_through_fresh_trade_details_path():
    import inspect
    from app.telegram import handlers

    source = inspect.getsource(handlers)
    assert source.count('await show_details(message, data["selected_trade_id"])') >= 2
    assert 'await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))' in source
    assert "selected_trade_id" in source
    assert "TradeView" not in source


def test_quick_mode_details_show_take_profit_and_human_readiness_without_identifiers():
    trade = Trade.open(
        AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG,
        Price(100), Quantity(2), NOW, "USDT", take_profit=Price(125),
    )
    text = details_text(GetTradeDetailsResult(view(trade), ()))
    assert "Take Profit: 125" in text
    assert "Текущая готовность: ОТКРЫТА" in text
    assert str(trade.trade_id) not in text
    assert "INCOMPLETE" not in text
    assert "READY" not in text


def test_quick_mode_statistics_are_compact_and_use_percentage_win_rate():
    summary = PerformanceSummary(
        sample_size=4, trade_count=4, win_count=2, loss_count=1, breakeven_count=1,
        win_rate=Decimal("0.5"), gross_pnl=30, net_pnl=25, total_fees=5, total_expenses=0,
        average_net_pnl=6.25, average_win=20, average_loss=-10, profit_factor=2,
        expectancy=6.25, largest_win=20, largest_loss=-10, median_net_pnl=5,
        currency="USDT", ready_count=4, excluded_incomplete_count=1, open_count=2,
    )
    text = compact_statistics_text(summary, "7 дней")
    assert "Win Rate: 50%" in text
    assert "Готовы к статистике: 4" in text
    assert "Не заполнены: 1" in text
    callbacks = [button.callback_data for row in stats_period_keyboard().inline_keyboard for button in row]
    assert callbacks[:4] == ["stats_period:today", "stats_period:7d", "stats_period:30d", "stats_period:all"]
