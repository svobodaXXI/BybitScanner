"""Presentation formatting only; all business values come from Application."""

from decimal import Decimal, ROUND_HALF_UP

from app.application.dtos import CustomValueView, GetTradeDetailsResult, InstrumentView, TradeView
from app.core.monitoring.reminders import _zone
from app.core.trades.enums import TradeDirection
from app.core.trades.readiness import TradeReadinessStatus, evaluate_trade_readiness


_AUTOMATIC_FACTOR_LABELS = (
    ("entry_day_of_week", "День недели входа"),
    ("volume_1d_at_entry", "Дневной объём к входу"),
    ("turnover_1d_at_entry", "Дневной оборот к входу"),
    ("previous_day_volume", "Объём предыдущего дня"),
    ("previous_day_turnover", "Оборот предыдущего дня"),
    ("avg_volume_prev_5d", "Средний объём за 5 дней"),
    ("avg_turnover_prev_5d", "Средний оборот за 5 дней"),
    ("rvol_at_entry", "RVOL на входе"),
)
_WEEKDAY_NAMES = (
    "Понедельник", "Вторник", "Среда", "Четверг",
    "Пятница", "Суббота", "Воскресенье",
)


def decimal_text(value, *, decimal_places: int | None = None) -> str:
    text = format(value, "f" if decimal_places is None else f".{decimal_places}f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def statistics_decimal_text(value, *, decimal_places: int) -> str:
    """Bound Decimal output for Telegram only; stored values remain exact."""
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        decimal = value
    elif isinstance(value, int):
        decimal = Decimal(value)
    else:
        decimal = Decimal(str(value))
    quantum = Decimal(1).scaleb(-decimal_places)
    decimal = decimal.quantize(quantum, rounding=ROUND_HALF_UP)
    if decimal == 0:
        decimal = abs(decimal)
    text = format(decimal, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def money_text(value, *, signed: bool = False, decimal_places: int | None = None) -> str:
    if value is None:
        return "—"
    amount = decimal_text(value.amount, decimal_places=decimal_places)
    if signed and value.amount > 0:
        amount = "+" + amount
    return f"{amount} {value.currency}"


def automatic_factors_text(observations=(), *, closed: bool = False) -> str:
    """Render selected automatic observations without exposing storage metadata."""
    by_factor = {item.factor_id: item for item in observations}
    lines = ["Автоданные"]
    for factor_id, label in _AUTOMATIC_FACTOR_LABELS:
        lines.append(f"{label}: {_automatic_factor_value_text(factor_id, by_factor.get(factor_id))}")
    if closed:
        lines.append(
            "Длительность сделки: "
            + _automatic_factor_value_text("holding_duration_seconds", by_factor.get("holding_duration_seconds"))
        )
    return "\n".join(lines)


def _automatic_factor_value_text(factor_id, observation) -> str:
    if observation is None or observation.value is None:
        return "—"
    if getattr(observation.quality_status, "value", observation.quality_status) != "VALID":
        return "—"
    if getattr(observation.availability_status, "value", observation.availability_status) != "AVAILABLE":
        return "—"
    value = observation.value
    if factor_id == "entry_day_of_week":
        try:
            return _WEEKDAY_NAMES[int(value) - 1]
        except (TypeError, ValueError, IndexError):
            return "—"
    if factor_id == "rvol_at_entry":
        return f"{statistics_decimal_text(value, decimal_places=2)}x"
    if factor_id == "holding_duration_seconds":
        return _duration_text(value)
    suffix = " USDT" if (observation.currency or observation.unit) == "USDT" else ""
    if suffix:
        return f"{_readable_decimal_text(value, decimal_places=2)}{suffix}"
    return _readable_decimal_text(value)


def _readable_decimal_text(value, *, decimal_places: int | None = None) -> str:
    if decimal_places is not None:
        text = statistics_decimal_text(value, decimal_places=decimal_places)
    else:
        text = format(Decimal(str(value)), "f")
    sign = ""
    if text.startswith(("-", "+")):
        sign, text = text[0], text[1:]
    integer, separator, fraction = text.partition(".")
    grouped = f"{int(integer):,}".replace(",", " ")
    return sign + grouped + (separator + fraction.rstrip("0") if fraction.rstrip("0") else "")


def _duration_text(value) -> str:
    """Display exact stored seconds with fractional seconds truncated for UI."""
    total_seconds = max(0, int(Decimal(str(value))))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes:02d} мин {seconds:02d} сек"
    if minutes:
        return f"{minutes} мин {seconds:02d} сек"
    return f"{seconds} сек"


def trade_text(
    trade: TradeView,
    instrument: InstrumentView | None = None,
    *,
    timezone_name: str = "UTC",
    custom_values: tuple[CustomValueView, ...] = (),
    field_definitions=(),
    readiness=None,
    automatic_observations=(),
) -> str:
    is_open = trade.status.value == "OPEN"
    lines = [
        f"{'🟢 СДЕЛКА ОТКРЫТА' if is_open else '✅ СДЕЛКА ЗАКРЫТА'}",
        "",
        f"Инструмент: {instrument.symbol if instrument is not None else 'не найден в каталоге'}",
        f"Направление: {trade.direction.value}",
        "",
        f"Вход: {decimal_text(trade.entry_price.value)}",
        f"Дата/время входа: {datetime_text(trade.opened_at, timezone_name)}",
    ]
    if not is_open:
        lines.extend([
            "",
            f"Выход: {decimal_text(trade.exit_price.value) if trade.exit_price else '—'}",
            f"Дата/время выхода: {datetime_text(trade.closed_at, timezone_name)}",
        ])
    lines.extend([
        "",
        f"{'Количество / текущий объём' if is_open else 'Количество'}: {decimal_text(trade.quantity.value)}",
        "",
        f"Стоп: {decimal_text(trade.stop_price.value) if trade.stop_price else '—'}",
        f"Take Profit: {decimal_text(trade.take_profit.value) if trade.take_profit else '—'}",
        f"R/R: {planned_rr_text(trade)}",
        "",
        f"Комиссии: {money_text(trade.fees)}",
    ])
    if is_open:
        lines.append("Net PnL: — (сделка ещё открыта)")
    else:
        lines.append(f"Net PnL: {money_text(trade.net_pnl, signed=True)}")
    # Keep direct DTO formatting and the catalog-backed production path
    # identical: a trade detail always shows the journal context block.
    lines.extend(["", automatic_factors_text(
        automatic_observations,
        closed=not is_open,
    )])
    lines.extend(["", *custom_fields_text(custom_values, field_definitions)])
    if readiness is not None:
        lines.extend(["", readiness_text(readiness, field_definitions)])
    if is_open:
        lines.extend(["", "Статус: 🟢 ОТКРЫТА"])
    return "\n".join(lines)


def custom_value_text(item: CustomValueView) -> str:
    value = item.value.value
    if item.option is not None:
        rendered = item.option.label
    elif hasattr(value, "value"):
        rendered = str(value)
    elif isinstance(value, bool):
        rendered = "Да" if value else "Нет"
    else:
        rendered = decimal_text(value) if hasattr(value, "as_tuple") else str(value)
    definition = item.definition
    label = definition.name if definition is not None else "Дополнительное поле"
    suffix = " (неактивное поле)" if definition is not None and not definition.is_active else ""
    return f"{label}{suffix}: {rendered}"


def details_text(
    result: GetTradeDetailsResult,
    instrument: InstrumentView | None = None,
    *,
    timezone_name: str = "UTC",
) -> str:
    instrument = instrument or result.instrument
    readiness = result.readiness or evaluate_trade_readiness(result.trade)
    return trade_text(
        result.trade,
        instrument,
        timezone_name=timezone_name,
        custom_values=result.custom_values,
        field_definitions=result.field_definitions,
        readiness=readiness,
        automatic_observations=result.automatic_observations,
    )


def _missing_label(value: str) -> str:
    return {
        "INSTRUMENT": "инструмент", "DIRECTION": "направление", "ENTRY_PRICE": "цена входа",
        "QUANTITY": "количество", "EXIT_PRICE": "цена выхода", "NET_PNL": "результат сделки",
    }.get(value, "обязательное поле" if value.startswith("dynamic_field:") else value)


def compact_open_trade_text(
    trade: TradeView,
    instrument: InstrumentView | None = None,
    *,
    index: int | None = None,
    timezone_name: str = "UTC",
) -> str:
    prefix = f"{index}. " if index is not None else ""
    return "\n".join([
        f"{prefix}🟢 {instrument.symbol if instrument else 'Инструмент недоступен'} · {trade.direction.value}",
        "   ОТКРЫТА",
        f"   Вход: {decimal_text(trade.entry_price.value)}",
        f"   Количество / текущий объём: {decimal_text(trade.quantity.value)}",
        f"   Открыта: {datetime_text(trade.opened_at, timezone_name)}",
    ])


def new_trade_notification_text(
    trade: TradeView,
    instrument: InstrumentView | None = None,
    *,
    timezone_name: str = "UTC",
) -> str:
    """Compact, factual notification for one newly created logical trade."""
    return "🆕 Новая сделка в журнале\n\n" + compact_open_trade_text(
        trade, instrument, timezone_name=timezone_name,
    ) + "\n\nЗаполните контекст сделки в Telegram."


def incomplete_reminder_text(count: int) -> str:
    return (
        "⚠ Есть незаполненные сделки\n\n"
        f"Требуют заполнения: {int(count)}\n\n"
        "Заполните обязательные поля, чтобы сделки попали в статистику."
    )


def compact_recent_trade_text(trade: TradeView, instrument: InstrumentView | None = None, *, index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else ""
    return "\n".join([
        f"{prefix}{instrument.symbol if instrument else 'Инструмент недоступен'}",
        f"{trade.direction.value} · {'ЗАКРЫТА' if trade.status.value == 'CLOSED' else 'ОТКРЫТА'}",
        f"Net PnL: {money_text(trade.net_pnl, signed=True, decimal_places=4)}",
    ])


def compact_journal_trade_text(
    trade: TradeView,
    instrument: InstrumentView | None = None,
    *,
    index: int | None = None,
    timezone_name: str = "UTC",
) -> str:
    """Render one unified Journal row without hiding lifecycle state."""
    if trade.status.value == "OPEN":
        return compact_open_trade_text(trade, instrument, index=index, timezone_name=timezone_name)
    prefix = f"{index}. " if index is not None else ""
    return "\n".join([
        f"{prefix}✅ {instrument.symbol if instrument else 'Инструмент недоступен'} · {trade.direction.value}",
        "   ЗАКРЫТА",
        f"   Net PnL: {money_text(trade.net_pnl, signed=True, decimal_places=4)}",
        f"   Закрыта: {datetime_text(trade.closed_at, timezone_name)}",
    ])


def datetime_text(value, timezone_name: str = "UTC") -> str:
    if value is None:
        return "—"
    return value.astimezone(_zone(timezone_name)).strftime("%d.%m.%Y %H:%M:%S")


def planned_rr_text(trade: TradeView) -> str:
    if trade.stop_price is None or trade.take_profit is None:
        return "—"
    if trade.direction is TradeDirection.LONG:
        risk = trade.entry_price.value - trade.stop_price.value
        reward = trade.take_profit.value - trade.entry_price.value
    else:
        risk = trade.stop_price.value - trade.entry_price.value
        reward = trade.entry_price.value - trade.take_profit.value
    if risk <= 0 or reward <= 0:
        return "—"
    return f"1:{format(reward / risk, '.2f')}"


_CANONICAL_FIELDS = (
    ("strategy", "Стратегия"),
    ("setup", "Сетап"),
    ("followed_plan", "По плану?"),
    ("error", "Ошибка"),
    ("comment", "Комментарий"),
)


def custom_fields_text(custom_values, field_definitions=()):
    by_code = {
        str(item.definition.code): item
        for item in custom_values
        if item.definition is not None
    }
    lines = []
    for code, label in _CANONICAL_FIELDS:
        item = by_code.get(code)
        lines.append(custom_value_text(item) if item is not None else f"{label}: —")
    canonical_codes = {code for code, _ in _CANONICAL_FIELDS}
    lines.extend(
        custom_value_text(item)
        for item in custom_values
        if item.definition is None or str(item.definition.code) not in canonical_codes
    )
    return lines


def readiness_text(readiness, field_definitions=()) -> str:
    if readiness.status is TradeReadinessStatus.OPEN:
        return "Текущая готовность: ОТКРЫТА"
    if readiness.status is TradeReadinessStatus.READY:
        return "Готовность: ✓ ГОТОВА"
    labels = {
        str(item.id): item.name
        for item in field_definitions
        if getattr(item, "required_for_statistics", False)
    }
    missing = [labels.get(item.removeprefix("dynamic_field:"), _missing_label(item)) for item in readiness.missing]
    return "Готовность: ⚠ НЕ ГОТОВА\nНе заполнено:\n" + "\n".join(f"• {item}" for item in missing)


def compact_statistics_text(summary, period: str) -> str:
    currency = summary.currency or "—"
    win_rate = "—" if summary.win_rate is None else f"{statistics_decimal_text(summary.win_rate * 100, decimal_places=2)}%"
    return "\n".join([
        f"📊 Статистика · {period}", "", f"Сделок: {summary.trade_count}",
        f"Net PnL: {statistics_decimal_text(summary.net_pnl, decimal_places=4)} {currency}",
        f"Win Rate: {win_rate}",
        f"Profit Factor: {statistics_decimal_text(summary.profit_factor, decimal_places=2)}",
        f"Expectancy: {statistics_decimal_text(summary.expectancy, decimal_places=4)} {currency}",
        "", f"Готовы к статистике: {summary.ready_count}",
        f"Не заполнены: {summary.excluded_incomplete_count}", f"Открытых: {summary.open_count}",
    ])
