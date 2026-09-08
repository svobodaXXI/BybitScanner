"""Data-driven inline keyboards for the production journal UI."""

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.application.dtos import InstrumentView, TradeView
from app.core.accounts.account_id import AccountId
from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.custom_field_option import CustomFieldOption


def _field_status_text(status) -> str:
    return "Активно" if getattr(status, "value", status) == "ACTIVE" else "Неактивно"


def main_menu_keyboard(*, dev_mode: bool = False, webapp_url: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Новая сделка", callback_data="new_trade")],
        [InlineKeyboardButton(text="📂 Открытые сделки", callback_data="open_trades")],
        [InlineKeyboardButton(text="⚠ Требуют заполнения", callback_data="attention")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="statistics")],
        [InlineKeyboardButton(text="⚙ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="🕘 Последние сделки", callback_data="recent_trades")],
    ]
    if dev_mode:
        rows.append([InlineKeyboardButton(text="🛠 Development", callback_data="development")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Поля статистики", callback_data="settings_fields")],
        [InlineKeyboardButton(text="📥 История Bybit", callback_data="settings_bybit_history")],
        [InlineKeyboardButton(text="📅 Начало журнала", callback_data="settings_tracking_start")],
        [InlineKeyboardButton(text="🗑 Исключённые сделки", callback_data="settings_excluded")],
        [InlineKeyboardButton(text="Напоминания", callback_data="settings_reminders")],
        [InlineKeyboardButton(text="Счёт по умолчанию", callback_data="settings_account")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])


def reminders_keyboard(*, enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔕 Выключить" if enabled else "🔔 Включить", callback_data="reminder:toggle")],
        [InlineKeyboardButton(text="🕒 Изменить время", callback_data="reminder:time")],
        [InlineKeyboardButton(text="🌍 Изменить часовой пояс", callback_data="reminder:timezone")],
        [InlineKeyboardButton(text="⬅️ Настройки", callback_data="settings")],
    ])


def reminder_timezone_keyboard(timezones: Iterable[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=f"reminder:timezone:{name}")] for label, name in timezones]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="settings_reminders")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def incomplete_reminder_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Заполнить", callback_data="attention:closed")],
        [InlineKeyboardButton(text="⚠ Требуют внимания", callback_data="attention")],
    ])


def account_selection_keyboard(accounts: Iterable[AccountId]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=f"Счёт {index}", callback_data=f"account:{account_id}")] for index, account_id in enumerate(accounts, 1)]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def direction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 LONG", callback_data="new:LONG"),
            InlineKeyboardButton(text="🔴 SHORT", callback_data="new:SHORT"),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])


def instrument_selection_keyboard(instruments: Iterable[InstrumentView]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=instrument.symbol, callback_data=f"instrument:{instrument.instrument_id}")]
        for instrument in instruments
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_list_keyboard(trades: Iterable[TradeView], *, offset: int = 0, limit: int = 50, has_next: bool = False, all_trades: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text="Подробнее",
            callback_data=f"trade:{trade.trade_id}",
        )]
        for trade in trades
    ]
    if all_trades:
        navigation = []
        if offset > 0:
            navigation.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"all:page:{max(0, offset - limit)}"))
        if has_next:
            navigation.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"all:page:{offset + limit}"))
        if navigation:
            rows.append(navigation)
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recent_trades_keyboard(
    trades: Iterable[TradeView],
    instruments: Iterable[InstrumentView | None],
    *,
    offset: int = 0,
    limit: int = 5,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    """Render one identifiable detail button per recent trade."""
    rows = []
    for index, (trade, instrument) in enumerate(zip(trades, instruments, strict=True), offset + 1):
        symbol = instrument.symbol if instrument is not None else "Сделка"
        rows.append([InlineKeyboardButton(text=f"{index} · {symbol}", callback_data=f"recent_trade:{trade.trade_id}:{offset}")])
    navigation = []
    if offset > 0:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"recent:page:{max(0, offset - limit)}"))
    if has_next:
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"recent:page:{offset + limit}"))
    if navigation:
        rows.append(navigation)
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_detail_keyboard(
    trade: TradeView,
    *,
    ready: bool = False,
    imported: bool = False,
    excluded: bool = False,
    back_callback: str = "menu",
) -> InlineKeyboardMarkup:
    trade_id = str(trade.trade_id)
    rows = []
    rows.append([InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit:{trade_id}")])
    if trade.status.value == "OPEN":
        rows.append([InlineKeyboardButton(text="✅ Закрыть сделку", callback_data=f"close:{trade_id}")])
    elif not ready:
        rows.append([InlineKeyboardButton(text="✍️ Заполнить обязательные поля", callback_data=f"enrich:{trade_id}")])
    if imported and trade.status.value == "CLOSED" and not ready and not excluded:
        rows.append([InlineKeyboardButton(text="🗑 Исключить из журнала", callback_data=f"exclude:{trade_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trade_edit_keyboard(
    trade: TradeView,
    fields: Iterable[CustomFieldDefinition] = (),
    *,
    imported: bool = False,
) -> InlineKeyboardMarkup:
    trade_id = str(trade.trade_id)
    rows = [
        [InlineKeyboardButton(text="Изменить Stop Loss", callback_data="edit:stop")],
        [InlineKeyboardButton(text="Изменить Take Profit", callback_data="edit:take")],
    ]
    manual_fields = tuple(item for item in fields if item.is_active and item.source.value == "MANUAL")
    if imported:
        manual_fields = tuple(item for item in manual_fields if str(item.code) in {"strategy", "setup", "followed_plan", "error", "comment"})
    for field in manual_fields:
        callback_data = {
            "strategy": "edit:strategy",
            "setup": "edit:setup",
            "followed_plan": "edit:plan",
            "error": "edit:error",
            "comment": "edit:comment",
        }.get(str(field.code), f"edit_field:{field.code}")
        rows.append([InlineKeyboardButton(text=field.name, callback_data=callback_data)])
    if not imported:
        rows.append([
            InlineKeyboardButton(text="Добавить комиссию", callback_data=f"fee:{trade_id}"),
            InlineKeyboardButton(text="Добавить расход", callback_data=f"expense:{trade_id}"),
        ])
    rows.extend([
        [InlineKeyboardButton(text="✍️ Заполнить обязательные поля", callback_data=f"enrich:{trade_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="edit:back")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def field_management_keyboard(fields: Iterable[CustomFieldDefinition]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"{field.name} · {_field_status_text(field.status)}", callback_data=f"field_manage:{field.id}")]
        for field in fields
    ]
    rows.extend([
        [InlineKeyboardButton(text="➕ Добавить поле", callback_data="field_add")],
        [InlineKeyboardButton(text="⬅️ Настройки", callback_data="settings")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def field_definition_keyboard(field: CustomFieldDefinition, options: Iterable[CustomFieldOption] = ()) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Активно" if field.is_active else "Активировать", callback_data=f"field_toggle:{field.id}")],
        [InlineKeyboardButton(text=f"Обязательно: {'Да' if field.required_for_statistics else 'Нет'}", callback_data=f"field_required:{field.id}")],
    ]
    if field.value_type.value == "CHOICE":
        rows.append([InlineKeyboardButton(text="➕ Добавить вариант", callback_data=f"option_add:{field.id}")])
        rows.extend(
            [InlineKeyboardButton(text=f"{'Выключить' if option.active else 'Включить'}: {option.label}", callback_data=f"option_toggle:{option.id}")]
            for option in options
        )
    rows.append([InlineKeyboardButton(text="⬅️ Поля статистики", callback_data="settings_fields")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def field_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="CHOICE", callback_data="field_type:CHOICE")],
        [InlineKeyboardButton(text="YES_NO", callback_data="field_type:YES_NO")],
        [InlineKeyboardButton(text="TEXT", callback_data="field_type:TEXT")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings_fields")],
    ])


def stats_period_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня", callback_data="stats_period:today"), InlineKeyboardButton(text="7 дней", callback_data="stats_period:7d")],
        [InlineKeyboardButton(text="30 дней", callback_data="stats_period:30d"), InlineKeyboardButton(text="Все время", callback_data="stats_period:all")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])


def after_create_keyboard(trade: TradeView) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Открытые сделки", callback_data="open_trades")],
        [InlineKeyboardButton(text="Главное меню", callback_data="menu")],
    ])


def new_trade_notification_keyboard(trade_id: str) -> InlineKeyboardMarkup:
    """Durable actions for a trade created by incremental exchange sync."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Заполнить сделку", callback_data=f"edit:{trade_id}")],
        [InlineKeyboardButton(text="📂 Открытые сделки", callback_data="open_trades")],
    ])


def readiness_action_keyboard(trade_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Заполнить сейчас", callback_data=f"enrich:{trade_id}")],
        [InlineKeyboardButton(text="Позже", callback_data="menu")],
    ])


def attention_keyboard(
    items: Iterable,
    *,
    category: str = "all",
    offset: int = 0,
    limit: int = 5,
    total: int | None = None,
    open_count: int | None = None,
    closed_count: int | None = None,
) -> InlineKeyboardMarkup:
    """Render bounded Attention rows with durable trade callbacks."""
    items = tuple(items)
    if total is None:
        total = len(items)
    if open_count is None:
        open_count = sum(
            getattr(item.readiness.status, "value", item.readiness.status) == "OPEN"
            for item in items
        )
    if closed_count is None:
        closed_count = max(0, total - open_count)
    rows = []
    if category == "all":
        rows.append([
            InlineKeyboardButton(text=f"🟢 Открытые · {open_count}", callback_data="attention:open"),
            InlineKeyboardButton(text=f"⚠ Закрытые · {closed_count}", callback_data="attention:closed"),
        ])
    for index, item in enumerate(items, offset + 1):
        symbol = item.instrument_label or "Сделка"
        rows.append([InlineKeyboardButton(text=f"📄 Открыть {index} · {symbol}", callback_data=f"trade:{item.trade_id}")])
        if getattr(item.readiness.status, "value", item.readiness.status) == "INCOMPLETE":
            rows.append([InlineKeyboardButton(text=f"✍️ Заполнить {index} · {symbol}", callback_data=f"enrich:{item.trade_id}")])
    if total:
        navigation = []
        if offset > 0:
            navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"attention:page:{category}:{max(0, offset - limit)}"))
        if offset + limit < total:
            navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"attention:page:{category}:{offset + limit}"))
        if navigation:
            rows.append(navigation)
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")])
    if category in {"all", "closed"}:
        rows.insert(-1, [InlineKeyboardButton(text="🧹 Исключить старые", callback_data="bulk_exclude")])
    if category != "all":
        rows.insert(-1, [InlineKeyboardButton(text="⚠ Все требуют внимания", callback_data="attention")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bulk_exclusion_ranges_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Старше 30 дней", callback_data="bulk:30")],
        [InlineKeyboardButton(text="Старше 90 дней", callback_data="bulk:90")],
        [InlineKeyboardButton(text="До выбранной даты", callback_data="bulk:custom")],
        [InlineKeyboardButton(text="Отмена", callback_data="attention")],
    ])


def bulk_exclusion_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подтвердить", callback_data="bulk:confirm")],
        [InlineKeyboardButton(text="Отмена", callback_data="attention")],
    ])


def choice_keyboard(options: Iterable[CustomFieldOption], *, allow_skip: bool = False) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=option.label, callback_data=f"field_option:{option.id}")] for option in options]
    if allow_skip:
        rows.append([InlineKeyboardButton(text="Пропустить", callback_data="field_skip")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def yes_no_keyboard(*, allow_skip: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="Да", callback_data="field_bool:1"),
            InlineKeyboardButton(text="Нет", callback_data="field_bool:0"),
        ],
    ]
    if allow_skip:
        rows.append([InlineKeyboardButton(text="Пропустить", callback_data="field_skip")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_keyboard(*, allow_skip: bool = False, skip_callback: str = "field_skip") -> InlineKeyboardMarkup:
    rows = []
    if allow_skip:
        rows.append([InlineKeyboardButton(text="Пропустить", callback_data=skip_callback)])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def development_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧪 Execution Lab", callback_data="execution_lab")],
        [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
    ])


def bybit_history_modes_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Только новые сделки", callback_data="bybit:mode:NEW_ONLY")],
        [InlineKeyboardButton(text="📅 Последние 30 дней", callback_data="bybit:mode:LAST_30_DAYS")],
        [InlineKeyboardButton(text="📚 Вся доступная история", callback_data="bybit:mode:ALL_AVAILABLE")],
        [InlineKeyboardButton(text="🗓 Выбрать период", callback_data="bybit:custom")],
        [InlineKeyboardButton(text="🔄 Проверить историю заново", callback_data="bybit:refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
    ])


def bybit_import_preview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Импортировать", callback_data="bybit:confirm")],
        [InlineKeyboardButton(text="Изменить период", callback_data="bybit:period")],
        [InlineKeyboardButton(text="🟢 Только новые сделки", callback_data="bybit:mode:NEW_ONLY")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")],
    ])


def bybit_new_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Начать с новых сделок", callback_data="bybit:new-only:confirm")],
        [InlineKeyboardButton(text="Изменить период", callback_data="bybit:period")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")],
    ])


def bybit_preview_error_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Повторить", callback_data="bybit:refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings_bybit_history")],
    ])


def bybit_history_missing_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Проверить историю", callback_data="bybit:refresh")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
    ])


def excluded_trade_keyboard(trade_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="↩️ Восстановить эту сделку", callback_data=f"restore:{trade_id}:0")],
        [InlineKeyboardButton(text="⬅️ Настройки", callback_data="settings")],
    ])


def excluded_trades_keyboard(
    trades: Iterable[TradeView],
    labels: Iterable[str] = (),
    *,
    offset: int = 0,
    limit: int = 5,
    total: int | None = None,
    has_next: bool = False,
) -> InlineKeyboardMarkup:
    trades = tuple(trades)
    labels = tuple(labels)
    rows = []
    for index, trade in enumerate(trades, offset + 1):
        label = labels[index - offset - 1] if index - offset - 1 < len(labels) else "Сделка"
        rows.append([InlineKeyboardButton(text=f"↩️ {index} · {label}", callback_data=f"restore:{trade.trade_id}:{offset}")])
    if total is None:
        total = offset + len(trades) + (1 if has_next else 0)
    if total:
        navigation = []
        if offset:
            navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"excluded:page:{max(0, offset - limit)}"))
        if has_next:
            navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"excluded:page:{offset + limit}"))
        if navigation:
            rows.append(navigation)
    rows.append([InlineKeyboardButton(text="⬅️ Настройки", callback_data="settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
