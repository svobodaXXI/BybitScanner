"""Telegram-independent formatting for the development harness."""

from collections.abc import Iterable
from decimal import Decimal

from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.execution import Execution
from app.core.trades.trade_aggregate import TradeAggregate
from app.core.trades.trade import Trade


def format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def format_money(money: Money | None, *, signed: bool = False) -> str:
    if money is None:
        return "—"
    amount = format_decimal(money.amount)
    if signed and money.amount > 0:
        amount = f"+{amount}"
    return f"{amount} {money.currency}"


def format_fee(money: Money) -> str:
    """Display a non-negative domain fee as a negative cost."""
    if money.amount == 0:
        return f"0 {money.currency}"
    return f"-{format_decimal(money.amount)} {money.currency}"


def format_expenses(expenses: Iterable[Expense], currency: str) -> str:
    expenses = tuple(expenses)
    lines = [format_money(expense.amount, signed=True) for expense in expenses]
    total = Money(0, currency)
    for expense in expenses:
        total += expense.amount
    rendered = "\n".join(lines) if lines else "—"
    return f"Расходы:\n{rendered}\n\nИтог с учётом знака: {format_money(total, signed=True)}"


def short_trade_id(trade: Trade) -> str:
    return str(trade.trade_id)[:8]


def format_trade(trade: Trade, instrument_symbol: str) -> str:
    status = trade.status.value
    status_label = {"OPEN": "ОТКРЫТА", "CLOSED": "ЗАКРЫТА"}.get(status, status)
    lines = [
        f"{'✅ СДЕЛКА ЗАКРЫТА' if status == 'CLOSED' else '✅ СДЕЛКА ОТКРЫТА'}",
        "",
        f"Идентификатор сделки: {short_trade_id(trade)}",
        f"Инструмент: {instrument_symbol}",
        f"Направление: {trade.direction.value}",
        f"Статус: {status_label}",
        "",
        f"Цена входа: {format_decimal(trade.entry_price.value)}",
        f"Цена выхода: {format_decimal(trade.exit_price.value) if trade.exit_price else '—'}",
        f"Количество: {format_decimal(trade.quantity.value)}",
        f"Стоп-цена: {format_decimal(trade.stop_price.value) if trade.stop_price else '—'}",
        f"Риск: {format_money(trade.risk.amount if trade.risk else None)}",
        "",
        f"Комиссии: {format_fee(trade.fees)}",
        format_expenses(trade.expenses, trade.fees.currency),
        "",
        f"Валовая прибыль: {format_money(trade.gross_pnl, signed=True)}",
        f"Чистая прибыль: {format_money(trade.net_pnl, signed=True)}",
        "",
        f"Открыта: {trade.opened_at.isoformat(sep=' ', timespec='minutes')} UTC",
        f"Закрыта: {trade.closed_at.isoformat(sep=' ', timespec='minutes')} UTC"
        if trade.closed_at
        else "Закрыта: —",
    ]
    return "\n".join(lines)


def format_trade_list(trades: Iterable[tuple[Trade, str]]) -> str:
    entries = []
    for trade, symbol in trades:
        if trade.net_pnl is None:
            details = (
                f"{symbol} | {trade.direction.value} | "
                f"Вход {format_decimal(trade.entry_price.value)} | "
                f"Кол-во {format_decimal(trade.quantity.value)}"
            )
        else:
            details = (
                f"{symbol} | {trade.direction.value} | "
                f"Чистая прибыль {format_money(trade.net_pnl, signed=True)}"
            )
        status_label = {"OPEN": "ОТКРЫТА", "CLOSED": "ЗАКРЫТА"}.get(trade.status.value, trade.status.value)
        entries.append(f"{status_label}\n{details}\nСделка: {short_trade_id(trade)}")
    return "\n\n".join(entries) if entries else "Сделок пока нет."


def format_aggregate(aggregate: TradeAggregate, instrument_symbol: str = "TEST") -> str:
    """Render aggregation state without calculating any domain values."""
    status = "OPEN" if aggregate.status is TradeStatus.OPEN else "CLOSED"
    return "\n".join(
        [
            "TRADE AGGREGATE",
            "",
            f"TradeId: {short_trade_id(aggregate)}",
            f"Instrument: {instrument_symbol}",
            f"Direction: {aggregate.direction.value}",
            f"Status: {status}",
            f"Open Qty: {format_decimal(aggregate.open_quantity.value)}",
            f"Avg Entry: {format_decimal(aggregate.average_entry.value)}",
            f"Realized Qty: {format_decimal(aggregate.realized_quantity.value)}",
            f"Realized Gross PnL: {format_money(aggregate.realized_gross_pnl, signed=True)}",
            f"Fees: {format_fee(aggregate.total_fees)}",
            f"Net Realized PnL: {format_money(aggregate.net_realized_pnl, signed=True)}",
            f"Executions: {aggregate.execution_count}",
        ]
    )


def format_execution_lab_result(
    execution: Execution,
    aggregate: TradeAggregate,
    *,
    duplicate: bool = False,
) -> str:
    """Render the outcome of an Execution Lab action."""
    if duplicate:
        heading = "DUPLICATE EXECUTION IGNORED"
    elif aggregate.status is TradeStatus.CLOSED:
        heading = "TRADE CLOSED"
    elif (
        aggregate.direction is TradeDirection.LONG and execution.side.value == "SELL"
    ) or (
        aggregate.direction is TradeDirection.SHORT and execution.side.value == "BUY"
    ):
        heading = "PARTIAL CLOSE"
    else:
        heading = "EXECUTION APPLIED"

    return "\n".join(
        [
            heading,
            "",
            f"{execution.side.value} {format_decimal(execution.quantity.value)} @ {format_decimal(execution.price.value)}",
            "",
            format_aggregate(aggregate),
        ]
    )


def start_text() -> str:
    return (
        "Торговый журнал — тестовый контур\n\n"
        "Этап 1.5: Telegram-тестирование ядра сделок\n\n"
        "Доменные проверки: этап 1\n"
        "Хранилище: ПАМЯТЬ\n"
        "Режим: РАЗРАБОТКА\n\n"
        "Доступны несколько открытых сделок одновременно.\n"
        "Частичные исполнения и частичные закрытия пока не реализованы."
    )
