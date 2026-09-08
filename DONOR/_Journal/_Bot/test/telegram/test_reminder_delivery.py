import asyncio
from contextlib import suppress
from datetime import date, time, timedelta, timezone, datetime

from app.core.accounts.account_id import AccountId
from app.core.monitoring import ReminderSettings
from app.telegram.bot import run_daily_reminder_check
from app.telegram.bot import reminder_loop
from app.telegram.config import TelegramSettings


ACCOUNT = AccountId.generate()
BASE = datetime(2026, 9, 7, 20, tzinfo=timezone.utc)


class BotFake:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.sent = []

    async def send_message(self, *args, **kwargs):
        if self.fail:
            raise RuntimeError("temporary Telegram failure")
        self.sent.append((args, kwargs))


class RuntimeFake:
    def __init__(self, *, count=1, reminder=None, fail_save=False):
        self.count = count
        self.fail_save = fail_save
        self.reminder = reminder or ReminderSettings(
            account_id=ACCOUNT,
            daily_attention_digest_time=time(20, 0),
            timezone_name="UTC",
        )
        self.saved = []

    async def get_reminder_settings(self, account_id):
        assert account_id == ACCOUNT
        return self.reminder

    async def incomplete_attention_count(self, *, account_id=None):
        assert account_id == ACCOUNT
        return self.count

    async def save_reminder_settings(self, reminder):
        if self.fail_save:
            raise RuntimeError("database unavailable")
        self.reminder = reminder
        self.saved.append(reminder)


def telegram_settings():
    return TelegramSettings("token", 123, "db", ACCOUNT)


def test_due_digest_sends_once_per_local_day_and_again_next_day():
    runtime = RuntimeFake()
    bot = BotFake()

    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE.replace(hour=19))) is False
    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is True
    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE.replace(minute=5))) is False
    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE + timedelta(days=1))) is True

    assert len(bot.sent) == 2
    assert runtime.reminder.last_reminder_local_date == date(2026, 9, 8)
    text, markup = bot.sent[0][0][1], bot.sent[0][1]["reply_markup"]
    assert "Требуют заполнения: 1" in text
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks == ["attention:closed", "attention"]
    assert all(len(item.encode("utf-8")) <= 64 for item in callbacks)


def test_no_incomplete_trades_produce_no_digest():
    runtime = RuntimeFake(count=0)
    bot = BotFake()

    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is False
    assert bot.sent == []
    assert runtime.saved == []


def test_disabled_digest_produces_no_message():
    runtime = RuntimeFake(reminder=ReminderSettings(
        account_id=ACCOUNT,
        daily_attention_digest_enabled=False,
        daily_attention_digest_time=time(20, 0),
        timezone_name="UTC",
    ))
    bot = BotFake()

    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is False
    assert bot.sent == []
    assert runtime.saved == []


def test_send_failure_does_not_mark_delivery_and_retry_can_send():
    runtime = RuntimeFake()
    bot = BotFake(fail=True)

    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is False
    assert runtime.saved == []
    bot.fail = False
    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is True
    assert len(bot.sent) == 1
    assert runtime.reminder.last_reminder_local_date == BASE.date()


def test_state_persist_failure_after_send_is_not_claimed_as_durable(caplog):
    caplog.set_level("ERROR")
    runtime = RuntimeFake(fail_save=True)
    bot = BotFake()

    assert asyncio.run(run_daily_reminder_check(bot, runtime, telegram_settings(), now=BASE)) is False
    assert len(bot.sent) == 1
    assert runtime.saved == []
    assert runtime.reminder.last_reminder_local_date is None
    assert "REMINDER_STATE_PERSIST_FAILED" in caplog.text
    assert "delivery_sent=true" in caplog.text
    assert "durable_state=false" in caplog.text


def test_reminder_worker_starts_and_shuts_down_cleanly(monkeypatch, caplog):
    caplog.set_level("INFO")
    runtime = RuntimeFake(count=0)
    bot = BotFake()
    monkeypatch.setattr("app.telegram.bot.REMINDER_CHECK_INTERVAL_SECONDS", 0.001)

    async def exercise():
        task = asyncio.create_task(reminder_loop(runtime, telegram_settings(), bot))
        await asyncio.sleep(0.01)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    asyncio.run(exercise())

    assert "REMINDER_WORKER_STARTED" in caplog.text
    assert "REMINDER_WORKER_STOPPED" in caplog.text
