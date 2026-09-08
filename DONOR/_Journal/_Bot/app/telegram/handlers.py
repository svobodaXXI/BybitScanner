"""Production Telegram handlers; business operations go through JournalApplication."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from dataclasses import replace
import logging
import time
import asyncio

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, TelegramObject, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest
from zoneinfo import ZoneInfo

from app.application import SearchInstrumentsCommand, HistoricalImportSelection
from app.core.imports import HistoricalImportMode, HistoryProgress, JournalTradeState
from app.application.statistics import StatisticsFilter
from app.application.dtos import (
    AddExpenseCommand,
    AddFeeCommand,
    AddManualCustomValueCommand,
    CloseManualTradeCommand,
    CreateManualTradeCommand,
    EnrichTradeCommand,
    GetTradeDetailsCommand,
    ListAllTradesCommand,
    ListOpenTradesCommand,
    UpdateTradeProtectionCommand,
)
from app.application.errors import ApplicationError
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.accounts.account_id import AccountId
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.statistics.custom_field_option import CustomFieldOption
from app.core.statistics.ids import CustomFieldDefinitionId, CustomFieldOptionId
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.trade_id import TradeId
from app.core.trades.readiness import TradeReadinessStatus
from app.core.monitoring import REMINDER_TIMEZONES, timezone_display_name, validate_timezone_name

from .composition import JournalApplication
from .config import TelegramSettings
from .errors import user_error
from .formatting import compact_journal_trade_text, compact_open_trade_text, compact_recent_trade_text, compact_statistics_text, custom_value_text, details_text, trade_text
from .keyboards import (
    cancel_keyboard,
    account_selection_keyboard,
    after_create_keyboard,
    attention_keyboard,
    field_definition_keyboard,
    field_management_keyboard,
    field_type_keyboard,
    choice_keyboard,
    development_keyboard,
    direction_keyboard,
    instrument_selection_keyboard,
    main_menu_keyboard,
    recent_trades_keyboard,
    trade_detail_keyboard,
    trade_edit_keyboard,
    settings_keyboard,
    trade_list_keyboard,
    yes_no_keyboard,
    readiness_action_keyboard,
    stats_period_keyboard,
    bybit_history_modes_keyboard,
    bybit_import_preview_keyboard,
    bybit_new_only_keyboard,
    bybit_preview_error_keyboard,
    bybit_history_missing_keyboard,
    excluded_trade_keyboard,
    bulk_exclusion_ranges_keyboard,
    bulk_exclusion_preview_keyboard,
    excluded_trades_keyboard,
    reminders_keyboard,
    reminder_timezone_keyboard,
)
from .state import JournalStates

logger = logging.getLogger(__name__)

TELEGRAM_SAFE_MESSAGE_LIMIT = 3800
ATTENTION_PAGE_SIZE = 5
EXCLUDED_PAGE_SIZE = 5


def _parse_history_date(value: str | None, *, end: bool = False) -> datetime:
    raw = (value or "").strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00")) if "-" in raw else datetime.strptime(raw, "%d.%m.%Y").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise ValueError("invalid history date") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    if end and len(raw) <= 10:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _history_preview_text(mode: HistoricalImportMode, preview) -> str:
    labels = {
        HistoricalImportMode.NEW_ONLY: "🟢 Только новые сделки",
        HistoricalImportMode.LAST_30_DAYS: "📅 Последние 30 дней",
        HistoricalImportMode.ALL_AVAILABLE: "📚 Вся доступная история",
        HistoricalImportMode.CUSTOM: "🗓 Выбранный период",
    }
    period = f"{preview.selected_start:%d.%m.%Y} — {preview.selected_end:%d.%m.%Y}"
    return (
        f"{labels[mode]}\n\nПериод:\n{period}\n\n"
        f"Найдено:\n• Исполнений: {preview.execution_count}\n"
        f"• Сделок: {preview.logical_trade_count}\n• Инструментов: {preview.symbol_count}\n"
        f"• Уже в журнале: {preview.already_imported_trade_count}\n"
        f"• Будет добавлено: {preview.would_import_trade_count}\n"
        f"• Переходящих через границу: {preview.boundary_crossing_trade_count}"
    )


def _field_status_label(status) -> str:
    return "Активно" if getattr(status, "value", status) == "ACTIVE" else "Неактивно"


def _new_only_setup_text(start: datetime) -> str:
    return (
        "🟢 Только новые сделки\n\n"
        "Начать вести журнал с:\n"
        f"{start:%d.%m.%Y}\n\n"
        "Старые сделки импортированы не будут.\n"
        "Новые сделки будут добавляться автоматически."
    )


async def _edit_message_safely(message, text: str, markup=None) -> None:
    """Telegram's identical-edit response is a harmless idempotent no-op."""
    text, markup = _bounded_telegram_payload(text, markup, "edit")
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise


def _bounded_telegram_payload(text: str, markup, context: str):
    """Keep every Telegram send/edit below the platform limit."""
    if len(text) <= TELEGRAM_SAFE_MESSAGE_LIMIT:
        return text, markup
    logger.error("Telegram render exceeded safe message limit context=%s chars=%s", context, len(text))
    return "❌ Не удалось отобразить список. Используйте постраничную навигацию.", None


def unique_exact_active_instrument(instruments, query: str):
    """Return the only exact active symbol, leaving fuzzy results for a picker."""
    normalized = query.strip().upper() if isinstance(query, str) else ""
    matches = tuple(
        item for item in instruments
        if getattr(item, "active", False) and getattr(item, "symbol", "") == normalized
    )
    return matches[0] if len(matches) == 1 else None


class AuthorizationMiddleware(BaseMiddleware):
    """Allow only the configured Telegram owner."""

    def __init__(self, allowed_user_id: int | None) -> None:
        self.allowed_user_id = allowed_user_id

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        user_id = user.id if user is not None else None
        if self.allowed_user_id is None or user_id != self.allowed_user_id:
            logger.warning("Unauthorized Telegram access attempt: user_id=%s", user_id)
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ запрещён.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Доступ запрещён.")
            return None
        return await handler(event, data)


def create_router(runtime: JournalApplication, settings: TelegramSettings) -> Router:
    router = Router(name="production_journal")

    async def send(event, text: str, markup=None, *, edit: bool = False):
        text, markup = _bounded_telegram_payload(text, markup, "send")
        if isinstance(event, CallbackQuery):
            if event.message is not None:
                if edit:
                    await _edit_message_safely(event.message, text, markup)
                    return event.message
                else:
                    return await event.message.answer(text, reply_markup=markup)
        else:
            return await event.answer(text, reply_markup=markup)

    async def journal_timezone_name() -> str:
        """Resolve persisted journal timezone before falling back to env config."""
        getter = getattr(runtime, "get_reminder_settings", None)
        if getter is not None and settings.journal_account_id is not None:
            try:
                persisted = await getter(settings.journal_account_id)
            except (TypeError, ValueError, ApplicationError):
                persisted = None
            if persisted is not None and persisted.timezone_name:
                return persisted.timezone_name
        return settings.reminder_settings.timezone_name

    async def show_menu(event, state: FSMContext) -> None:
        await state.clear()
        await send(event, "Торговый журнал\n\nВыберите действие.", main_menu_keyboard(dev_mode=settings.dev_mode, webapp_url=settings.webapp_url), edit=isinstance(event, CallbackQuery))

    async def expected_error(event, error: Exception, *, edit: bool = False) -> bool:
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except TelegramBadRequest:
                pass
        text = user_error(error)
        if text is None:
            return False
        await send(event, text, cancel_keyboard(), edit=edit)
        return True

    def resolution_context(
        status: TradeStatus,
        details=None,
        state_data: dict | None = None,
    ) -> CustomFieldResolutionContext:
        """Resolve fields against the selected trade, not its navigation path."""
        state_data = state_data or {}
        instrument = getattr(details, "instrument", None)

        def value_code(code: str) -> str | None:
            for item in getattr(details, "custom_values", ()):
                definition = getattr(item, "definition", None)
                if definition is None or str(definition.code) != code:
                    continue
                option = getattr(item, "option", None)
                if option is not None:
                    return str(option.code)
                value = getattr(getattr(item, "value", None), "value", None)
                return None if value is None else str(value)
            return None

        exchange = getattr(instrument, "exchange", None) or state_data.get("resolution_exchange") or settings.exchange
        market = getattr(instrument, "market", None) or state_data.get("resolution_market") or settings.market
        strategy = value_code("strategy") or state_data.get("resolution_strategy_code") or settings.strategy_code
        setup = value_code("setup") or state_data.get("resolution_setup_code") or settings.setup_code
        return CustomFieldResolutionContext(
            phase=CustomFieldPhase.OPEN if status is TradeStatus.OPEN else CustomFieldPhase.POST_TRADE,
            exchange=exchange,
            market=market,
            strategy_code=strategy,
            setup_code=setup,
        )

    def context_state(details) -> dict[str, str | None]:
        context = resolution_context(details.trade.status, details)
        return {
            "resolution_exchange": context.exchange,
            "resolution_market": context.market,
            "resolution_strategy_code": None if context.strategy_code is None else str(context.strategy_code),
            "resolution_setup_code": None if context.setup_code is None else str(context.setup_code),
        }

    def is_trade_edit_callback(callback: CallbackQuery) -> bool:
        if not callback.data or not callback.data.startswith("edit:"):
            return False
        try:
            TradeId(callback.data.split(":", 1)[1])
        except (TypeError, ValueError):
            return False
        return True

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        await show_menu(message, state)

    @router.callback_query(F.data == "menu")
    async def handle_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await show_menu(callback, state)

    @router.callback_query(F.data == "settings")
    async def handle_settings(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        await send(callback, "⚙ Настройки", settings_keyboard(), edit=True)

    @router.callback_query(F.data == "settings_fields")
    async def handle_settings_fields(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        fields = await runtime.list_custom_fields()
        rows = [
            f"• {field.name} — {_field_status_label(field.status)} · "
            f"{'обязательно' if field.required_for_statistics else 'необязательно'}"
            for field in fields
        ]
        await send(callback, "📋 Поля статистики\n\n" + ("\n".join(rows) or "Полей пока нет."), field_management_keyboard(fields), edit=True)

    @router.callback_query(F.data == "field_add")
    async def handle_field_add(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        await state.set_state(JournalStates.field_create_name)
        await send(callback, "Введите название нового ручного поля.", cancel_keyboard(), edit=True)

    @router.message(JournalStates.field_create_name)
    async def handle_field_create_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("Название не должно быть пустым. Повторите ввод.")
            return
        await state.update_data(field_name=name)
        await state.set_state(JournalStates.field_create_type)
        await message.answer("Выберите тип поля.", reply_markup=field_type_keyboard())

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_type:")))
    async def handle_field_create_type(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            value_type = CustomFieldValueType(callback.data.split(":", 1)[1])
        except (TypeError, ValueError):
            await callback.answer("Некорректный тип.", show_alert=True)
            return
        data = await state.get_data()
        try:
            definition = await runtime.create_custom_field(
                code=f"custom_{CustomFieldDefinitionId.generate().value.hex}",
                name=data["field_name"],
                value_type=value_type,
            )
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(callback, error, edit=True):
                await callback.answer("Поле не создано.", show_alert=True)
            return
        await state.clear()
        await callback.answer()
        await send(callback, f"Поле создано: {definition.name}", field_definition_keyboard(definition), edit=True)

    async def render_field_manage(callback: CallbackQuery, *, answer: bool = True, field_id=None) -> None:
        try:
            field_id = field_id or CustomFieldDefinitionId(callback.data.split(":", 1)[1])
            definition = await runtime.get_custom_field(field_id)
            options = await runtime.list_custom_field_options(field_id, include_inactive=True)
        except (TypeError, ValueError, ApplicationError):
            definition = None
            options = ()
        if definition is None:
            if answer:
                await callback.answer("Поле не найдено.", show_alert=True)
            return
        if answer:
            await callback.answer()
        await send(callback, f"{definition.name}\n\nТип: {definition.value_type.value}\nСтатус: {_field_status_label(definition.status)}\nОбязательно для статистики: {'Да' if definition.required_for_statistics else 'Нет'}", field_definition_keyboard(definition, options), edit=True)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_manage:")))
    async def handle_field_manage(callback: CallbackQuery, state: FSMContext) -> None:
        await render_field_manage(callback)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_toggle:")))
    async def handle_field_toggle(callback: CallbackQuery) -> None:
        field_id = CustomFieldDefinitionId(callback.data.split(":", 1)[1])
        definition = await runtime.get_custom_field(field_id)
        if definition is None:
            await callback.answer("Поле не найдено.", show_alert=True)
            return
        await runtime.set_custom_field_active(field_id, not definition.is_active)
        await callback.answer()
        await render_field_manage(callback, answer=False)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_required:")))
    async def handle_field_required(callback: CallbackQuery) -> None:
        field_id = CustomFieldDefinitionId(callback.data.split(":", 1)[1])
        definition = await runtime.get_custom_field(field_id)
        if definition is None:
            await callback.answer("Поле не найдено.", show_alert=True)
            return
        await runtime.set_custom_field_required_for_statistics(field_id, not definition.required_for_statistics)
        await callback.answer()
        await render_field_manage(callback, answer=False)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("option_toggle:")))
    async def handle_option_toggle(callback: CallbackQuery) -> None:
        option_id = CustomFieldOptionId(callback.data.split(":", 1)[1])
        option = None
        field_id = None
        for definition in await runtime.list_custom_fields():
            options = await runtime.list_custom_field_options(definition.id, include_inactive=True)
            option = next((item for item in options if item.id == option_id), None)
            if option is not None:
                field_id = definition.id
                break
        if option is None:
            await callback.answer("Вариант не найден.", show_alert=True)
            return
        await runtime.save_custom_field_option(option.activate() if not option.active else option.deactivate())
        await callback.answer()
        await render_field_manage(callback, answer=False, field_id=field_id)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("option_add:")))
    async def handle_option_add(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        await state.update_data(option_field_id=callback.data.split(":", 1)[1])
        await state.set_state(JournalStates.field_option_name)
        await send(callback, "Введите отображаемое название варианта.", cancel_keyboard(), edit=True)

    @router.message(JournalStates.field_option_name)
    async def handle_option_name(message: Message, state: FSMContext) -> None:
        label = (message.text or "").strip()
        data = await state.get_data()
        if not label:
            await message.answer("Название варианта не должно быть пустым.")
            return
        field_id = CustomFieldDefinitionId(data["option_field_id"])
        options = await runtime.list_custom_field_options(field_id, include_inactive=True)
        option = CustomFieldOption.create(
            field_id,
            f"option_{CustomFieldDefinitionId.generate().value.hex}",
            label,
            sort_order=len(options),
        )
        try:
            await runtime.save_custom_field_option(option)
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("Вариант не добавлен.")
            return
        definition = await runtime.get_custom_field(field_id)
        await state.clear()
        await send(message, f"Вариант добавлен: {label}", field_definition_keyboard(definition, (*options, option)))

    @router.callback_query(F.data == "settings_reminders")
    async def handle_settings_reminders(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if settings.journal_account_id is None:
            await send(callback, "Напоминания недоступны: не настроен счёт.", settings_keyboard(), edit=True)
            return
        try:
            reminder = await runtime.get_reminder_settings(settings.journal_account_id)
            reminder = reminder or replace(settings.reminder_settings, account_id=settings.journal_account_id)
            timezone_label = timezone_display_name(reminder.timezone_name)
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        status = "Включены" if reminder.daily_attention_digest_enabled else "Выключены"
        await send(
            callback,
            f"🔔 Напоминания\n\nНапоминания: {status}\nВремя: {reminder.daily_attention_digest_time:%H:%M}\nЧасовой пояс: {timezone_label}\n\nДайджест отправляется не чаще одного раза в день\nдля закрытых сделок, не готовых к статистике.",
            reminders_keyboard(enabled=reminder.daily_attention_digest_enabled),
            edit=True,
        )

    async def current_reminder_settings():
        reminder = await runtime.get_reminder_settings(settings.journal_account_id)
        return reminder or replace(settings.reminder_settings, account_id=settings.journal_account_id)

    @router.callback_query(F.data == "reminder:toggle")
    async def handle_reminder_toggle(callback: CallbackQuery, state: FSMContext) -> None:
        if settings.journal_account_id is None:
            await callback.answer("Не настроен счёт.", show_alert=True)
            return
        try:
            reminder = await current_reminder_settings()
            updated = replace(
                reminder,
                account_id=settings.journal_account_id,
                daily_attention_digest_enabled=not reminder.daily_attention_digest_enabled,
            )
            await runtime.save_reminder_settings(updated)
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await handle_settings_reminders(callback, state)

    @router.callback_query(F.data == "reminder:time")
    async def handle_reminder_time_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(JournalStates.reminder_time)
        await send(callback, "Введите время ежедневного напоминания в формате ЧЧ:ММ.", cancel_keyboard(), edit=True)

    @router.message(JournalStates.reminder_time)
    async def handle_reminder_time(message: Message, state: FSMContext) -> None:
        try:
            reminder_time = datetime.strptime((message.text or "").strip(), "%H:%M").time()
            if settings.journal_account_id is None:
                raise ValueError("journal account is not configured")
            reminder = await current_reminder_settings()
            await runtime.save_reminder_settings(replace(
                reminder,
                account_id=settings.journal_account_id,
                daily_attention_digest_time=reminder_time,
            ))
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Некорректное время. Используйте формат ЧЧ:ММ.")
            return
        await state.clear()
        await message.answer(
            f"✅ Время напоминания изменено: {reminder_time:%H:%M}",
            reply_markup=reminders_keyboard(enabled=reminder.daily_attention_digest_enabled),
        )

    @router.callback_query(F.data == "reminder:timezone")
    async def handle_reminder_timezone_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await send(
            callback,
            "🌍 Выберите часовой пояс",
            reminder_timezone_keyboard(REMINDER_TIMEZONES),
            edit=True,
        )

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("reminder:timezone:")))
    async def handle_reminder_timezone(callback: CallbackQuery, state: FSMContext) -> None:
        if settings.journal_account_id is None:
            await callback.answer("Не настроен счёт.", show_alert=True)
            return
        selected = callback.data.rsplit(":", 1)[-1]
        allowed = dict(REMINDER_TIMEZONES)
        if selected not in allowed.values():
            await callback.answer("Некорректный часовой пояс.", show_alert=True)
            return
        try:
            validate_timezone_name(selected)
            reminder = await current_reminder_settings()
            await runtime.save_reminder_settings(replace(
                reminder,
                account_id=settings.journal_account_id,
                timezone_name=selected,
            ))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await handle_settings_reminders(callback, state)

    @router.callback_query(F.data == "settings_account")
    async def handle_settings_account(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        label = "настроен" if settings.journal_account_id else "не настроен"
        await send(callback, f"Счёт по умолчанию: {label}", settings_keyboard(), edit=True)

    async def discover_and_show_history(event, state: FSMContext, *, force_refresh: bool = False) -> None:
        if settings.journal_account_id is None:
            await send(event, "📥 История Bybit\n\nНе настроен счёт журнала.", settings_keyboard(), edit=isinstance(event, CallbackQuery))
            return
        try:
            import_settings = await runtime.get_exchange_import_settings(settings.journal_account_id, "BYBIT")
            needs_discovery = force_refresh or import_settings is None or import_settings.history_available_from is None
            if needs_discovery:
                last_progress = 0.0
                progress_lock = asyncio.Lock()
                await send(event, "📥 Анализ истории Bybit\n\n⏳ Получаю данные с биржи...", bybit_history_modes_keyboard(), edit=isinstance(event, CallbackQuery))

                async def on_progress(progress: HistoryProgress) -> None:
                    nonlocal last_progress
                    now = time.monotonic()
                    if progress.windows_completed < progress.windows_total and now - last_progress < 2.0:
                        return
                    async with progress_lock:
                        now = time.monotonic()
                        if progress.windows_completed < progress.windows_total and now - last_progress < 2.0:
                            return
                        last_progress = now
                        total = progress.windows_total
                        percent = 100 if not total else int(progress.windows_completed * 100 / total)
                        await send(
                            event,
                            "📥 Анализ истории Bybit\n\n"
                            f"⏳ Получаю данные с биржи...\n\n"
                            f"Проверено периодов: {progress.windows_completed} / {total}\n"
                            f"Найдено исполнений: {progress.executions_found}\n"
                            f"Прогресс: {percent}%",
                            bybit_history_modes_keyboard(), edit=isinstance(event, CallbackQuery),
                        )

                discovery = await runtime.discover_bybit_history(
                    lookback_start=getattr(
                        runtime,
                        "bybit_history_lookback_start",
                        datetime(2025, 1, 1, tzinfo=timezone.utc),
                    ),
                    force_refresh=force_refresh,
                    progress_callback=on_progress,
                )
                available = discovery.history_available_from
            else:
                available = import_settings.history_available_from
        except (TypeError, ValueError, ApplicationError, RuntimeError) as error:
            if not await expected_error(event, error, edit=isinstance(event, CallbackQuery)):
                await send(event, "❌ Не удалось определить доступную историю Bybit.", settings_keyboard(), edit=isinstance(event, CallbackQuery))
            return
        if available is None:
            await send(event, "📥 История Bybit\n\nПоддерживаемой истории не найдено.", settings_keyboard(), edit=isinstance(event, CallbackQuery))
            return
        await state.clear()
        await state.update_data(history_available_from=available.isoformat())
        timezone_name = await journal_timezone_name()
        try:
            local = available.astimezone(ZoneInfo(timezone_name))
        except Exception:
            local = available
        await send(event, f"📥 История Bybit\n\nДоступная история для дневника:\nс {local:%d.%m.%Y}\n\nС какого момента начать вести журнал?", bybit_history_modes_keyboard(), edit=isinstance(event, CallbackQuery))

    @router.callback_query(F.data == "settings_bybit_history")
    async def handle_settings_bybit_history(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await discover_and_show_history(callback, state)

    @router.callback_query(F.data == "bybit:refresh")
    async def handle_bybit_refresh(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await discover_and_show_history(callback, state, force_refresh=True)

    async def show_import_preview(event, state: FSMContext, mode: HistoricalImportMode, *, start=None, end=None) -> None:
        data = await state.get_data()
        if data.get("preview_in_progress"):
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer("Предпросмотр уже выполняется")
                except TelegramBadRequest:
                    pass
            return
        supported = None
        if settings.journal_account_id is not None:
            persisted = await runtime.get_exchange_import_settings(settings.journal_account_id, "BYBIT")
            if persisted is not None:
                supported = persisted.history_available_from
        if supported is None:
            await send(
                event,
                "⚠ История Bybit ещё не подготовлена.\n\n"
                "Сначала выполните проверку доступной истории.",
                bybit_history_missing_keyboard(), edit=isinstance(event, CallbackQuery),
            )
            return
        await state.update_data(history_available_from=supported.isoformat())
        selection = HistoricalImportSelection(mode, supported, selected_start=start, selected_end=end)
        if mode is HistoricalImportMode.NEW_ONLY:
            await state.update_data(
                history_new_only_start=selection.selected_start.isoformat(),
                history_plan=None,
            )
            await send(event, _new_only_setup_text(selection.selected_start), bybit_new_only_keyboard(), edit=isinstance(event, CallbackQuery))
            return
        await state.update_data(preview_in_progress=True, operation_id=f"preview-{time.monotonic_ns()}")
        operation_message = None

        async def render_operation(text: str, markup=None) -> None:
            nonlocal operation_message
            if operation_message is None:
                operation_message = await send(event, text, markup, edit=isinstance(event, CallbackQuery))
                return
            await _edit_message_safely(operation_message, text, markup)

        try:
            await render_operation("📊 Формирую предварительный импорт\n\n⏳ Получаю исполнения...")
            last_progress = 0.0
            progress_lock = asyncio.Lock()

            async def on_progress(progress: HistoryProgress) -> None:
                nonlocal last_progress
                now = time.monotonic()
                if progress.stage == "fetch" and now - last_progress < 2.0 and progress.windows_completed < progress.windows_total:
                    return
                async with progress_lock:
                    now = time.monotonic()
                    if progress.stage == "fetch" and now - last_progress < 2.0 and progress.windows_completed < progress.windows_total:
                        return
                    last_progress = now
                    if progress.stage == "fetch":
                        stage = f"⏳ Получаю исполнения...\nПроверено периодов: {progress.windows_completed} / {progress.windows_total}"
                    elif progress.stage == "aggregate":
                        stage = "✅ Получение данных\n⏳ Собираю логические сделки..."
                    else:
                        stage = "✅ Получение данных\n✅ Сборка сделок\n⏳ Проверяю уже импортированные..."
                await render_operation(f"📊 Формирую предварительный импорт\n\n{stage}")

            preview, plan = await runtime.preview_bybit_import(selection, progress_callback=on_progress)
        except (TypeError, ValueError, ApplicationError, RuntimeError) as error:
            safe_text = user_error(error) or "❌ Не удалось сформировать предпросмотр.\n\nКод: HISTORICAL_PREVIEW"
            await render_operation(safe_text, bybit_preview_error_keyboard())
            await state.update_data(preview_in_progress=False, operation_id=None)
            return
        finally:
            await state.update_data(preview_in_progress=False, operation_id=None)
        await state.update_data(history_plan=plan)
        await render_operation(f"📊 Предпросмотр импорта\n\n{_history_preview_text(mode, preview)}", bybit_import_preview_keyboard())

    @router.callback_query(F.data.startswith("bybit:mode:"))
    async def handle_bybit_mode(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            mode = HistoricalImportMode(callback.data.rsplit(":", 1)[1])
        except ValueError:
            await callback.answer("Некорректный режим.", show_alert=True)
            return
        if (await state.get_data()).get("preview_in_progress"):
            await callback.answer("Предпросмотр уже выполняется")
            return
        await callback.answer()
        await show_import_preview(callback, state, mode)

    @router.callback_query(F.data == "bybit:new-only:confirm")
    async def handle_bybit_new_only_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        data = await state.get_data()
        value = data.get("history_new_only_start")
        if not value:
            await send(callback, "❌ Настройка устарела. Начните выбор истории заново.", bybit_history_modes_keyboard(), edit=True)
            return
        try:
            updated = await runtime.start_bybit_tracking(datetime.fromisoformat(value))
        except (TypeError, ValueError, PermissionError, ApplicationError) as error:
            if not await expected_error(callback, error, edit=True):
                await send(callback, "❌ Не удалось начать ведение журнала.", bybit_history_modes_keyboard(), edit=True)
            return
        await state.clear()
        await send(
            callback,
            f"✅ Журнал начат с {updated.tracking_start_at:%d.%m.%Y}\n\n"
            "Старые сделки не импортированы. Новые сделки будут добавляться автоматически.",
            main_menu_keyboard(), edit=True,
        )

    @router.callback_query(F.data == "bybit:period")
    async def handle_bybit_period(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await send(callback, "Выберите период заново.", bybit_history_modes_keyboard(), edit=True)

    @router.callback_query(F.data == "bybit:custom")
    async def handle_bybit_custom(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(JournalStates.history_custom_start)
        await send(callback, "Введите дату начала в формате ДД.ММ.ГГГГ или ISO-8601 UTC.", cancel_keyboard(), edit=True)

    @router.message(JournalStates.history_custom_start)
    async def handle_bybit_custom_start(message: Message, state: FSMContext) -> None:
        try:
            value = _parse_history_date(message.text)
        except ValueError:
            await message.answer("❌ Некорректная дата. Повторите ввод.")
            return
        await state.update_data(history_custom_start=value.isoformat())
        await state.set_state(JournalStates.history_custom_end)
        await message.answer("Введите дату окончания или «сейчас».", reply_markup=cancel_keyboard())

    @router.message(JournalStates.history_custom_end)
    async def handle_bybit_custom_end(message: Message, state: FSMContext) -> None:
        try:
            value = datetime.now(timezone.utc) if (message.text or "").strip().lower() in {"сейчас", "now"} else _parse_history_date(message.text, end=True)
            data = await state.get_data()
            await show_import_preview(message, state, HistoricalImportMode.CUSTOM, start=datetime.fromisoformat(data["history_custom_start"]), end=value)
        except ValueError:
            await message.answer("❌ Некорректная дата или период. Повторите ввод.")

    @router.callback_query(F.data == "bybit:confirm")
    async def handle_bybit_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        plan = data.get("history_plan")
        if plan is None:
            await callback.answer("Предпросмотр устарел. Начните заново.", show_alert=True)
            return
        await callback.answer()
        try:
            result = await runtime.import_bybit_plan(plan, confirm_token=plan.token)
        except (TypeError, ValueError, PermissionError, ApplicationError) as error:
            if not await expected_error(callback, error, edit=True):
                await send(callback, "❌ Импорт не выполнен. Данные не удалены.", bybit_history_modes_keyboard(), edit=True)
            return
        await state.clear()
        await send(
            callback,
            f"✅ Импорт завершён\n\n"
            f"Плановых сделок: {result.planned_journal_trades}\n"
            f"Создано сделок: {result.created or result.added_trade_count}\n"
            f"Обновлено: {result.updated}\n"
            f"Уже были в журнале: {result.already_existing or result.already_imported_trade_count}\n"
            f"Исполнений обработано: {result.processed_execution_count}\n"
            f"Ошибок: {len(result.errors)}",
            main_menu_keyboard(),
            edit=True,
        )

    @router.callback_query(F.data == "settings_tracking_start")
    async def handle_settings_tracking_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        current = await runtime.get_exchange_import_settings(settings.journal_account_id, "BYBIT")
        if current is None or current.history_available_from is None:
            await discover_and_show_history(callback, state)
            return
        start = "не задано" if current.tracking_start_at is None else current.tracking_start_at.astimezone(timezone.utc).strftime("%d.%m.%Y")
        await send(callback, f"📅 Начало журнала\n\nДоступная история Bybit: с {current.history_available_from:%d.%m.%Y}\nТекущее начало журнала: {start}\n\nИзменение начала журнала требует предпросмотра и подтверждения через импорт.", bybit_history_modes_keyboard(), edit=True)

    async def show_excluded(event, offset: int = 0) -> None:
        offset = max(0, offset)
        trades = await runtime.list_excluded_trades(
            account_id=settings.journal_account_id,
            limit=EXCLUDED_PAGE_SIZE + 1,
            offset=offset,
        )
        page = trades[:EXCLUDED_PAGE_SIZE]
        if not page and offset > 0:
            await show_excluded(event, max(0, offset - EXCLUDED_PAGE_SIZE))
            return
        labels = []
        lines = ["🗑 Исключённые сделки", ""]
        for index, trade in enumerate(page, offset + 1):
            instrument = await runtime.get_instrument(trade.instrument_id)
            symbol = instrument.symbol if instrument else "Сделка"
            labels.append(symbol)
            lines.append(f"{index}. {symbol} · {trade.closed_at:%d.%m.%Y}")
        count_excluded = getattr(runtime, "count_excluded_trades", None)
        total = await count_excluded(account_id=settings.journal_account_id) if count_excluded is not None else None
        has_next = offset + len(page) < total if total is not None else len(trades) > EXCLUDED_PAGE_SIZE
        if page:
            suffix = f" из {total}" if total is not None else ""
            page_text = ""
            if total is not None:
                page_text = f"Страница {offset // EXCLUDED_PAGE_SIZE + 1} из {max(1, (total + EXCLUDED_PAGE_SIZE - 1) // EXCLUDED_PAGE_SIZE)}\n"
            lines.extend(["", page_text + f"Показано {offset + 1}–{offset + len(page)}{suffix}"])
        await send(
            event,
            "\n".join(lines) if page else "🗑 Исключённых сделок нет.",
            excluded_trades_keyboard(
                page, labels, offset=offset, limit=EXCLUDED_PAGE_SIZE,
                total=total, has_next=has_next,
            ),
            edit=isinstance(event, CallbackQuery),
        )

    @router.callback_query(F.data == "settings_excluded")
    async def handle_settings_excluded(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await show_excluded(callback)

    @router.callback_query(F.data.startswith("excluded:page:"))
    async def handle_excluded_page(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_excluded(callback, int(callback.data.rsplit(":", 1)[1]))

    @router.callback_query(F.data == "excluded:noop")
    async def handle_excluded_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("exclude:") and callback.data != "exclude:confirm"))
    async def handle_exclude_start(callback: CallbackQuery, state: FSMContext) -> None:
        trade_id = callback.data.split(":", 1)[1]
        await state.update_data(exclude_trade_id=trade_id)
        await callback.answer()
        await send(callback, "Исключить сделку из журнала?\n\nБиржевые факты сохранятся; сделка исчезнет из статистики и Attention.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Исключить", callback_data="exclude:confirm")], [InlineKeyboardButton(text="Отмена", callback_data="menu")]]), edit=True)

    @router.callback_query(F.data == "exclude:confirm")
    async def handle_exclude_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            await runtime.exclude_trade(TradeId(data["exclude_trade_id"]))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await state.clear()
        await callback.answer()
        await send(callback, "✅ Сделка исключена из журнала. Биржевые исполнения сохранены.", settings_keyboard(), edit=True)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("restore:")))
    async def handle_restore(callback: CallbackQuery, state: FSMContext) -> None:
        parts = callback.data.split(":")
        trade_id = parts[1]
        offset = int(parts[2]) if len(parts) > 2 else 0
        try:
            await runtime.restore_trade(TradeId(trade_id))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await callback.answer("Сделка восстановлена")
        await show_excluded(callback, offset)

    async def prompt_instrument(event, state: FSMContext) -> None:
        await state.set_state(JournalStates.instrument_query)
        await send(event, "Введите тикер, символ или название инструмента.", cancel_keyboard(), edit=isinstance(event, CallbackQuery))

    @router.callback_query(F.data == "new_trade")
    async def handle_new_trade(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        try:
            accounts = tuple(await runtime.list_active_accounts())
        except AttributeError:
            accounts = ()
        if not accounts and settings.journal_account_id is not None:
            accounts = (settings.journal_account_id,)
        if len(accounts) == 1:
            await state.update_data(account_id=str(accounts[0]))
            await prompt_instrument(callback, state)
        elif len(accounts) > 1:
            await state.set_state(JournalStates.account_selection)
            await send(callback, "Выберите счёт.", account_selection_keyboard(accounts), edit=True)
        else:
            await send(callback, "❌ Нет доступных счетов. Настройте счёт по умолчанию.", main_menu_keyboard(), edit=True)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("account:")))
    async def handle_account_selection(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            account_id = AccountId(callback.data.split(":", 1)[1])
        except (TypeError, ValueError):
            await callback.answer("Некорректный счёт.", show_alert=True)
            return
        await callback.answer()
        await state.update_data(account_id=str(account_id))
        await prompt_instrument(callback, state)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("new:")))
    async def handle_direction(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        direction = TradeDirection(callback.data.split(":", 1)[1])
        await state.update_data(direction=direction.value)
        await state.set_state(JournalStates.entry_price)
        await send(callback, "Введите цену входа.", cancel_keyboard())

    @router.message(JournalStates.instrument_query)
    async def handle_instrument_query(message: Message, state: FSMContext) -> None:
        query = (message.text or "").strip()
        try:
            instruments = await runtime.search_instruments(SearchInstrumentsCommand(query))
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Введите тикер или название инструмента.", reply_markup=cancel_keyboard())
            return
        if not instruments:
            await message.answer("🔎 Инструмент не найден в каталоге. Повторите поиск или отмените.", reply_markup=cancel_keyboard())
            return
        selected = unique_exact_active_instrument(instruments, query)
        if selected is not None:
            await state.update_data(selected_instrument_id=str(selected.instrument_id))
            await state.set_state(JournalStates.entry_price)
            await message.answer(f"Выбран: {selected.symbol}\n\nВыберите направление.", reply_markup=direction_keyboard())
            return
        await state.set_state(JournalStates.instrument_selection)
        await message.answer("Выберите найденный инструмент:", reply_markup=instrument_selection_keyboard(instruments))

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("instrument:")))
    async def handle_instrument_selection(callback: CallbackQuery, state: FSMContext) -> None:
        try:
            instrument_id = InstrumentId(callback.data.split(":", 1)[1])
            instrument = await runtime.get_instrument(instrument_id)
        except (TypeError, ValueError, ApplicationError):
            instrument = None
        if instrument is None or not instrument.active:
            await callback.answer("Инструмент больше недоступен. Повторите поиск.", show_alert=True)
            await state.set_state(JournalStates.instrument_query)
            return
        await callback.answer()
        await state.update_data(selected_instrument_id=str(instrument.instrument_id))
        await state.set_state(JournalStates.entry_price)
        await send(callback, f"Выбран: {instrument.symbol}\n\nВыберите направление.", direction_keyboard(), edit=True)

    @router.message(JournalStates.entry_price)
    async def handle_entry_price(message: Message, state: FSMContext) -> None:
        try:
            price = Price((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer("❌ Некорректная цена. Повторите ввод.")
            return
        await state.update_data(entry_price=str(price.value))
        await state.set_state(JournalStates.quantity)
        await message.answer("Введите количество.", reply_markup=cancel_keyboard())

    @router.message(JournalStates.quantity)
    async def handle_quantity(message: Message, state: FSMContext) -> None:
        try:
            quantity = Quantity((message.text or "").strip())
            if quantity.value <= 0:
                raise ValueError("quantity must be greater than zero")
        except (TypeError, ValueError):
            await message.answer("❌ Количество должно быть больше нуля. Повторите ввод.")
            return
        await state.update_data(quantity=str(quantity.value))
        await state.set_state(JournalStates.stop_price)
        await message.answer("Stop Loss?", reply_markup=cancel_keyboard(allow_skip=True, skip_callback="new_skip:stop"))

    async def proceed_to_take_profit(event, state: FSMContext) -> None:
        await state.set_state(JournalStates.take_profit)
        await send(event, "Take Profit?", cancel_keyboard(allow_skip=True, skip_callback="new_skip:take"), edit=isinstance(event, CallbackQuery))

    async def create_open_trade(event, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            result = await runtime.create_manual_trade(CreateManualTradeCommand(
                account_id=AccountId(data["account_id"]), instrument_id=InstrumentId(data["selected_instrument_id"]),
                direction=TradeDirection(data["direction"]), entry_price=Price(data["entry_price"]),
                quantity=Quantity(data["quantity"]), opened_at=datetime.now(timezone.utc), currency=settings.default_currency,
                stop_price=None if not data.get("stop_price") else Price(data["stop_price"]),
                take_profit=None if not data.get("take_profit") else Price(data["take_profit"]),
            ))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(event, error):
                await send(event, "❌ Сделку не удалось создать. Проверьте введённые данные.")
            return
        await state.clear()
        instrument = await runtime.get_instrument(result.trade.instrument_id)
        await send(event, trade_text(result.trade, instrument), after_create_keyboard(result.trade), edit=isinstance(event, CallbackQuery))

    @router.message(JournalStates.stop_price)
    async def handle_stop_price(message: Message, state: FSMContext) -> None:
        try:
            price = Price((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer("❌ Некорректная цена Stop Loss. Повторите или нажмите «Пропустить».", reply_markup=cancel_keyboard(allow_skip=True, skip_callback="new_skip:stop"))
            return
        await state.update_data(stop_price=str(price.value))
        await proceed_to_take_profit(message, state)

    @router.callback_query(F.data == "new_skip:stop")
    async def skip_stop(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await proceed_to_take_profit(callback, state)

    @router.message(JournalStates.take_profit)
    async def handle_take_profit(message: Message, state: FSMContext) -> None:
        try:
            price = Price((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer("❌ Некорректная цена Take Profit. Повторите или нажмите «Пропустить».", reply_markup=cancel_keyboard(allow_skip=True, skip_callback="new_skip:take"))
            return
        await state.update_data(take_profit=str(price.value))
        await create_open_trade(message, state)

    @router.callback_query(F.data == "new_skip:take")
    async def skip_take(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await create_open_trade(callback, state)

    async def instrument_label(instrument_id) -> str:
        instrument = await runtime.get_instrument(instrument_id)
        return instrument.label if instrument is not None else "Инструмент не найден в каталоге"

    async def list_open(event) -> None:
        result = await runtime.list_open_trades(ListOpenTradesCommand(account_id=settings.journal_account_id))
        timezone_name = await journal_timezone_name()
        rows = []
        for index, trade in enumerate(result.trades, 1):
            rows.append(compact_open_trade_text(
                trade,
                await runtime.get_instrument(trade.instrument_id),
                index=index,
                timezone_name=timezone_name,
            ))
        text = "📂 Открытые сделки\n\n" + ("\n\n".join(rows) or "Открытых сделок нет.")
        await send(event, text, trade_list_keyboard(result.trades), edit=isinstance(event, CallbackQuery))

    @router.callback_query(F.data == "open_trades")
    async def handle_open_trades(callback: CallbackQuery) -> None:
        await callback.answer()
        await list_open(callback)

    async def list_recent(event, offset: int = 0) -> None:
        page_size = 5
        result = await runtime.list_all_trades(ListAllTradesCommand(
            account_id=settings.journal_account_id,
            limit=page_size + 1,
            offset=offset,
        ))
        trades = result.trades[:page_size]
        attention = await runtime.attention(account_id=settings.journal_account_id)
        incomplete_ids = {str(item.trade_id) for item in attention.items if item.readiness.status is TradeReadinessStatus.INCOMPLETE}
        rows = []
        instruments = []
        for index, trade in enumerate(trades, 1):
            instrument = await runtime.get_instrument(trade.instrument_id)
            instruments.append(instrument)
            row = compact_recent_trade_text(trade, instrument, index=offset + index)
            if str(trade.trade_id) in incomplete_ids:
                row += "\n⚠ НЕ ГОТОВА"
            rows.append(row)
        await send(
            event,
            "🕘 Последние сделки\n\n" + ("\n\n".join(rows) or "Сделок пока нет."),
            recent_trades_keyboard(trades, instruments, offset=offset, limit=page_size, has_next=len(result.trades) > page_size),
            edit=isinstance(event, CallbackQuery),
        )

    @router.callback_query(F.data == "recent_trades")
    async def handle_recent_trades(callback: CallbackQuery) -> None:
        await callback.answer()
        await list_recent(callback)

    @router.callback_query(F.data.startswith("recent:page:"))
    async def handle_recent_page(callback: CallbackQuery) -> None:
        await callback.answer()
        await list_recent(callback, int(callback.data.rsplit(":", 1)[1]))

    async def show_attention(event, category: str = "all", offset: int = 0) -> None:
        result = await runtime.attention(account_id=settings.journal_account_id)
        if category not in {"all", "open", "closed"}:
            category = "all"
        items = tuple(
            item for item in result.items
            if category == "all"
            or (category == "open" and item.readiness.status is TradeReadinessStatus.OPEN)
            or (category == "closed" and item.readiness.status is not TradeReadinessStatus.OPEN)
        )
        page = items[offset:offset + ATTENTION_PAGE_SIZE]
        if not page and offset > 0:
            await show_attention(event, category, max(0, offset - ATTENTION_PAGE_SIZE))
            return
        lines = [
            "⚠ Требуют внимания",
            "",
            f"🟢 Открытые сделки: {result.summary.open_count}",
            f"⚠ Закрытые, требуют заполнения: {result.summary.incomplete_count}",
            "",
        ]
        if page:
            page_count = max(1, (len(items) + ATTENTION_PAGE_SIZE - 1) // ATTENTION_PAGE_SIZE)
            lines.append(f"Страница {offset // ATTENTION_PAGE_SIZE + 1} из {page_count}")
            lines.append(f"Показано {offset + 1}–{offset + len(page)} из {len(items)}")
            lines.append("")
        for index, item in enumerate(page, offset + 1):
            is_open = item.readiness.status is TradeReadinessStatus.OPEN
            status = "🟢 ОТКРЫТА" if is_open else "⚠ НЕ ГОТОВА"
            missing = item.missing_labels or tuple(_telegram_missing_label(reason) for reason in item.readiness.missing)
            detail = "Активная позиция — заполнение не требуется." if is_open else "Не заполнено:\n" + "\n".join(f"• {reason}" for reason in missing)
            direction = getattr(getattr(item.trade, "direction", None), "value", "—")
            lines.extend([f"{index}. {item.instrument_label or 'Инструмент недоступен'} · {direction} · {status}", detail, ""])
        await send(
            event,
            "\n".join(lines).rstrip(),
            attention_keyboard(
                page, category=category, offset=offset, limit=ATTENTION_PAGE_SIZE,
                total=len(items), open_count=result.summary.open_count,
                closed_count=result.summary.incomplete_count,
            ),
            edit=isinstance(event, CallbackQuery),
        )

    @router.callback_query(F.data == "attention")
    async def handle_attention(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_attention(callback)

    @router.callback_query(F.data == "attention:open")
    async def handle_open_attention(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_attention(callback, "open")

    @router.callback_query(F.data == "attention:closed")
    async def handle_closed_attention(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_attention(callback, "closed")

    @router.callback_query(F.data.startswith("attention:page:"))
    async def handle_attention_page(callback: CallbackQuery) -> None:
        _, _, category, raw_offset = callback.data.split(":", 3)
        await callback.answer()
        await show_attention(callback, category, int(raw_offset))

    @router.callback_query(F.data == "attention:noop")
    async def handle_attention_noop(callback: CallbackQuery) -> None:
        await callback.answer()

    @router.callback_query(F.data == "bulk_exclude")
    async def handle_bulk_exclude(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await send(callback, "🧹 Исключить старые незаполненные сделки\n\nБудут рассмотрены только закрытые сделки, не готовые к статистике, и только импортированные записи. Готовые и открытые сделки не затрагиваются.", bulk_exclusion_ranges_keyboard(), edit=True)

    @router.callback_query(lambda callback: bool(callback.data and callback.data in {"bulk:30", "bulk:90"}))
    async def handle_bulk_exclude_range(callback: CallbackQuery, state: FSMContext) -> None:
        days = int(callback.data.rsplit(":", 1)[1])
        try:
            preview = await runtime.preview_bulk_exclude_old_incomplete(
                account_id=settings.journal_account_id,
                older_than=datetime.now(timezone.utc) - timedelta(days=days),
            )
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await state.update_data(bulk_exclusion_preview=preview)
        await callback.answer()
        await send(callback, f"Будет исключено: {len(preview.trade_ids)} незаполненных сделок\n\nПорог: старше {days} дней\n\nГотовые и открытые сделки не затрагиваются. Биржевые факты сохранятся.", bulk_exclusion_preview_keyboard(), edit=True)

    @router.callback_query(F.data == "bulk:custom")
    async def handle_bulk_custom_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.set_state(JournalStates.bulk_custom_date)
        await send(callback, "Введите дату: будут рассмотрены сделки, закрытые до неё (ДД.ММ.ГГГГ).", cancel_keyboard(), edit=True)

    @router.message(JournalStates.bulk_custom_date)
    async def handle_bulk_custom_date(message: Message, state: FSMContext) -> None:
        try:
            cutoff = _parse_history_date(message.text)
            preview = await runtime.preview_bulk_exclude_old_incomplete(account_id=settings.journal_account_id, older_than=cutoff)
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Некорректная дата или предпросмотр не выполнен.")
            return
        await state.update_data(bulk_exclusion_preview=preview)
        await message.answer(f"Будет исключено: {len(preview.trade_ids)} незаполненных сделок\n\nДо даты: {cutoff:%d.%m.%Y}\n\nГотовые и открытые сделки не затрагиваются. Биржевые факты сохранятся.", reply_markup=bulk_exclusion_preview_keyboard())

    @router.callback_query(F.data == "bulk:confirm")
    async def handle_bulk_exclude_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        preview = data.get("bulk_exclusion_preview")
        if preview is None:
            await callback.answer("Предпросмотр устарел.", show_alert=True)
            return
        try:
            count = await runtime.apply_bulk_exclusion(preview, confirm_token=preview.token)
        except (TypeError, ValueError, PermissionError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await state.clear()
        await callback.answer()
        await send(callback, f"✅ Исключено сделок: {count}. Исполнения сохранены.", settings_keyboard(), edit=True)

    def _telegram_missing_label(value: str) -> str:
        return {"INSTRUMENT": "Инструмент", "DIRECTION": "Направление", "ENTRY_PRICE": "Цена входа", "QUANTITY": "Количество", "EXIT_PRICE": "Цена выхода", "NET_PNL": "Результат"}.get(value, "обязательное поле")

    def _period_filter(period: str) -> StatisticsFilter:
        now = datetime.now(timezone.utc)
        if period == "today":
            from_at = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "7d":
            from_at = now - timedelta(days=7)
        elif period == "30d":
            from_at = now - timedelta(days=30)
        elif period == "all":
            from_at = None
        else:
            raise ValueError("unknown statistics period")
        return StatisticsFilter(account_id=settings.journal_account_id, from_at=from_at, status=TradeStatus.CLOSED)

    async def show_statistics(event, period: str = "all") -> None:
        try:
            summary = await runtime.statistics_summary(_period_filter(period))
        except ValueError:
            await send(event, "⚠ За выбранный период есть разные валюты. Общий Net PnL недоступен.", stats_period_keyboard(), edit=isinstance(event, CallbackQuery))
            return
        labels = {"today": "Сегодня", "7d": "7 дней", "30d": "30 дней", "all": "Все время"}
        await send(event, compact_statistics_text(summary, labels[period]), stats_period_keyboard(), edit=isinstance(event, CallbackQuery))

    @router.callback_query(F.data == "statistics")
    async def handle_statistics(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_statistics(callback)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("stats_period:")))
    async def handle_statistics_period(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_statistics(callback, callback.data.split(":", 1)[1])

    async def list_all(event, offset: int = 0) -> None:
        result = await runtime.list_all_trades(ListAllTradesCommand(
            account_id=settings.journal_account_id,
            limit=settings.history_page_size,
            offset=offset,
        ))
        rows = []
        for index, trade in enumerate(result.trades, 1):
            instrument = await runtime.get_instrument(trade.instrument_id)
            rows.append(compact_journal_trade_text(trade, instrument, index=index))
        text = "📚 Сделки\n\n" + ("\n\n".join(rows) or "Сделок пока нет.")
        await send(event, text, trade_list_keyboard(result.trades, offset=offset, limit=settings.history_page_size, has_next=len(result.trades) == settings.history_page_size, all_trades=True), edit=isinstance(event, CallbackQuery))

    @router.callback_query(F.data == "all_trades")
    async def handle_all_trades(callback: CallbackQuery) -> None:
        await callback.answer()
        await list_all(callback)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("all:page:")))
    async def handle_all_page(callback: CallbackQuery) -> None:
        await callback.answer()
        await list_all(callback, int(callback.data.rsplit(":", 1)[1]))

    async def show_details(event, trade_id: str, *, back_callback: str = "menu") -> None:
        try:
            result = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
        except (TypeError, ValueError, ApplicationError) as error:
            if not await expected_error(event, error, edit=isinstance(event, CallbackQuery)):
                await send(event, "❌ Не удалось загрузить сделку.")
            return
        instrument = await runtime.get_instrument(result.trade.instrument_id)
        timezone_name = await journal_timezone_name()
        await send(
            event,
            details_text(result, instrument, timezone_name=timezone_name),
            trade_detail_keyboard(
                result.trade,
                ready=result.readiness is not None and result.readiness.status is TradeReadinessStatus.READY,
                imported=result.has_exchange_executions,
                excluded=result.journal_state is JournalTradeState.EXCLUDED_USER,
                back_callback=back_callback,
            ),
            edit=isinstance(event, CallbackQuery),
        )

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("trade:")))
    async def handle_trade_selection(callback: CallbackQuery) -> None:
        await callback.answer()
        await show_details(callback, callback.data.split(":", 1)[1])

    @router.callback_query(F.data.startswith("recent_trade:"))
    async def handle_recent_trade_selection(callback: CallbackQuery) -> None:
        await callback.answer()
        parts = callback.data.split(":")
        trade_id = parts[1]
        offset = int(parts[2]) if len(parts) > 2 else 0
        await show_details(callback, trade_id, back_callback=f"recent:page:{offset}")

    @router.callback_query(is_trade_edit_callback)
    async def handle_edit(callback: CallbackQuery, state: FSMContext) -> None:
        trade_id = callback.data.split(":", 1)[1]
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await callback.answer()
        await state.clear()
        await state.update_data(
            selected_trade_id=trade_id,
            enrichment_status=details.trade.status.value,
            **context_state(details),
        )
        fields = await runtime.list_custom_fields()
        timezone_name = await journal_timezone_name()
        await send(
            callback,
            "✏️ Редактирование сделки\n\n" + details_text(
                details,
                details.instrument,
                timezone_name=timezone_name,
            ),
            trade_edit_keyboard(details.trade, fields, imported=details.has_exchange_executions),
            edit=True,
        )

    @router.callback_query(lambda callback: bool(
        callback.data
        and (callback.data.startswith("edit_field:") or (
            callback.data.startswith("edit:")
            and callback.data.split(":", 1)[1] not in {"stop", "take", "back"}
        ))
    ))
    async def handle_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        trade_raw = data.get("selected_trade_id")
        field_token = callback.data.split(":", 1)[1]
        field_code = {"plan": "followed_plan"}.get(field_token, field_token)
        if field_code in {"stop", "take", "back"} or not trade_raw:
            await callback.answer("Редактор сделки устарел. Откройте его заново.", show_alert=True)
            await state.clear()
            return
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_raw))
            definition = next((item for item in await runtime.list_custom_fields() if str(item.code) == field_code), None)
            options = () if definition is None else await runtime.list_custom_field_options(definition.id)
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        if definition is None or not definition.is_active or definition.source is not CustomFieldSource.MANUAL:
            await callback.answer("Поле недоступно для редактирования.", show_alert=True)
            return
        await callback.answer()
        await state.update_data(
            selected_trade_id=str(details.trade.trade_id),
            current_field_id=str(definition.id),
            enrichment_status=details.trade.status.value,
            edit_mode=True,
            **context_state(details),
        )
        current = next((item for item in details.custom_values if item.definition and item.definition.id == definition.id), None)
        current_text = custom_value_text(current) if current is not None else f"{definition.name}: —"
        await state.set_state(JournalStates.enrichment_value)
        if definition.value_type is CustomFieldValueType.CHOICE:
            await send(callback, f"{current_text}\n\nВыберите новое значение:", choice_keyboard(options), edit=True)
        elif definition.value_type is CustomFieldValueType.YES_NO:
            await send(callback, f"{current_text}\n\nВыберите новое значение:", yes_no_keyboard(), edit=True)
        else:
            await send(callback, f"{current_text}\n\nВведите новое значение:", cancel_keyboard(), edit=True)

    async def start_protection_edit(callback: CallbackQuery, state: FSMContext, state_value, label: str) -> None:
        data = await state.get_data()
        trade_id = data.get("selected_trade_id")
        if not trade_id:
            await callback.answer("Редактор сделки устарел. Откройте его заново.", show_alert=True)
            return
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        await callback.answer()
        await state.clear()
        await state.update_data(selected_trade_id=str(details.trade.trade_id))
        await state.set_state(state_value)
        current = details.trade.stop_price if state_value is JournalStates.edit_stop_price else details.trade.take_profit
        current_text = "—" if current is None else str(current.value)
        await send(callback, f"{label} (сейчас: {current_text})? Введите цену или нажмите «Пропустить».", cancel_keyboard(allow_skip=True, skip_callback="edit_skip"), edit=True)

    @router.callback_query(F.data == "edit:stop")
    async def handle_edit_stop_start(callback: CallbackQuery, state: FSMContext) -> None:
        await start_protection_edit(callback, state, JournalStates.edit_stop_price, "Stop Loss")

    @router.callback_query(F.data == "edit:take")
    async def handle_edit_take_start(callback: CallbackQuery, state: FSMContext) -> None:
        await start_protection_edit(callback, state, JournalStates.edit_take_profit, "Take Profit")

    async def save_protection(event, state: FSMContext, *, stop_price=None, take_profit=None) -> None:
        data = await state.get_data()
        try:
            await runtime.update_trade_protection(UpdateTradeProtectionCommand(TradeId(data["selected_trade_id"]), stop_price=stop_price, take_profit=take_profit))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(event, error):
                await send(event, "❌ Изменение не сохранено. Повторите ввод.")
            return
        await state.clear()
        await show_details(event, data["selected_trade_id"])

    @router.message(JournalStates.edit_stop_price)
    async def handle_edit_stop(message: Message, state: FSMContext) -> None:
        try: value = Price((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer("❌ Некорректная цена Stop Loss. Повторите ввод.")
            return
        await save_protection(message, state, stop_price=value)

    @router.message(JournalStates.edit_take_profit)
    async def handle_edit_take(message: Message, state: FSMContext) -> None:
        try: value = Price((message.text or "").strip())
        except (TypeError, ValueError):
            await message.answer("❌ Некорректная цена Take Profit. Повторите ввод.")
            return
        await save_protection(message, state, take_profit=value)

    @router.callback_query(F.data == "edit_skip")
    async def handle_edit_skip(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        await callback.answer()
        await state.clear()
        await show_details(callback, data.get("selected_trade_id"))

    @router.callback_query(F.data == "edit:back")
    async def handle_edit_back(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        trade_id = data.get("selected_trade_id")
        await callback.answer()
        await state.clear()
        if trade_id:
            await show_details(callback, trade_id)
        else:
            await show_menu(callback, state)

    async def prepare_action(callback: CallbackQuery, state: FSMContext, state_value, prompt: str):
        trade_id = callback.data.split(":", 1)[1]
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
        except (TypeError, ValueError, ApplicationError) as error:
            await expected_error(callback, error, edit=False)
            return None
        await state.clear()
        await state.update_data(selected_trade_id=str(details.trade.trade_id), currency=details.trade.fees.currency)
        await state.set_state(state_value)
        await callback.answer()
        await send(callback, prompt.format(currency=details.fees.currency), cancel_keyboard())
        return details

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("fee:")))
    async def handle_fee_start(callback: CallbackQuery, state: FSMContext) -> None:
        await prepare_action(callback, state, JournalStates.fee, "Введите комиссию ({currency}) числом.")

    @router.message(JournalStates.fee)
    async def handle_fee(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            amount = Decimal((message.text or "").strip())
            if not amount.is_finite():
                raise ValueError("fee must be finite")
            result = await runtime.add_fee(AddFeeCommand(TradeId(data["selected_trade_id"]), Money(amount, data["currency"])))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Некорректная комиссия. Повторите ввод.")
            return
        await state.clear()
        await show_details(message, data["selected_trade_id"])

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("expense:")))
    async def handle_expense_start(callback: CallbackQuery, state: FSMContext) -> None:
        await prepare_action(callback, state, JournalStates.expense, "Введите подписанную сумму расхода ({currency}), например +25 или -25.")

    @router.message(JournalStates.expense)
    async def handle_expense(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            amount = Decimal((message.text or "").strip())
            if not amount.is_finite():
                raise ValueError("expense must be finite")
            result = await runtime.add_expense(AddExpenseCommand(TradeId(data["selected_trade_id"]), Expense(Money(amount, data["currency"]))))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Некорректный расход. Повторите ввод.")
            return
        await state.clear()
        await show_details(message, data["selected_trade_id"])

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("close:")))
    async def handle_close_start(callback: CallbackQuery, state: FSMContext) -> None:
        await prepare_action(callback, state, JournalStates.exit_price, "Введите цену выхода.")

    @router.message(JournalStates.exit_price)
    async def handle_close(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        try:
            result = await runtime.close_manual_trade(CloseManualTradeCommand(
                TradeId(data["selected_trade_id"]), Price((message.text or "").strip()), datetime.now(timezone.utc)
            ))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(message, error):
                await message.answer("❌ Сделку нельзя закрыть. Повторите цену.")
            return
        await state.clear()
        await show_close_result(message, data["selected_trade_id"])

    async def show_close_result(event, trade_id: str) -> None:
        details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
        instrument = await runtime.get_instrument(details.trade.instrument_id)
        timezone_name = await journal_timezone_name()
        if details.readiness is not None and details.readiness.status is TradeReadinessStatus.READY:
            text = "✓ Сделка готова к статистике\n\n" + details_text(details, instrument, timezone_name=timezone_name)
            markup = trade_detail_keyboard(details.trade, ready=True, imported=details.has_exchange_executions)
        else:
            try:
                enrichment = await runtime.enrich_trade(EnrichTradeCommand(
                    details.trade.trade_id,
                    resolution_context=resolution_context(TradeStatus.CLOSED, details),
                ))
                fields = ", ".join(item.name for item in enrichment.missing_manual_required if item.required_for_statistics) or "обязательные поля"
            except (TypeError, ValueError, ArithmeticError, ApplicationError):
                fields = "обязательные поля"
            text = "Сделка закрыта, но не готова к статистике.\n\nНужно заполнить:\n• " + fields + "\n\n" + details_text(details, instrument, timezone_name=timezone_name)
            markup = readiness_action_keyboard(str(details.trade.trade_id))
        await send(event, text, markup)

    async def present_next(event, state: FSMContext) -> None:
        data = await state.get_data()
        queue = data.get("enrichment_queue", [])
        index = data.get("enrichment_index", 0)
        skipped = set(data.get("enrichment_skipped", []))
        while index < len(queue) and queue[index] in skipped:
            index += 1
        if index >= len(queue):
            trade_id = data["selected_trade_id"]
            trade_status = TradeStatus(data.get("enrichment_status", "OPEN"))
            await state.clear()
            try:
                enrichment = await runtime.enrich_trade(EnrichTradeCommand(
                    TradeId(trade_id), resolution_context=resolution_context(trade_status, state_data=data)
                ))
                details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
            except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
                if not await expected_error(event, error, edit=isinstance(event, CallbackQuery)):
                    await send(event, "❌ Обогащение не удалось завершить.")
                return
            instrument = await runtime.get_instrument(details.trade.instrument_id)
            readiness = details.readiness
            timezone_name = await journal_timezone_name()
            if readiness is not None and readiness.status is TradeReadinessStatus.READY:
                text = "✓ Сделка готова к статистике\n\n" + details_text(details, instrument, timezone_name=timezone_name)
            else:
                text = "Сделка закрыта, но не готова к статистике.\n\n" + details_text(details, instrument, timezone_name=timezone_name)
            await send(event, text, trade_detail_keyboard(details.trade, ready=readiness is not None and readiness.status is TradeReadinessStatus.READY, imported=details.has_exchange_executions), edit=isinstance(event, CallbackQuery))
            return
        field_id = queue[index]
        definition = await runtime.get_custom_field(CustomFieldDefinitionId(field_id))
        if definition is None or not definition.is_active or definition.source is not CustomFieldSource.MANUAL:
            await state.update_data(enrichment_index=index + 1)
            return await present_next(event, state)
        await state.update_data(enrichment_index=index, current_field_id=field_id)
        optional = field_id in set(data.get("enrichment_optional", []))
        suffix = " Можно пропустить." if optional else ""
        await state.set_state(JournalStates.enrichment_value)
        if definition.value_type is CustomFieldValueType.CHOICE:
            options = await runtime.list_custom_field_options(definition.id)
            await send(event, f"Поле: {definition.name}{suffix}", choice_keyboard(options, allow_skip=optional), edit=isinstance(event, CallbackQuery))
        elif definition.value_type is CustomFieldValueType.YES_NO:
            await send(event, f"Поле: {definition.name}{suffix}", yes_no_keyboard(allow_skip=optional), edit=isinstance(event, CallbackQuery))
        else:
            await send(event, f"Поле: {definition.name}{suffix}", cancel_keyboard(allow_skip=optional))

    async def begin_enrichment(callback: CallbackQuery, state: FSMContext) -> None:
        trade_id = callback.data.split(":", 1)[1]
        await callback.answer()
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
            result = await runtime.enrich_trade(EnrichTradeCommand(
                details.trade.trade_id,
                resolution_context=resolution_context(details.trade.status, details),
            ))
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            await expected_error(callback, error, edit=True)
            return
        queue = [str(item.id) for item in result.missing_manual_required if item.required_for_statistics]
        await state.clear()
        await state.update_data(
            selected_trade_id=str(details.trade.trade_id),
            enrichment_queue=queue,
            enrichment_index=0,
            enrichment_optional=[],
            enrichment_skipped=[],
            enrichment_status=details.trade.status.value,
            **context_state(details),
        )
        await present_next(callback, state)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("enrich:")))
    async def handle_enrichment(callback: CallbackQuery, state: FSMContext) -> None:
        await begin_enrichment(callback, state)

    async def submit_manual(event, state: FSMContext, value) -> None:
        data = await state.get_data()
        try:
            command = AddManualCustomValueCommand(
                TradeId(data["selected_trade_id"]),
                CustomFieldDefinitionId(data["current_field_id"]),
                value,
                resolution_context=resolution_context(
                    TradeStatus(data.get("enrichment_status", "OPEN")),
                    state_data=data,
                ),
            )
            if data.get("edit_mode"):
                await runtime.upsert_manual_custom_value(command)
            else:
                await runtime.add_manual_custom_value(command)
        except (TypeError, ValueError, ArithmeticError, ApplicationError) as error:
            if not await expected_error(event, error):
                await send(event, "❌ Значение не принято. Повторите ввод.")
            return
        if data.get("edit_mode"):
            await state.clear()
            await show_details(event, data["selected_trade_id"])
            return
        await state.update_data(enrichment_index=(data.get("enrichment_index", 0) + 1))
        await present_next(event, state)

    @router.message(JournalStates.enrichment_value)
    async def handle_enrichment_value(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        definition = await runtime.get_custom_field(CustomFieldDefinitionId(data["current_field_id"]))
        if definition is None:
            await state.update_data(enrichment_index=data.get("enrichment_index", 0) + 1)
            await present_next(message, state)
            return
        raw = (message.text or "").strip()
        if definition.value_type is CustomFieldValueType.NUMBER:
            try:
                value = Decimal(raw)
                if not value.is_finite():
                    raise ValueError
            except (InvalidOperation, ValueError):
                await message.answer("❌ Нужно конечное число Decimal. Повторите ввод.")
                return
        elif definition.value_type is CustomFieldValueType.TEXT:
            value = raw
        else:
            await message.answer("Выберите значение кнопкой.")
            return
        await submit_manual(message, state, value)

    @router.callback_query(F.data == "field_skip")
    async def handle_field_skip(callback: CallbackQuery, state: FSMContext) -> None:
        data = await state.get_data()
        if data.get("current_field_id") not in set(data.get("enrichment_optional", [])):
            await callback.answer("Это поле обязательно.", show_alert=True)
            return
        await callback.answer()
        skipped = [*data.get("enrichment_skipped", []), data["current_field_id"]]
        await state.update_data(enrichment_skipped=skipped, enrichment_index=data.get("enrichment_index", 0) + 1)
        await present_next(callback, state)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_option:")))
    async def handle_field_option(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        try:
            option_id = CustomFieldOptionId(callback.data.split(":", 1)[1])
        except (TypeError, ValueError):
            await callback.answer("Некорректный вариант.", show_alert=True)
            return
        await submit_manual(callback, state, option_id)

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("field_bool:")))
    async def handle_field_bool(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await submit_manual(callback, state, callback.data.split(":", 1)[1] == "1")

    @router.callback_query(F.data == "cancel")
    async def handle_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await show_menu(callback, state)

    @router.callback_query(F.data == "development")
    async def handle_development(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if not settings.dev_mode:
            await show_menu(callback, state)
            return
        await state.clear()
        await send(callback, "🛠 Development\n\nExecution Lab использует отдельное in-memory состояние и не является журналом сделок.", development_keyboard(), edit=True)

    @router.callback_query(F.data == "execution_lab")
    async def handle_execution_lab(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        if not settings.dev_mode:
            await show_menu(callback, state)
            return
        await state.clear()
        await send(callback, "🧪 Execution Lab\n\nДля acceptance-проверок используйте development harness. Данные не сохраняются в Journal.", development_keyboard(), edit=True)

    return router
