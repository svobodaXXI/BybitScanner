"""Inline keyboards for the development harness."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.trades.trade import Trade
from app.dev_harness.state import InMemoryTradeStore


def main_menu_keyboard(*, dev_mode: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="➕ Новая сделка", callback_data="new_trade")],
        [InlineKeyboardButton(text="📂 Открытые сделки", callback_data="open_trades")],
        [InlineKeyboardButton(text="📚 Все сделки", callback_data="trades")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
    ]
    if dev_mode:
        rows.append([InlineKeyboardButton(text="🛠 Development", callback_data="development")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def menu_keyboard(*, dev_mode: bool = False) -> InlineKeyboardMarkup:
    return main_menu_keyboard(dev_mode=dev_mode)


def direction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🟢 LONG", callback_data="open:LONG"),
                InlineKeyboardButton(text="🔴 SHORT", callback_data="open:SHORT"),
            ],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
        ]
    )


def development_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Execution Lab", callback_data="execution_lab")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
        ]
    )


def execution_lab_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="BUY execution", callback_data="lab:buy"),
                InlineKeyboardButton(text="SELL execution", callback_data="lab:sell"),
            ],
            [
                InlineKeyboardButton(text="Show aggregate", callback_data="lab:show"),
                InlineKeyboardButton(text="Reset lab", callback_data="lab:reset"),
            ],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
        ]
    )


def trade_detail_keyboard(trade: Trade) -> InlineKeyboardMarkup:
    trade_id = str(trade.trade_id)
    rows = []
    if trade.status.value == "OPEN":
        rows.extend(
            [
                [InlineKeyboardButton(text="💰 Добавить комиссию", callback_data=f"fee:{trade_id}")],
                [
                    InlineKeyboardButton(text="➕ Добавить расход", callback_data=f"expense:+:{trade_id}"),
                    InlineKeyboardButton(text="➖ Добавить расход", callback_data=f"expense:-:{trade_id}"),
                ],
                [InlineKeyboardButton(text="🏁 Закрыть сделку", callback_data=f"close:{trade_id}")],
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="📋 Обновить", callback_data=f"trade:{trade_id}")],
            [InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def trades_keyboard(store: InMemoryTradeStore, trades=None) -> InlineKeyboardMarkup:
    trades = store.all() if trades is None else tuple(trades)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{store.symbol_for(trade)} | {trade.direction.value} | {str(trade.trade_id)[:8]}",
                callback_data=f"trade:{trade.trade_id}",
            )
        ]
        for trade in trades
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Меню", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
