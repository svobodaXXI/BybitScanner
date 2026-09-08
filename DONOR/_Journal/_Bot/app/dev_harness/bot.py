"""Launch the Phase 1 Telegram development harness."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from .config import load_settings
from .formatting import start_text
from .handlers import AuthorizationMiddleware, create_router
from .keyboards import main_menu_keyboard
from .state import InMemoryTradeStore


def create_dispatcher(store: InMemoryTradeStore | None = None, *, dev_mode: bool = False) -> Dispatcher:
    store = store or InMemoryTradeStore()
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(store, dev_mode=dev_mode))
    return dispatcher


def startup_notification_text() -> str:
    return (
        "✅ Торговый журнал — тестовый контур запущен\n\n"
        "Этап 1.5: Telegram-тестирование ядра сделок\n"
        "Режим: РАЗРАБОТКА\n"
        "Хранилище: ПАМЯТЬ\n"
        "Область: одна точка входа + полное закрытие"
    )


async def notify_startup(bot: Bot, allowed_user_id: int | None, *, dev_mode: bool = False) -> None:
    """Notify the configured owner without exposing credentials or other users."""
    if allowed_user_id is None:
        logging.getLogger(__name__).warning("STARTUP_NOTIFICATION_SKIPPED: user ID is not configured")
        return
    await bot.send_message(
        allowed_user_id,
        startup_notification_text(),
        reply_markup=main_menu_keyboard(dev_mode=dev_mode),
    )


async def main() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required; copy .env.example to .env and fill it")

    dispatcher = create_dispatcher(dev_mode=settings.dev_mode)
    authorization = AuthorizationMiddleware(settings.allowed_user_id)
    dispatcher.message.outer_middleware(authorization)
    dispatcher.callback_query.outer_middleware(authorization)

    bot = Bot(settings.telegram_bot_token)
    logging.getLogger(__name__).info("BOT_STARTED")
    try:
        await notify_startup(bot, settings.allowed_user_id, dev_mode=settings.dev_mode)
        try:
            await dispatcher.start_polling(bot)
        except asyncio.CancelledError:
            logging.getLogger(__name__).info("BOT_STOPPED")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("BOT_STOPPED")
