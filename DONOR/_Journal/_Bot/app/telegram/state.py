"""FSM states for one Telegram user's current interaction."""

from aiogram.fsm.state import State, StatesGroup


class JournalStates(StatesGroup):
    account_selection = State()
    instrument_query = State()
    instrument_selection = State()
    entry_price = State()
    quantity = State()
    stop_price = State()
    take_profit = State()
    edit_stop_price = State()
    edit_take_profit = State()
    fee = State()
    expense = State()
    exit_price = State()
    enrichment_value = State()
    history_custom_start = State()
    history_custom_end = State()
    bulk_custom_date = State()
    field_create_name = State()
    field_create_type = State()
    field_option_name = State()
    reminder_time = State()
