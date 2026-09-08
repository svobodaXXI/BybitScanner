"""Telegram handlers for the Phase 1 development harness."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from aiogram import BaseMiddleware, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide, TradeDirection
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId

from .config import is_authorized
from .formatting import (
    format_aggregate,
    format_execution_lab_result,
    format_trade,
    format_trade_list,
    start_text,
)
from .keyboards import (
    execution_lab_keyboard,
    development_keyboard,
    direction_keyboard,
    main_menu_keyboard,
    menu_keyboard,
    trade_detail_keyboard,
    trades_keyboard,
)
from .state import ExecutionLabState, InMemoryTradeStore

logger = logging.getLogger(__name__)

DEMO_ACCOUNT_ID = AccountId.parse("00000000-0000-0000-0000-000000000001")


class HarnessStates(StatesGroup):
    instrument = State()
    entry_price = State()
    quantity = State()
    currency = State()
    stop_price = State()
    risk_money = State()
    fee = State()
    expense = State()
    exit_price = State()
    execution_price = State()
    execution_quantity = State()
    execution_fee = State()
    execution_external_id = State()


class AuthorizationMiddleware(BaseMiddleware):
    """Protect every message and callback handler with the configured whitelist."""

    def __init__(self, allowed_user_id: int | None) -> None:
        self.allowed_user_id = allowed_user_id

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = getattr(event, "from_user", None)
        user_id = user.id if user is not None else None
        if user_id is None or not is_authorized(user_id, self.allowed_user_id):
            logger.warning("Неавторизованный пользователь Telegram попытался получить доступ: %s", user_id)
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Доступ запрещён.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⛔ Доступ запрещён.")
            return None

        logger.info("Пользователь авторизован: user_id=%s", user_id)
        return await handler(event, data)


def create_router(store: InMemoryTradeStore, *, dev_mode: bool = False) -> Router:
    router = Router(name="dev_harness")

    async def show_main_menu(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(start_text(), reply_markup=main_menu_keyboard(dev_mode=dev_mode))

    @router.message(CommandStart())
    async def handle_start(message: Message, state: FSMContext) -> None:
        await show_main_menu(message, state)

    execution_lab = ExecutionLabState()

    async def show_execution_lab(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        aggregate = execution_lab.aggregate()
        text = (
            "🧪 Execution Lab\n\n"
            "Инструмент: TEST\n"
            "Валюта комиссии: USDT\n\n"
            + (format_aggregate(aggregate) if aggregate is not None else "Исполнений пока нет.")
        )
        if callback.message:
            await callback.message.edit_text(text, reply_markup=execution_lab_keyboard())

    @router.callback_query(F.data == "execution_lab")
    async def handle_execution_lab(callback: CallbackQuery, state: FSMContext) -> None:
        if not dev_mode:
            await callback.answer("Development mode отключён.", show_alert=True)
            return
        await show_execution_lab(callback, state)

    @router.callback_query(F.data == "development")
    async def handle_development(callback: CallbackQuery, state: FSMContext) -> None:
        if not dev_mode:
            await callback.answer("Development mode отключён.", show_alert=True)
            return
        await callback.answer()
        await state.clear()
        if callback.message:
            await callback.message.edit_text("🛠 Development", reply_markup=development_keyboard())

    async def begin_execution(callback: CallbackQuery, state: FSMContext, side: ExecutionSide) -> None:
        await callback.answer()
        await state.clear()
        await state.update_data(execution_side=side.value)
        await state.set_state(HarnessStates.execution_price)
        if callback.message:
            await callback.message.answer(f"Execution Lab — {side.value}\nВведите цену")

    @router.callback_query(F.data == "lab:buy")
    async def handle_lab_buy(callback: CallbackQuery, state: FSMContext) -> None:
        await begin_execution(callback, state, ExecutionSide.BUY)

    @router.callback_query(F.data == "lab:sell")
    async def handle_lab_sell(callback: CallbackQuery, state: FSMContext) -> None:
        await begin_execution(callback, state, ExecutionSide.SELL)

    @router.callback_query(F.data == "lab:show")
    async def handle_lab_show(callback: CallbackQuery) -> None:
        await callback.answer()
        aggregate = execution_lab.aggregate()
        if callback.message:
            await callback.message.edit_text(
                format_aggregate(aggregate) if aggregate is not None else "Исполнений пока нет.",
                reply_markup=execution_lab_keyboard(),
            )

    @router.callback_query(F.data == "lab:reset")
    async def handle_lab_reset(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        execution_lab.reset()
        if callback.message:
            await callback.message.edit_text(
                "Execution Lab сброшен.\n\nИнструмент: TEST\nВалюта комиссии: USDT",
                reply_markup=execution_lab_keyboard(),
            )

    @router.message(HarnessStates.execution_price)
    async def handle_lab_price(message: Message, state: FSMContext) -> None:
        try:
            price = Price((message.text or "").strip())
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректная цена исполнения.\n{error}")
            return
        await state.update_data(execution_price=price)
        await state.set_state(HarnessStates.execution_quantity)
        await message.answer("Введите количество исполнения")

    @router.message(HarnessStates.execution_quantity)
    async def handle_lab_quantity(message: Message, state: FSMContext) -> None:
        try:
            quantity = Quantity((message.text or "").strip())
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректное количество исполнения.\n{error}")
            return
        await state.update_data(execution_quantity=quantity)
        await state.set_state(HarnessStates.execution_fee)
        await message.answer("Введите комиссию (USDT)")

    @router.message(HarnessStates.execution_fee)
    async def handle_lab_fee(message: Message, state: FSMContext) -> None:
        try:
            fee = Money((message.text or "").strip(), execution_lab.currency)
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректная комиссия исполнения.\n{error}")
            return
        await state.update_data(execution_fee=fee)
        await state.set_state(HarnessStates.execution_external_id)
        await message.answer("External execution ID (необязательно; для автогенерации отправьте —)")

    @router.message(HarnessStates.execution_external_id)
    async def handle_lab_external_id(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        external_id_text = (message.text or "").strip()
        external_id = None if external_id_text in {"", "-", "—", "skip", "SKIP"} else external_id_text
        try:
            fact = execution_lab.make_fact(
                ExecutionSide(data["execution_side"]),
                data["execution_price"],
                data["execution_quantity"],
                data["execution_fee"],
                external_id,
            )
            execution, aggregate, duplicate = execution_lab.apply_fact(fact)
        except (TypeError, ValueError, ArithmeticError) as error:
            await state.clear()
            await message.answer(f"❌ Исполнение отклонено.\n{error}", reply_markup=execution_lab_keyboard())
            return

        await state.clear()
        logger.info(
            "Execution Lab: side=%s quantity=%s external_execution_id=%s duplicate=%s",
            execution.side,
            execution.quantity.value,
            execution.external_execution_id,
            duplicate,
        )
        await message.answer(
            format_execution_lab_result(execution, aggregate, duplicate=duplicate),
            reply_markup=execution_lab_keyboard(),
        )

    @router.callback_query(F.data == "menu")
    async def handle_menu(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        if callback.message:
            await callback.message.edit_text(start_text(), reply_markup=menu_keyboard(dev_mode=dev_mode))

    @router.callback_query(F.data == "new_trade")
    async def handle_new_trade(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        await state.clear()
        if callback.message:
            await callback.message.edit_text("Выберите направление новой сделки", reply_markup=direction_keyboard())

    async def begin_open(callback: CallbackQuery, state: FSMContext, direction: TradeDirection) -> None:
        await callback.answer()
        await state.clear()
        await state.update_data(direction=direction.value)
        await state.set_state(HarnessStates.instrument)
        if callback.message:
            await callback.message.answer("Введите символ инструмента")

    @router.callback_query(F.data == "open:LONG")
    async def handle_open_long(callback: CallbackQuery, state: FSMContext) -> None:
        await begin_open(callback, state, TradeDirection.LONG)

    @router.callback_query(F.data == "open:SHORT")
    async def handle_open_short(callback: CallbackQuery, state: FSMContext) -> None:
        await begin_open(callback, state, TradeDirection.SHORT)

    @router.message(HarnessStates.instrument)
    async def handle_instrument(message: Message, state: FSMContext) -> None:
        symbol = (message.text or "").strip().upper()
        if not symbol:
            await message.answer("❌ Символ инструмента не может быть пустым.")
            return
        await state.update_data(instrument_symbol=symbol)
        await state.set_state(HarnessStates.entry_price)
        await message.answer("Введите цену входа")

    @router.message(HarnessStates.entry_price)
    async def handle_entry_price(message: Message, state: FSMContext) -> None:
        try:
            entry_price = Price((message.text or "").strip())
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректная цена входа.\n{error}")
            return
        await state.update_data(entry_price=entry_price)
        await state.set_state(HarnessStates.quantity)
        await message.answer("Введите количество")

    @router.message(HarnessStates.quantity)
    async def handle_quantity(message: Message, state: FSMContext) -> None:
        try:
            quantity = Quantity((message.text or "").strip())
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректное количество.\n{error}")
            return
        await state.update_data(quantity=quantity)
        await state.set_state(HarnessStates.currency)
        await message.answer("Введите валюту")

    @router.message(HarnessStates.currency)
    async def handle_currency(message: Message, state: FSMContext) -> None:
        currency = (message.text or "").strip().upper()
        try:
            Money(0, currency)
        except (TypeError, ValueError) as error:
            await message.answer(f"❌ Некорректная валюта.\n{error}")
            return
        await state.update_data(currency=currency)
        await state.set_state(HarnessStates.stop_price)
        await message.answer("Введите цену стоп-лосса (необязательно; для пропуска отправьте —)")

    @router.message(HarnessStates.stop_price)
    async def handle_stop_price(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip()
        if text in {"", "-", "skip", "SKIP"}:
            stop_price = None
        else:
            try:
                stop_price = Price(text)
            except (TypeError, ValueError) as error:
                await message.answer(f"❌ Некорректная цена стоп-лосса.\n{error}")
                return
        await state.update_data(stop_price=stop_price)
        await state.set_state(HarnessStates.risk_money)
        await message.answer("Введите денежный риск (необязательно; для пропуска отправьте —)")

    @router.message(HarnessStates.risk_money)
    async def handle_risk_money(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        text = (message.text or "").strip()
        if text in {"", "-", "skip", "SKIP"}:
            risk = None
        else:
            try:
                risk = Risk(Money(text, data["currency"]))
            except (TypeError, ValueError) as error:
                await message.answer(f"❌ Некорректный риск.\n{error}")
                return

        try:
            trade = Trade.open(
                DEMO_ACCOUNT_ID,
                InstrumentId.generate(),
                TradeDirection(data["direction"]),
                data["entry_price"],
                data["quantity"],
                datetime.now(timezone.utc),
                data["currency"],
                stop_price=data["stop_price"],
                risk=risk,
            )
        except (TypeError, ValueError) as error:
            logger.exception("Ошибка домена при открытии сделки")
            await message.answer(f"❌ Сделка не создана.\n{error}")
            return

        store.add(trade, data["instrument_symbol"])
        await state.clear()
        logger.info("Сделка открыта: trade_id=%s", trade.trade_id)
        await message.answer(
            format_trade(trade, data["instrument_symbol"]),
            reply_markup=trade_detail_keyboard(trade),
        )

    @router.callback_query(F.data == "open_trades")
    async def handle_open_trades(callback: CallbackQuery) -> None:
        await callback.answer()
        if callback.message:
            open_trades = store.open()
            await callback.message.edit_text(
                "📂 Открытые сделки\n\n" + format_trade_list((trade, store.symbol_for(trade)) for trade in open_trades),
                reply_markup=trades_keyboard(store, open_trades),
            )

    @router.callback_query(F.data == "trades")
    async def handle_trades(callback: CallbackQuery) -> None:
        await callback.answer()
        items = [(trade, store.symbol_for(trade)) for trade in store.all()]
        if callback.message:
            await callback.message.edit_text(
                "📚 Все сделки\n\n" + format_trade_list(items), reply_markup=trades_keyboard(store)
            )

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("trade:")))
    async def handle_trade_selection(callback: CallbackQuery) -> None:
        await callback.answer()
        trade = store.get_by_string(callback.data.split(":", 1)[1])
        if trade is None:
            await callback.answer("Сделка не найдена.", show_alert=True)
            return
        if callback.message:
            await callback.message.edit_text(
                format_trade(trade, store.symbol_for(trade)), reply_markup=trade_detail_keyboard(trade)
            )

    def selected_trade(callback: CallbackQuery) -> Trade | None:
        if not callback.data:
            return None
        trade_id = callback.data.split(":")[-1]
        trade = store.get_by_string(trade_id)
        return trade

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("fee:")))
    async def handle_add_fee_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        trade = selected_trade(callback)
        if trade is None:
            await callback.answer("Сделка не найдена.", show_alert=True)
            return
        await state.clear()
        await state.update_data(selected_trade_id=str(trade.trade_id))
        await state.set_state(HarnessStates.fee)
        if callback.message:
            await callback.message.answer(f"Введите комиссию ({trade.fees.currency})")

    @router.message(HarnessStates.fee)
    async def handle_add_fee(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        trade = store.get_by_string(data.get("selected_trade_id", ""))
        if trade is None:
            await state.clear()
            await message.answer("❌ Сделка не найдена.", reply_markup=menu_keyboard(dev_mode=dev_mode))
            return
        try:
            fee = Money((message.text or "").strip(), trade.fees.currency)
            trade.add_fee(fee)
        except (TypeError, ValueError, ArithmeticError) as error:
            await message.answer(f"❌ Комиссия отклонена.\n{error}")
            return
        await state.clear()
        logger.info("Комиссия добавлена: trade_id=%s", trade.trade_id)
        await message.answer(format_trade(trade, store.symbol_for(trade)), reply_markup=trade_detail_keyboard(trade))

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("expense:")))
    async def handle_add_expense_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        trade = selected_trade(callback)
        if trade is None:
            await callback.answer("Сделка не найдена.", show_alert=True)
            return
        sign = callback.data.split(":", 2)[1]
        await state.clear()
        await state.update_data(expense_sign=sign)
        await state.update_data(selected_trade_id=str(trade.trade_id))
        await state.set_state(HarnessStates.expense)
        if callback.message:
            await callback.message.answer(
                f"Введите сумму {'положительного' if sign == '+' else 'отрицательного'} расхода "
                f"({trade.fees.currency})"
            )

    @router.message(HarnessStates.expense)
    async def handle_add_expense(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        trade = store.get_by_string(data.get("selected_trade_id", ""))
        if trade is None:
            await state.clear()
            await message.answer("❌ Сделка не найдена.", reply_markup=menu_keyboard(dev_mode=dev_mode))
            return
        try:
            amount = Money((message.text or "").strip(), trade.fees.currency)
            if amount.amount < 0:
                raise ValueError("enter a non-negative amount")
            if data["expense_sign"] == "-":
                amount = Money(-amount.amount, amount.currency)
            trade.add_expense(Expense(amount))
        except (TypeError, ValueError, ArithmeticError) as error:
            await message.answer(f"❌ Расход отклонён.\n{error}")
            return
        await state.clear()
        logger.info("Расход добавлен: trade_id=%s", trade.trade_id)
        await message.answer(format_trade(trade, store.symbol_for(trade)), reply_markup=trade_detail_keyboard(trade))

    @router.callback_query(lambda callback: bool(callback.data and callback.data.startswith("close:")))
    async def handle_close_start(callback: CallbackQuery, state: FSMContext) -> None:
        await callback.answer()
        trade = selected_trade(callback)
        if trade is None:
            await callback.answer("Сделка не найдена.", show_alert=True)
            return
        await state.clear()
        await state.update_data(selected_trade_id=str(trade.trade_id))
        await state.set_state(HarnessStates.exit_price)
        if callback.message:
            await callback.message.answer("Введите цену выхода")

    @router.message(HarnessStates.exit_price)
    async def handle_close(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        trade = store.get_by_string(data.get("selected_trade_id", ""))
        if trade is None:
            await state.clear()
            await message.answer("❌ Сделка не найдена.", reply_markup=menu_keyboard(dev_mode=dev_mode))
            return
        try:
            exit_price = Price((message.text or "").strip())
            trade.close(exit_price, datetime.now(timezone.utc))
        except (TypeError, ValueError, ArithmeticError) as error:
            await message.answer(f"❌ Сделку нельзя закрыть.\n{error}")
            return
        await state.clear()
        logger.info("Сделка закрыта: trade_id=%s", trade.trade_id)
        await message.answer(format_trade(trade, store.symbol_for(trade)), reply_markup=trade_detail_keyboard(trade))

    return router
