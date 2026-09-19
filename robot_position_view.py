"""Read-only PAPER position view for the Telegram position card and chart.

``load_position_view`` gathers one symbol's durable position, Robot trade,
frozen candidate snapshot and execution evidence from the Terminal store.
``format_position_card`` renders the Telegram caption. Neither function
mutates trading state; the same view serves an open position and a closed
Robot trade (the close post reuses it via ``trade_id``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from terminal.domain.models import (
    Category, OrderId, PositionKey, PositionSide, Symbol, TradingAccountId,
)


PAPER_ACCOUNT_ID = TradingAccountId("paper")
CAPTION_LIMIT = 1024
EXECUTION_WINDOW_MS = 5_000
RESTING_LIMIT_STATUSES = frozenset({"open", "partially_filled"})
NOT_ROBOT_LINE = "Позиция не от робота — график недоступен"


@dataclass(frozen=True)
class TradeMarker:
    time_ms: int
    price: Decimal
    side: str  # "Buy" / "Sell"
    filled: bool  # False = resting limit order not yet executed


@dataclass(frozen=True)
class PositionView:
    symbol: str
    direction: str  # "LONG" / "SHORT"
    is_open: bool
    quantity: Decimal | None
    average_entry: Decimal | None
    stop_price: Decimal | None
    take_price: Decimal | None
    pattern: str | None
    sync_state: str | None = None
    trade: Any = None  # RobotTradeRecord when the position belongs to the Robot
    signal_snapshot: Mapping[str, Any] | None = None
    markers: tuple[TradeMarker, ...] = ()
    last_price: Decimal | None = None

    @property
    def is_robot(self) -> bool:
        return self.trade is not None

    @property
    def entry_time_ms(self) -> int | None:
        return self.trade.entry_time_ms if self.trade is not None else None

    @property
    def exit_time_ms(self) -> int | None:
        return self.trade.exit_time_ms if self.trade is not None else None

    @property
    def exit_price(self) -> Decimal | None:
        return self.trade.exit_price if self.trade is not None else None


def with_last_price(view: PositionView, price: Any) -> PositionView:
    return replace(view, last_price=_decimal(price))


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    try:
        number = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _direction_from_side(side: Any) -> str:
    value = str(getattr(side, "value", side)).strip().upper()
    return value if value in {"LONG", "SHORT"} else value or "—"


def _is_open_projection(projection) -> bool:
    if projection is None or projection.side is PositionSide.FLAT:
        return False
    quantity = _decimal(projection.quantity)
    return quantity is not None and quantity != 0


def _trade_markers(store, account, trade, candidate, *, now_ms: int) -> tuple[TradeMarker, ...]:
    state = candidate.robot_state if candidate is not None else None
    execution = state.get("execution") if isinstance(state, Mapping) else None
    limit_order_id = execution.get("limit_order_id") if isinstance(execution, Mapping) else None
    limit_order_id = str(limit_order_id).strip() if limit_order_id else ""

    if trade.entry_path == "LIMIT" and limit_order_id:
        executions = store.load_executions_for_order(account, OrderId(limit_order_id))
    else:
        start = trade.entry_time_ms - EXECUTION_WINDOW_MS
        end = (trade.exit_time_ms if trade.exit_time_ms is not None else now_ms) + EXECUTION_WINDOW_MS
        executions = tuple(
            item for item in store.load_executions_for_symbol(account, trade.symbol)
            if start <= item.exchange_timestamp_ms <= end
        )
    markers = [
        TradeMarker(item.exchange_timestamp_ms, item.price.value, item.side.value, True)
        for item in executions
    ]

    if limit_order_id:
        limit = store.get_paper_limit(limit_order_id, account)
        if limit is not None and limit.status in RESTING_LIMIT_STATUSES:
            markers.append(TradeMarker(limit.created_at_ms, limit.price, limit.side.value, False))
    return tuple(markers)


def load_position_view(
    store,
    symbol: str,
    *,
    trade_id: str | None = None,
    account: TradingAccountId = PAPER_ACCOUNT_ID,
    now_ms: int | None = None,
) -> PositionView | None:
    """Return the open position for ``symbol`` (or one Robot trade by id).

    Returns ``None`` when there is no open position and no ``trade_id``.
    """

    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    sym = Symbol(str(symbol).strip().upper())
    key = PositionKey(account, Category.LINEAR, sym, 0)
    projection = store.get_position_projection(key)

    if trade_id is not None:
        trade = store.get_robot_trade(trade_id)
        if trade is None or trade.symbol != sym:
            return None
    else:
        if not _is_open_projection(projection):
            return None
        trade = store.get_open_robot_trade_for_symbol(account, sym)

    is_open = trade.exit_time_ms is None if trade is not None else True
    position_open = is_open and _is_open_projection(projection)

    if position_open:
        direction = _direction_from_side(projection.side)
        quantity = _decimal(projection.quantity)
        average_entry = _decimal(projection.average_entry)
    else:
        direction = trade.direction
        quantity = trade.entry_quantity
        average_entry = trade.average_entry

    stop_price = take_price = None
    if position_open:
        protection = store.get_protection_projection(key)
        if protection is not None:
            stop_price = _decimal(protection.stop_loss)
            take_price = _decimal(protection.take_profit)
    if trade is not None:
        stop_price = stop_price if stop_price is not None else trade.stop_price
        take_price = take_price if take_price is not None else trade.take_price

    candidate = snapshot = None
    markers: tuple[TradeMarker, ...] = ()
    pattern = None
    if trade is not None:
        direction = trade.direction
        pattern = trade.pattern
        candidate = store.get_robot_candidate(trade.candidate_id)
        snapshot = candidate.signal_snapshot if candidate is not None else None
        markers = _trade_markers(store, account, trade, candidate, now_ms=now_ms)

    return PositionView(
        symbol=sym.value,
        direction=direction,
        is_open=is_open,
        quantity=quantity,
        average_entry=average_entry,
        stop_price=stop_price,
        take_price=take_price,
        pattern=pattern,
        sync_state=str(projection.sync_state) if projection is not None else None,
        trade=trade,
        signal_snapshot=snapshot,
        markers=markers,
    )


def format_price(value: Any, significant: int = 6) -> str:
    number = _decimal(value)
    if number is None:
        return "—"
    if number == 0:
        return "0"
    places = max(0, significant - 1 - number.adjusted())
    rounded = number.quantize(Decimal(1).scaleb(-places))
    return format(rounded.normalize(), "f")


def _format_quantity(value: Any) -> str:
    number = _decimal(value)
    return "—" if number is None else format(number.normalize(), "f")


def _signed_usdt(value: Decimal) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{format_price(abs(value))} USDT"


def _unrealized_pnl(view: PositionView) -> tuple[Decimal, Decimal] | None:
    if None in (view.last_price, view.average_entry, view.quantity) or view.average_entry == 0:
        return None
    sign = Decimal(-1) if view.direction == "SHORT" else Decimal(1)
    move = (view.last_price - view.average_entry) * sign
    return move * abs(view.quantity), move / view.average_entry * 100


def format_position_card(view: PositionView) -> str:
    lines = [
        f"{view.symbol} · {view.direction}",
        "",
        f"Статус: {'открыта' if view.is_open else 'закрыта'}",
        f"Размер: {_format_quantity(view.quantity)}",
        f"Средний вход: {format_price(view.average_entry)}",
    ]
    if view.is_open:
        pnl = _unrealized_pnl(view)
        lines.append(
            f"PnL: ~{_signed_usdt(pnl[0])} ({pnl[1]:+.2f}%)" if pnl is not None else "PnL: —"
        )
    else:
        trade = view.trade
        reason = f" ({trade.exit_reason})" if trade.exit_reason else ""
        lines.append(f"Выход: {format_price(trade.exit_price)}{reason}")
        if trade.realized_pnl_usdt is not None and trade.realized_pnl_pct is not None:
            lines.append(
                f"PnL: {_signed_usdt(trade.realized_pnl_usdt)} ({trade.realized_pnl_pct:+.2f}%)"
            )
    lines += [
        f"STOP: {format_price(view.stop_price)}",
        f"TAKE: {format_price(view.take_price)}",
        f"Паттерн: {view.pattern or '—'}",
    ]
    if not view.is_robot:
        lines.append(NOT_ROBOT_LINE)
    return "\n".join(lines)[:CAPTION_LIMIT]
