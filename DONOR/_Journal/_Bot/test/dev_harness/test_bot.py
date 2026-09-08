import asyncio

from aiogram.types import InlineKeyboardMarkup

from app.dev_harness.bot import notify_startup, startup_notification_text


class FakeBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str, object | None]] = []

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        self.sent_messages.append((chat_id, text, kwargs.get("reply_markup")))


def test_startup_notification_is_sent_to_configured_owner() -> None:
    bot = FakeBot()

    asyncio.run(notify_startup(bot, 5247320057))

    assert bot.sent_messages[0][0:2] == (5247320057, startup_notification_text())
    assert isinstance(bot.sent_messages[0][2], InlineKeyboardMarkup)


def test_startup_notification_is_skipped_without_owner_id() -> None:
    bot = FakeBot()

    asyncio.run(notify_startup(bot, None))

    assert bot.sent_messages == []
