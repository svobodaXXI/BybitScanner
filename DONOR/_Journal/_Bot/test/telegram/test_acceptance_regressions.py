from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio

from app.application.dtos import GetTradeDetailsResult, ListAllTradesResult, TradeView, InstrumentView
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from app.core.accounts.account_id import AccountId
from app.core.imports import HistoryProgress
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition, CustomFieldOption
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.trades.readiness import TradeReadiness, TradeReadinessStatus
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.telegram.composition import JournalApplication
from app.telegram.config import TelegramSettings
from app.telegram.handlers import create_router, _edit_message_safely, _bounded_telegram_payload
from app.telegram.errors import user_error
from app.infrastructure.exchanges.bybit.errors import BybitRequestError
from app.telegram.keyboards import (
    attention_keyboard,
    choice_keyboard,
    field_definition_keyboard,
    field_management_keyboard,
    main_menu_keyboard,
    recent_trades_keyboard,
    trade_detail_keyboard,
    trade_edit_keyboard,
    trade_list_keyboard,
    yes_no_keyboard,
    bybit_new_only_keyboard,
    excluded_trades_keyboard,
)
from app.core.trades.readiness import evaluate_trade_readiness
from app.core.monitoring import ReminderSettings


NOW = datetime(2026, 9, 5, 5, tzinfo=timezone.utc)


def _trade(index: int, *, closed: bool = True):
    trade = Trade.open(
        AccountId.generate(), InstrumentId.generate(),
        TradeDirection.LONG if index % 2 else TradeDirection.SHORT,
        Price(100 + index), Quantity("0.01"), NOW + timedelta(minutes=index), "USDT",
    )
    if closed:
        trade.close(Price(101 + index), NOW + timedelta(minutes=index + 1))
    return trade


def _instrument(trade, index: int):
    return InstrumentView(trade.instrument_id, f"COIN{index}USDT", f"Coin {index}", "BYBIT", "LINEAR", True)


def _buttons(markup):
    return [button for row in markup.inline_keyboard for button in row]


def test_all_telegram_callback_data_stays_within_64_byte_limit():
    trade = _trade(1)
    view = TradeView.from_trade(trade)
    instrument = _instrument(trade, 1)
    fields = tuple(
        CustomFieldDefinition.create(code, name, value_type, CustomFieldSource.MANUAL, CustomFieldPhase.POST_TRADE)
        for code, name, value_type in (
            ("strategy", "Стратегия", CustomFieldValueType.CHOICE),
            ("setup", "Сетап", CustomFieldValueType.CHOICE),
            ("followed_plan", "По плану?", CustomFieldValueType.YES_NO),
            ("error", "Ошибка", CustomFieldValueType.CHOICE),
            ("comment", "Комментарий", CustomFieldValueType.TEXT),
        )
    )
    options = tuple(CustomFieldOption.create(fields[0].id, code, label) for code, label in (
        ("trend_continuation", "Продолжение тренда"), ("consolidation", "Консолидация"), ("other", "Другое")
    ))
    attention = SimpleNamespace(
        trade_id=trade.trade_id,
        instrument_label="ZECUSDT",
        readiness=TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("dynamic_field:" + str(fields[0].id),)),
    )
    markups = (
        main_menu_keyboard(),
        trade_detail_keyboard(view, imported=True),
        trade_edit_keyboard(view, fields, imported=True),
        choice_keyboard(options),
        yes_no_keyboard(),
        attention_keyboard((attention,)),
        field_management_keyboard(fields),
        field_definition_keyboard(fields[0], options),
        recent_trades_keyboard((trade,), (instrument,)),
        recent_trades_keyboard((trade,), (instrument,), offset=5, has_next=True),
        trade_list_keyboard((view,), offset=50, limit=50, has_next=True, all_trades=True),
    )
    for markup in markups:
        for button in _buttons(markup):
            if button.callback_data is not None:
                assert len(button.callback_data.encode("utf-8")) <= 64, button.callback_data


def test_recent_trades_keyboard_has_distinct_trade_bound_buttons_and_pages():
    trades = tuple(_trade(index) for index in range(1, 8))
    instruments = tuple(_instrument(trade, index) for index, trade in enumerate(trades, 1))

    page_one = recent_trades_keyboard(trades[:5], instruments[:5], has_next=True)
    page_two = recent_trades_keyboard(trades[5:], instruments[5:], offset=5)

    page_one_buttons = _buttons(page_one)
    page_two_buttons = _buttons(page_two)
    assert [button.text for button in page_one_buttons[:5]] == [f"{index} · COIN{index}USDT" for index in range(1, 6)]
    assert [button.callback_data for button in page_one_buttons[:5]] == [f"recent_trade:{trade.trade_id}:0" for trade in trades[:5]]
    assert [button.text for button in page_two_buttons[:2]] == ["6 · COIN6USDT", "7 · COIN7USDT"]
    assert page_one_buttons[5].callback_data == "recent:page:5"
    assert page_two_buttons[2].callback_data == "recent:page:0"
    assert len({button.callback_data for button in page_one_buttons[:5]}) == 5


class _Message(Message):
    def __init__(self):
        pass

    async def edit_text(self, text, reply_markup=None):
        object.__setattr__(self, "edited", (text, reply_markup))


class _UnchangedMessage:
    async def edit_text(self, text, reply_markup=None):
        raise TelegramBadRequest(method=None, message="Bad Request: message is not modified")


class _ProgressMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, reply_markup=None):
        self.edits.append((text, reply_markup))


def test_discovery_error_keeps_safe_bybit_message_and_identical_error_screen_is_noop():
    error = BybitRequestError("Bybit API request failed:\nretCode=10001\nretMsg=invalid request")
    assert "retCode=10001" in user_error(error)
    async def retry_error_screen():
        await _edit_message_safely(_UnchangedMessage(), user_error(error), None)
        await _edit_message_safely(_UnchangedMessage(), user_error(error), None)
    asyncio.run(retry_error_screen())


def test_cached_bybit_history_menu_does_not_scan_and_refresh_explicitly_scans():
    from app.core.imports import ExchangeImportSettings, SupportedHistoryDiscovery

    account = AccountId.generate()
    available = datetime(2025, 11, 4, 18, 37, 30, 760000, tzinfo=timezone.utc)

    class HistoryRuntime:
        bybit_history_lookback_start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        def __init__(self):
            self.settings = ExchangeImportSettings(account, "BYBIT", history_available_from=available)
            self.discovery_calls = 0

        async def get_exchange_import_settings(self, account_id, exchange):
            return self.settings

        async def discover_bybit_history(self, **kwargs):
            self.discovery_calls += 1
            return SupportedHistoryDiscovery("SUPPORTED", available, available, available, 1, 0, None)

        async def get_reminder_settings(self, account_id):
            return ReminderSettings(timezone_name="UTC")

    runtime = HistoryRuntime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", account))
    state = _State()
    cached = _Callback.make("settings_bybit_history")
    asyncio.run(_handler(router, "handle_settings_bybit_history")(cached, state))
    assert runtime.discovery_calls == 0
    assert "04.11.2025" in cached.message.edited[0]
    refreshed = _Callback.make("bybit:refresh")
    asyncio.run(_handler(router, "handle_bybit_refresh")(refreshed, state))
    assert runtime.discovery_calls == 1
    assert refreshed.answers


def test_bybit_preview_uses_one_message_and_only_final_state_has_full_keyboard():
    class PreviewRuntime:
        def __init__(self):
            self.calls = 0
            self.persisted = datetime(2025, 1, 1, tzinfo=timezone.utc)

        async def get_exchange_import_settings(self, account_id, exchange):
            return SimpleNamespace(history_available_from=self.persisted)

        async def preview_bybit_import(self, selection, *, progress_callback):
            self.calls += 1
            await progress_callback(HistoryProgress("fetch", 3, 1, 12))
            await progress_callback(HistoryProgress("aggregate", 0, 0, 12))
            return SimpleNamespace(
                selected_start=selection.selected_start,
                selected_end=selection.selected_end,
                execution_count=12,
                logical_trade_count=4,
                symbol_count=2,
                already_imported_trade_count=1,
                would_import_trade_count=3,
                boundary_crossing_trade_count=1,
            ), SimpleNamespace(token="preview-token")

    runtime = PreviewRuntime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:mode:LAST_30_DAYS")
    message = _ProgressMessage()
    object.__setattr__(callback, "message", message)
    state = _State()
    asyncio.run(state.update_data(
        history_available_from=datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    ))

    asyncio.run(_handler(router, "handle_bybit_mode")(callback, state))

    assert runtime.calls == 1
    assert callback.answers
    assert len(message.edits) >= 3
    assert all(markup is None for _, markup in message.edits[:-1])
    assert message.edits[-1][1] is not None
    assert "Исполнений: 12" in message.edits[-1][0]


def test_duplicate_bybit_preview_tap_answers_without_starting_second_job():
    class PreviewRuntime:
        calls = 0

        async def preview_bybit_import(self, selection, *, progress_callback):
            self.calls += 1
            raise AssertionError("duplicate preview job started")

    runtime = PreviewRuntime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:mode:LAST_30_DAYS")
    state = _State()
    asyncio.run(state.update_data(
        history_available_from=datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat(),
        preview_in_progress=True,
        operation_id="preview-existing",
    ))

    asyncio.run(_handler(router, "handle_bybit_mode")(callback, state))

    assert runtime.calls == 0
    assert any("уже выполняется" in args[0] for args, _ in callback.answers)


def test_new_only_is_setup_confirmation_and_not_import_preview():
    class Runtime:
        async def get_exchange_import_settings(self, account_id, exchange):
            return SimpleNamespace(history_available_from=datetime(2025, 1, 1, tzinfo=timezone.utc))

        async def start_bybit_tracking(self, tracking_start_at):
            return SimpleNamespace(tracking_start_at=tracking_start_at)

    runtime = Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:mode:NEW_ONLY")
    state = _State()
    asyncio.run(state.update_data(
        history_available_from=datetime(2025, 1, 1, tzinfo=timezone.utc).isoformat()
    ))

    asyncio.run(_handler(router, "handle_bybit_mode")(callback, state))

    text, markup = callback.message.edited
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert "Начать вести журнал с:" in text
    assert "Старые сделки импортированы не будут." in text
    assert "bybit:new-only:confirm" in callbacks
    assert "bybit:confirm" not in callbacks
    assert all("Импортировать" not in button.text for button in _buttons(bybit_new_only_keyboard()))


def test_new_only_confirmation_persists_tracking_start_without_import_job():
    class Runtime:
        def __init__(self):
            self.starts = []

        async def start_bybit_tracking(self, tracking_start_at):
            self.starts.append(tracking_start_at)
            return SimpleNamespace(tracking_start_at=tracking_start_at)

    runtime = Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:new-only:confirm")
    state = _State()
    start = datetime(2026, 9, 6, tzinfo=timezone.utc)
    asyncio.run(state.update_data(history_new_only_start=start.isoformat()))

    asyncio.run(_handler(router, "handle_bybit_new_only_confirm")(callback, state))

    assert runtime.starts == [start]
    assert state.data == {}
    assert "Журнал начат с 06.09.2026" in callback.message.edited[0]


def test_empty_fsm_uses_persisted_boundary_and_stale_fsm_does_not_override_it():
    class Runtime:
        def __init__(self):
            self.persisted = datetime(2025, 11, 4, tzinfo=timezone.utc)
            self.selection = None

        async def get_exchange_import_settings(self, account_id, exchange):
            return SimpleNamespace(history_available_from=self.persisted)

        async def preview_bybit_import(self, selection, *, progress_callback):
            self.selection = selection
            return SimpleNamespace(
                selected_start=selection.selected_start, selected_end=selection.selected_end,
                execution_count=0, logical_trade_count=0, symbol_count=0,
                already_imported_trade_count=0, would_import_trade_count=0,
                boundary_crossing_trade_count=0,
            ), SimpleNamespace(token="token")

    runtime = Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:mode:ALL_AVAILABLE")
    state = _State()

    asyncio.run(_handler(router, "handle_bybit_mode")(callback, state))

    assert runtime.selection.supported_history_from == runtime.persisted
    assert "history_available_from" in state.data


def test_mode_callback_without_persisted_boundary_redirects_safely_without_discovery():
    class Runtime:
        discovery_calls = 0

        async def get_exchange_import_settings(self, account_id, exchange):
            return None

        async def discover_bybit_history(self, **kwargs):
            self.discovery_calls += 1

    runtime = Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    callback = _Callback.make("bybit:mode:LAST_30_DAYS")
    state = _State()

    asyncio.run(_handler(router, "handle_bybit_mode")(callback, state))

    assert runtime.discovery_calls == 0
    assert "История Bybit ещё не подготовлена" in callback.message.edited[0]
    assert callback.message.edited[1] is not None
    assert callback.answers


class _Callback(CallbackQuery):
    @classmethod
    def make(cls, data):
        callback = cls.model_construct()
        object.__setattr__(callback, "data", data)
        object.__setattr__(callback, "message", _Message.model_construct())
        object.__setattr__(callback.message, "edited", None)
        object.__setattr__(callback, "answers", [])
        return callback

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _State:
    def __init__(self):
        self.data = {}

    async def clear(self):
        self.data.clear()

    async def update_data(self, **values):
        self.data.update(values)

    async def get_data(self):
        return dict(self.data)

    async def set_state(self, value):
        self.state = value


class _Runtime:
    def __init__(self, trade, instrument, fields=(), options=()):
        self.trade = trade
        self.instrument = instrument
        self.fields = tuple(fields)
        self.options = tuple(options)
        self.requested_trade_ids = []
        self.saved_values = []

    async def get_trade_details(self, command):
        self.requested_trade_ids.append(command.trade_id)
        return GetTradeDetailsResult(
            TradeView.from_trade(self.trade), (), self.instrument,
            evaluate_trade_readiness(self.trade), (), False,
        )

    async def get_instrument(self, instrument_id):
        return self.instrument

    async def list_custom_fields(self):
        return self.fields

    async def list_custom_field_options(self, field_id, *, include_inactive=False):
        return tuple(item for item in self.options if item.field_id == field_id and (include_inactive or item.active))

    async def upsert_manual_custom_value(self, command):
        self.saved_values.append(command)

    async def get_reminder_settings(self, account_id):
        return ReminderSettings(timezone_name="Europe/Moscow")


def _handler(router, name):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


def test_real_detail_button_opens_editor_with_exact_trade_id_for_closed_trade():
    trade = _trade(1)
    instrument = _instrument(trade, 1)
    detail_markup = trade_detail_keyboard(TradeView.from_trade(trade), imported=True)
    edit_button = next(button for button in _buttons(detail_markup) if button.callback_data.startswith("edit:"))
    callback = _Callback.make(edit_button.callback_data)
    state = _State()
    runtime = _Runtime(trade, instrument)
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))

    asyncio.run(_handler(router, "handle_edit")(callback, state))

    assert runtime.requested_trade_ids == [trade.trade_id]
    assert state.data["selected_trade_id"] == str(trade.trade_id)
    assert "Редактирование сделки" in callback.message.edited[0]
    edit_markup = callback.message.edited[1]
    edit_callbacks = [button.callback_data for button in _buttons(edit_markup)]
    assert "edit:stop" in edit_callbacks
    assert "edit:take" in edit_callbacks
    assert callback.answers


def test_recent_detail_button_routes_to_the_exact_selected_trade():
    trade = _trade(7)
    instrument = _instrument(trade, 7)
    markup = recent_trades_keyboard((trade,), (instrument,))
    callback = _Callback.make(_buttons(markup)[0].callback_data)
    runtime = _Runtime(trade, instrument)
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))

    asyncio.run(_handler(router, "handle_recent_trade_selection")(callback))

    assert runtime.requested_trade_ids == [trade.trade_id]
    assert "Инструмент: COIN7USDT" in callback.message.edited[0]
    assert "Дата/время входа: 05.09.2026 08:07:00" in callback.message.edited[0]


def test_attention_105_items_are_paginated_with_exact_trade_callbacks():
    trades = tuple(_trade(index, closed=True) for index in range(1, 106))
    items = tuple(
        __import__("app.application.attention", fromlist=["AttentionItem"]).AttentionItem(
            TradeView.from_trade(trade),
            TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("NET_PNL",)),
            _instrument(trade, index),
            ("Результат",),
        )
        for index, trade in enumerate(trades, 1)
    )

    class Runtime:
        async def attention(self, *, account_id=None, instrument_id=None):
            from app.application.attention import AttentionResult, AttentionSummary
            return AttentionResult(AttentionSummary(105, 0, 105), items)

    router = create_router(Runtime(), TelegramSettings("token", 1, "db", trades[0].account_id))
    callback = _Callback.make("attention")
    asyncio.run(_handler(router, "handle_attention")(callback))

    text, markup = callback.message.edited
    trade_buttons = [button for button in _buttons(markup) if button.callback_data.startswith("trade:")]
    assert len(trade_buttons) == 5
    attention_action_buttons = [
        button for button in _buttons(markup)
        if button.callback_data and button.callback_data.startswith(("trade:", "enrich:"))
    ]
    assert any(button.text.startswith("📄 Открыть") for button in attention_action_buttons)
    assert any(button.text.startswith("✍️ Заполнить") for button in attention_action_buttons)
    assert all(str(trade.trade_id) in button.callback_data for trade, button in zip(trades[:5], trade_buttons))
    assert all(len(button.callback_data.encode("utf-8")) <= 64 for button in trade_buttons)
    assert "Показано 1–5 из 105" in text
    assert "Страница 1 из 21" in text
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert "attention:noop" not in callbacks
    assert "attention:page:all:5" in callbacks
    assert "attention:page:all:0" not in callbacks
    assert len(text) < 4096
    assert "106." not in text

    next_callback = _Callback.make("attention:page:all:5")
    asyncio.run(_handler(router, "handle_attention_page")(next_callback))
    next_text, next_markup = next_callback.message.edited
    assert "Показано 6–10 из 105" in next_text
    assert "Страница 2 из 21" in next_text
    assert any(button.callback_data == f"trade:{trades[5].trade_id}" for button in _buttons(next_markup))
    assert next_callback.answers


def test_attention_category_pages_have_independent_navigation():
    trades = tuple(_trade(index, closed=True) for index in range(1, 105))
    items = tuple(
        __import__("app.application.attention", fromlist=["AttentionItem"]).AttentionItem(
            TradeView.from_trade(trade),
            TradeReadiness(TradeReadinessStatus.INCOMPLETE, ("NET_PNL",)),
            _instrument(trade, index),
        )
        for index, trade in enumerate(trades, 1)
    )

    class Runtime:
        async def attention(self, *, account_id=None, instrument_id=None):
            from app.application.attention import AttentionResult, AttentionSummary
            return AttentionResult(AttentionSummary(104, 0, 104), items)

    router = create_router(Runtime(), TelegramSettings("token", 1, "db", trades[0].account_id))
    callback = _Callback.make("attention:closed")
    asyncio.run(_handler(router, "handle_closed_attention")(callback))
    _, markup = callback.message.edited
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert "attention:page:closed:5" in callbacks
    assert "attention:page:all:5" not in callbacks


def test_excluded_restore_buttons_are_distinct_and_restore_refreshes_current_page():
    first = _trade(1)
    second = _trade(2)
    trades = [first, second]
    instruments = {first.instrument_id: _instrument(first, 1), second.instrument_id: _instrument(second, 2)}

    class Runtime:
        async def list_excluded_trades(self, *, account_id=None, limit=50, offset=0):
            return tuple(trades[offset:offset + limit])

        async def count_excluded_trades(self, *, account_id=None):
            return len(trades)

        async def get_instrument(self, instrument_id):
            return instruments[instrument_id]

        async def restore_trade(self, trade_id):
            trades[:] = [trade for trade in trades if trade.trade_id != trade_id]

    router = create_router(Runtime(), TelegramSettings("token", 1, "db", first.account_id))
    callback = _Callback.make("settings_excluded")
    asyncio.run(_handler(router, "handle_settings_excluded")(callback, _State()))
    text, markup = callback.message.edited
    restore_buttons = [button for button in _buttons(markup) if button.callback_data.startswith("restore:")]
    assert [button.text for button in restore_buttons] == ["↩️ 1 · COIN1USDT", "↩️ 2 · COIN2USDT"]
    assert restore_buttons[0].callback_data == f"restore:{first.trade_id}:0"
    assert restore_buttons[1].callback_data == f"restore:{second.trade_id}:0"
    assert len(restore_buttons[0].callback_data.encode("utf-8")) <= 64
    assert "Показано 1–2 из 2" in text
    assert "Страница 1 из 1" in text
    assert all(button.callback_data != "excluded:noop" for button in _buttons(markup))

    restore_callback = _Callback.make(restore_buttons[0].callback_data)
    asyncio.run(_handler(router, "handle_restore")(restore_callback, _State()))
    refreshed_text, refreshed_markup = restore_callback.message.edited
    assert "COIN1USDT" not in refreshed_text
    assert "1. COIN2USDT" in refreshed_text
    assert all(str(first.trade_id) not in (button.callback_data or "") for button in _buttons(refreshed_markup))
    assert restore_callback.answers


def test_excluded_page_navigation_is_bounded_and_exact():
    trades = tuple(_trade(index) for index in range(1, 13))
    labels = tuple(f"COIN{index}USDT" for index in range(1, 13))
    from app.telegram.keyboards import excluded_trades_keyboard
    markup = excluded_trades_keyboard(trades[:5], labels[:5], offset=0, limit=5, total=12, has_next=True)
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert "excluded:page:5" in callbacks
    assert "excluded:noop" not in callbacks
    assert "excluded:page:0" not in callbacks
    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks if callback)
    page_two = excluded_trades_keyboard(trades[5:10], labels[5:10], offset=5, limit=5, total=12, has_next=True)
    assert "excluded:page:0" in [button.callback_data for button in _buttons(page_two)]
    last_page = excluded_trades_keyboard(trades[10:12], labels[10:12], offset=10, limit=5, total=12, has_next=False)
    last_callbacks = [button.callback_data for button in _buttons(last_page)]
    assert "excluded:page:15" not in last_callbacks
    assert "excluded:page:5" in last_callbacks


def test_custom_date_exclusion_flow_reaches_preview_in_one_process():
    class DateMessage:
        def __init__(self, text):
            self.text = text
            self.answers = []

        async def answer(self, text, reply_markup=None):
            self.answers.append((text, reply_markup))

    class Runtime:
        def __init__(self):
            self.cutoff = None

        async def preview_bulk_exclude_old_incomplete(self, *, account_id, older_than):
            self.cutoff = older_than
            return SimpleNamespace(trade_ids=(), token="preview-token")

    runtime = Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", AccountId.generate()))
    state = _State()
    start = _Callback.make("bulk:custom")
    asyncio.run(_handler(router, "handle_bulk_custom_start")(start, state))
    assert state.state is not None

    message = DateMessage("05.09.2026")
    message_handler = next(item.callback for item in router.message.handlers if item.callback.__name__ == "handle_bulk_custom_date")
    asyncio.run(message_handler(message, state))

    assert runtime.cutoff == datetime(2026, 9, 5, tzinfo=timezone.utc)
    assert message.answers
    assert "До даты: 05.09.2026" in message.answers[0][0]


def test_recent_detail_back_callback_preserves_page_offset():
    trade = _trade(7)
    instrument = _instrument(trade, 7)
    markup = recent_trades_keyboard((trade,), (instrument,), offset=5)
    callback = _Callback.make(_buttons(markup)[0].callback_data)
    runtime = _Runtime(trade, instrument)
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))

    asyncio.run(_handler(router, "handle_recent_trade_selection")(callback))

    callbacks = [button.callback_data for button in _buttons(callback.message.edited[1])]
    assert "recent:page:5" in callbacks


def test_oversized_telegram_payload_falls_back_to_safe_text_without_markup(caplog):
    text, markup = _bounded_telegram_payload("x" * 4097, object(), "attention")
    assert text.startswith("❌ Не удалось отобразить список")
    assert markup is None
    assert "safe message limit" in caplog.text


def test_open_trade_detail_and_editor_keep_lifecycle_and_context_edit_routes():
    trade = _trade(8, closed=False)
    instrument = _instrument(trade, 8)
    fields = tuple(
        CustomFieldDefinition.create(code, name, CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, CustomFieldPhase.OPEN)
        for code, name in (("strategy", "Стратегия"), ("setup", "Сетап"), ("followed_plan", "По плану?"), ("error", "Ошибка"), ("comment", "Комментарий"))
    )
    runtime = _Runtime(trade, instrument, fields)
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))
    callback = _Callback.make(f"edit:{trade.trade_id}")
    state = _State()

    asyncio.run(_handler(router, "handle_edit")(callback, state))

    text = callback.message.edited[0]
    callbacks = [button.callback_data for button in _buttons(callback.message.edited[1])]
    assert "🟢 СДЕЛКА ОТКРЫТА" in text
    assert "Выход:" not in text
    assert "Дата/время выхода:" not in text
    assert "edit:strategy" in callbacks
    assert "edit:setup" in callbacks
    assert "edit:plan" in callbacks
    assert "edit:error" in callbacks
    assert "edit:comment" in callbacks
    assert callback.answers


def test_unified_journal_list_renders_open_and_closed_with_exact_trade_routes():
    opened = _trade(11, closed=False)
    closed = _trade(12, closed=True)
    instruments = {opened.instrument_id: _instrument(opened, 11), closed.instrument_id: _instrument(closed, 12)}

    class Runtime:
        async def list_all_trades(self, command):
            return ListAllTradesResult((TradeView.from_trade(opened), TradeView.from_trade(closed)))

        async def get_instrument(self, instrument_id):
            return instruments[instrument_id]

    router = create_router(Runtime(), TelegramSettings("token", 1, "db", opened.account_id))
    callback = _Callback.make("all_trades")
    asyncio.run(_handler(router, "handle_all_trades")(callback))

    text, markup = callback.message.edited
    callbacks = [button.callback_data for button in _buttons(markup)]
    assert text.startswith("📚 Сделки")
    assert "🟢 COIN11USDT · LONG" in text
    assert "ОТКРЫТА" in text
    assert "✅ COIN12USDT · SHORT" in text
    assert "ЗАКРЫТА" in text
    assert f"trade:{opened.trade_id}" in callbacks
    assert f"trade:{closed.trade_id}" in callbacks


def test_edit_field_choice_uses_fsm_trade_and_upserts_selected_option():
    trade = _trade(1)
    instrument = _instrument(trade, 1)
    field = CustomFieldDefinition.create(
        "strategy", "Стратегия", CustomFieldValueType.CHOICE,
        CustomFieldSource.MANUAL, CustomFieldPhase.POST_TRADE,
    )
    option = CustomFieldOption.create(field.id, "trend_continuation", "Продолжение тренда")
    runtime = _Runtime(trade, instrument, (field,), (option,))
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))
    state = _State()
    asyncio.run(state.update_data(selected_trade_id=str(trade.trade_id), enrichment_status="CLOSED"))

    field_callback = _Callback.make("edit:strategy")
    asyncio.run(_handler(router, "handle_edit_field")(field_callback, state))
    assert state.data["selected_trade_id"] == str(trade.trade_id)
    assert state.data["current_field_id"] == str(field.id)
    option_callback = _Callback.make(f"field_option:{option.id}")
    asyncio.run(_handler(router, "handle_field_option")(option_callback, state))

    assert len(runtime.saved_values) == 1
    assert runtime.saved_values[0].trade_id == trade.trade_id
    assert runtime.saved_values[0].field_id == field.id
    assert runtime.saved_values[0].value == option.id
    assert state.data == {}


def test_open_trade_editor_uses_canonical_instrument_context_for_default_field():
    trade = _trade(2, closed=False)
    instrument = _instrument(trade, 2)
    field = CustomFieldDefinition.create(
        "strategy", "Стратегия", CustomFieldValueType.CHOICE,
        CustomFieldSource.MANUAL, CustomFieldPhase.ANY,
    )
    option = CustomFieldOption.create(field.id, "trend_continuation", "Продолжение тренда")
    runtime = _Runtime(trade, instrument, (field,), (option,))
    # Deliberately leave settings.exchange/market empty: the trade instrument
    # is the canonical source for scoped-field resolution.
    router = create_router(runtime, TelegramSettings("token", 1, "db", trade.account_id))
    state = _State()

    asyncio.run(_handler(router, "handle_edit")( _Callback.make(f"edit:{trade.trade_id}"), state))
    field_callback = _Callback.make("edit:strategy")
    asyncio.run(_handler(router, "handle_edit_field")(field_callback, state))
    asyncio.run(_handler(router, "handle_field_option")(_Callback.make(f"field_option:{option.id}"), state))

    command = runtime.saved_values[0]
    assert command.resolution_context.phase is CustomFieldPhase.OPEN
    assert command.resolution_context.exchange == "BYBIT"
    assert command.resolution_context.market == "LINEAR"
