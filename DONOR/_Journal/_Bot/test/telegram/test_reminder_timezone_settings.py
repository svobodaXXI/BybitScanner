import asyncio
from datetime import date, time

from aiogram.types import CallbackQuery

from app.core.accounts.account_id import AccountId
from app.core.monitoring import ReminderSettings
from app.telegram.config import TelegramSettings
from app.telegram.handlers import create_router


ACCOUNT = AccountId.generate()


class _Message:
    def __init__(self):
        self.edited = None

    async def edit_text(self, text, reply_markup=None):
        self.edited = (text, reply_markup)


class _InputMessage:
    def __init__(self, text):
        self.text = text
        self.answers = []

    async def answer(self, text, reply_markup=None):
        self.answers.append((text, reply_markup))


class _State:
    async def clear(self):
        pass


class _Callback(CallbackQuery):
    @classmethod
    def make(cls, data):
        callback = cls.model_construct()
        object.__setattr__(callback, "data", data)
        object.__setattr__(callback, "message", _Message())
        object.__setattr__(callback, "answers", [])
        return callback

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))


class _Runtime:
    def __init__(self):
        self.reminder = ReminderSettings(
            account_id=ACCOUNT,
            daily_attention_digest_time=time(3),
            timezone_name="UTC",
            last_reminder_local_date=date(2026, 9, 7),
        )
        self.saved = []

    async def get_reminder_settings(self, account_id):
        assert account_id == ACCOUNT
        return self.reminder

    async def save_reminder_settings(self, reminder):
        self.reminder = reminder
        self.saved.append(reminder)


def _handler(router, name):
    return next(item.callback for item in router.callback_query.handlers if item.callback.__name__ == name)


def _message_handler(router, name):
    return next(item.callback for item in router.message.handlers if item.callback.__name__ == name)


def test_reminder_settings_shows_timezone_and_timezone_picker_persists_canonical_id():
    runtime = _Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", ACCOUNT))
    state = object()

    screen = _Callback.make("settings_reminders")
    asyncio.run(_handler(router, "handle_settings_reminders")(screen, state))
    assert "Часовой пояс: UTC" in screen.message.edited[0]
    screen_buttons = [button for row in screen.message.edited[1].inline_keyboard for button in row]
    assert "reminder:timezone" in [button.callback_data for button in screen_buttons]

    picker = _Callback.make("reminder:timezone")
    asyncio.run(_handler(router, "handle_reminder_timezone_start")(picker, state))
    picker_buttons = [button for row in picker.message.edited[1].inline_keyboard for button in row]
    moscow = next(button for button in picker_buttons if button.text == "Москва (UTC+3)")

    selected = _Callback.make(moscow.callback_data)
    asyncio.run(_handler(router, "handle_reminder_timezone")(selected, state))

    assert runtime.reminder.timezone_name == "Europe/Moscow"
    assert runtime.reminder.last_reminder_local_date == date(2026, 9, 7)
    assert "Часовой пояс: Москва (UTC+3)" in selected.message.edited[0]
    assert selected.answers


def test_time_change_preserves_delivery_date():
    runtime = _Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", ACCOUNT))

    message = _InputMessage("04:15")
    asyncio.run(_message_handler(router, "handle_reminder_time")(message, _State()))

    assert runtime.reminder.daily_attention_digest_time == time(4, 15)
    assert runtime.reminder.last_reminder_local_date == date(2026, 9, 7)


def test_toggle_preserves_delivery_date_and_does_not_fabricate_one():
    runtime = _Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", ACCOUNT))
    callback = _Callback.make("reminder:toggle")

    asyncio.run(_handler(router, "handle_reminder_toggle")(callback, _State()))

    assert runtime.reminder.daily_attention_digest_enabled is False
    assert runtime.reminder.last_reminder_local_date == date(2026, 9, 7)


def test_invalid_timezone_callback_is_rejected_without_persistence():
    runtime = _Runtime()
    router = create_router(runtime, TelegramSettings("token", 1, "db", ACCOUNT))
    selected = _Callback.make("reminder:timezone:Not/A_Timezone")

    asyncio.run(_handler(router, "handle_reminder_timezone")(selected, object()))

    assert runtime.saved == []
    assert selected.answers[0][1]["show_alert"] is True
