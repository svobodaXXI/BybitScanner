"""Production Telegram startup and dispatcher composition."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import replace
from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher

from .composition import JournalApplication, create_runtime
from .config import TelegramSettings, load_settings
from .handlers import AuthorizationMiddleware, create_router
from .keyboards import main_menu_keyboard, new_trade_notification_keyboard
from .formatting import new_trade_notification_text
from .viewer_access import TelegramViewerAuthorizationMiddleware
from app.application.dtos import GetTradeDetailsCommand
from app.core.trades.enums import TradeStatus
from app.core.monitoring import AttentionReminderPolicy
from app.core.monitoring.reminders import _zone
from app.infrastructure.persistence.telegram_access import TelegramAccessStore
from .formatting import incomplete_reminder_text
from .keyboards import incomplete_reminder_keyboard

logger = logging.getLogger(__name__)
REMINDER_CHECK_INTERVAL_SECONDS = 60.0


class BotSingletonLock:
    """Best-effort local process lock to prevent Telegram polling conflicts."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        self._handle.seek(0)
        self._handle.write("0")
        self._handle.flush()
        try:
            if os.name == "nt":
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError):
            self._handle.close()
            self._handle = None
            return False
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def _safe_sync_error(error: Exception) -> str:
    message = " ".join(str(error).split())
    if re.search(r"(?i)(api[_ -]?key|api[_ -]?secret|authorization|signature|sign)", message):
        return "error details redacted"
    return message[:300] or type(error).__name__


async def notify_new_trades(bot: Bot | None, runtime: JournalApplication, settings: TelegramSettings, summary) -> None:
    """Notify the owner after persistence; notification failure is non-fatal."""
    trade_ids = tuple(dict.fromkeys(getattr(summary, "created_trade_ids", ())))
    if bot is None or not trade_ids:
        return
    if settings.allowed_user_id is None:
        logger.warning("BYBIT_NEW_TRADE_NOTIFICATION_SKIPPED reason=user_id_not_configured count=%s", len(trade_ids))
        return
    for trade_id in trade_ids:
        try:
            details = await runtime.get_trade_details(GetTradeDetailsCommand(trade_id))
            if details.trade.status is not TradeStatus.OPEN:
                logger.info("BYBIT_NEW_TRADE_NOTIFICATION_SKIPPED trade_id=%s reason=not_open", trade_id)
                continue
            await bot.send_message(
                settings.allowed_user_id,
                new_trade_notification_text(
                    details.trade,
                    details.instrument,
                    timezone_name=settings.reminder_settings.timezone_name,
                ),
                reply_markup=new_trade_notification_keyboard(str(details.trade.trade_id)),
            )
            logger.info("BYBIT_NEW_TRADE_NOTIFICATION_SENT trade_id=%s", trade_id)
        except Exception as error:  # persistence is already committed; keep sync alive
            logger.error(
                "BYBIT_NEW_TRADE_NOTIFICATION_FAILED trade_id=%s error_type=%s detail=%s",
                trade_id, type(error).__name__, _safe_sync_error(error),
            )


async def run_daily_reminder_check(
    bot: Bot | None,
    runtime: JournalApplication,
    settings: TelegramSettings,
    *,
    now: datetime | None = None,
) -> bool:
    """Deliver at most one CLOSED+INCOMPLETE digest for the local day."""
    account_id = settings.journal_account_id
    if account_id is None:
        logger.info("REMINDER_SKIPPED reason=account_not_configured")
        return False
    try:
        persisted = await runtime.get_reminder_settings(account_id)
        reminder = persisted or replace(settings.reminder_settings, account_id=account_id)
        if not reminder.daily_attention_digest_enabled:
            logger.info("REMINDER_SKIPPED reason=disabled")
            return False

        count_provider = getattr(runtime, "incomplete_attention_count", None)
        if count_provider is not None:
            incomplete = int(await count_provider(account_id=account_id))
        else:
            attention = await runtime.attention(account_id=account_id)
            incomplete = int(attention.summary.incomplete_count)

        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        local = current.astimezone(_zone(reminder.timezone_name))
        due = AttentionReminderPolicy.due_for_daily_digest(
            current,
            reminder,
            last_sent_local_date=reminder.last_reminder_local_date,
        )
        logger.debug("REMINDER_CHECK incomplete=%s due=%s", incomplete, str(due).lower())
        if not due:
            reason = "already_sent" if reminder.last_reminder_local_date == local.date() else "not_due"
            logger.debug("REMINDER_SKIPPED reason=%s", reason)
            return False
        if incomplete <= 0:
            logger.info("REMINDER_SKIPPED reason=no_incomplete")
            return False
        if bot is None or settings.allowed_user_id is None:
            logger.warning("REMINDER_SKIPPED reason=user_not_configured")
            return False

        try:
            await bot.send_message(
                settings.allowed_user_id,
                incomplete_reminder_text(incomplete),
                reply_markup=incomplete_reminder_keyboard(),
            )
        except Exception as error:
            logger.error(
                "REMINDER_SEND_FAILED error_type=%s detail=%s",
                type(error).__name__, _safe_sync_error(error),
            )
            return False

        try:
            await runtime.save_reminder_settings(replace(
                reminder,
                account_id=account_id,
                last_reminder_local_date=local.date(),
            ))
        except Exception as error:
            logger.error(
                "REMINDER_STATE_PERSIST_FAILED delivery_sent=true durable_state=false "
                "error_type=%s detail=%s",
                type(error).__name__, _safe_sync_error(error),
            )
            return False
        logger.info("REMINDER_SENT incomplete=%s", incomplete)
        return True
    except Exception as error:
        logger.error(
            "REMINDER_CHECK_FAILED error_type=%s detail=%s",
            type(error).__name__, _safe_sync_error(error),
        )
        return False


async def reminder_loop(runtime: JournalApplication, settings: TelegramSettings, bot: Bot) -> None:
    logger.info("REMINDER_WORKER_STARTED")
    try:
        while True:
            await run_daily_reminder_check(bot, runtime, settings)
            await asyncio.sleep(REMINDER_CHECK_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        raise
    finally:
        logger.info("REMINDER_WORKER_STOPPED")


async def run_bybit_incremental_sync(
    runtime: JournalApplication,
    settings: TelegramSettings,
    *,
    phase: str,
    bot: Bot | None = None,
):
    if not settings.bybit_auto_sync_enabled:
        logger.info("BYBIT_SYNC_DISABLED reason=config phase=%s", phase)
        return None
    if phase == "startup":
        logger.info("BYBIT_STARTUP_SYNC phase=%s", phase)
    else:
        logger.info("BYBIT_SYNC_TICK phase=%s", phase)
    try:
        summary = await runtime.sync_bybit_incremental(
            overlap_seconds=settings.bybit_sync_overlap_seconds,
            )
        await notify_new_trades(bot, runtime, settings, summary)
        return summary
    except ValueError as error:
        logger.warning("BYBIT_SYNC_DISABLED reason=not_configured phase=%s detail=%s", phase, _safe_sync_error(error))
    except Exception as error:
        logger.error(
            "BYBIT_SYNC_ERRORS count=1 phase=%s error_type=%s detail=%s",
            phase, type(error).__name__, _safe_sync_error(error),
            )
    return None


async def bybit_sync_loop(runtime: JournalApplication, settings: TelegramSettings, bot: Bot | None = None) -> None:
    while True:
        await asyncio.sleep(settings.bybit_sync_interval_seconds)
        await run_bybit_incremental_sync(runtime, settings, phase="interval", bot=bot)


def create_dispatcher(
    runtime: JournalApplication,
    settings: TelegramSettings,
    access_store: TelegramAccessStore | None = None,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(create_router(runtime, settings))
    if access_store is None:
        authorization = AuthorizationMiddleware(settings.allowed_user_id)
    else:
        authorization = TelegramViewerAuthorizationMiddleware(settings, access_store)
    dispatcher.message.outer_middleware(authorization)
    dispatcher.callback_query.outer_middleware(authorization)
    return dispatcher


def startup_notification_text() -> str:
    return "✅ Торговый журнал запущен\n\nДанные читаются из PostgreSQL."


async def notify_startup(bot: Bot, settings: TelegramSettings) -> None:
    if settings.allowed_user_id is None:
        logger.warning("STARTUP_NOTIFICATION_SKIPPED: user ID is not configured")
        return
    await bot.send_message(
        settings.allowed_user_id,
        startup_notification_text(),
        reply_markup=main_menu_keyboard(dev_mode=settings.dev_mode, webapp_url=settings.webapp_url),
    )


async def main() -> None:
    settings = load_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")
    if settings.journal_account_id is None:
        raise RuntimeError("JOURNAL_ACCOUNT_ID is required")

    lock = BotSingletonLock(Path(__file__).resolve().parents[2] / "runtime_logs" / "telegram_bot.lock")
    if not lock.acquire():
        logger.error("BOT_ALREADY_RUNNING")
        raise SystemExit(2)

    engine, runtime = create_runtime(
        settings.database_url,
        settings.journal_account_id,
        entry_timezone=ZoneInfo(settings.reminder_settings.timezone_name),
    )
    access_store = TelegramAccessStore.from_engine(engine)
    dispatcher = create_dispatcher(runtime, settings, access_store)
    bot = Bot(settings.telegram_bot_token)
    logger.info("BOT_STARTED")
    sync_task = None
    reminder_task = None
    try:
        await runtime.bootstrap_statistical_fields()
        await run_bybit_incremental_sync(runtime, settings, phase="startup", bot=bot)
        await run_daily_reminder_check(bot, runtime, settings)
        if settings.bybit_auto_sync_enabled:
            sync_task = asyncio.create_task(bybit_sync_loop(runtime, settings, bot), name="bybit-incremental-sync")
        reminder_task = asyncio.create_task(reminder_loop(runtime, settings, bot), name="telegram-reminder-worker")
        await notify_startup(bot, settings)
        await dispatcher.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("BOT_STOPPED")
    finally:
        if sync_task is not None:
            sync_task.cancel()
            with suppress(asyncio.CancelledError):
                await sync_task
        if reminder_task is not None:
            reminder_task.cancel()
            with suppress(asyncio.CancelledError):
                await reminder_task
        await bot.session.close()
        await engine.dispose()
        lock.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("BOT_STOPPED")
