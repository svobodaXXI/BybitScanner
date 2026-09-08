import asyncio
from datetime import date, time, timedelta

from app.core.accounts.account_id import AccountId
from app.core.monitoring import ReminderSettings
from app.infrastructure.persistence.mappers import reminder_settings_from_orm, reminder_settings_to_orm
from app.infrastructure.persistence.repositories.reminder_settings_repository import SqlAlchemyReminderSettingsRepository


class _Session:
    def __init__(self, existing):
        self.existing = existing
        self.flushed = 0

    async def scalar(self, statement):
        return self.existing

    async def execute(self, statement):
        raise AssertionError("reminder repository should use scalar")

    async def flush(self):
        self.flushed += 1


def test_reminder_settings_round_trip_preserves_per_account_policy():
    settings = ReminderSettings(
        account_id=AccountId.generate(),
        incomplete_reminder_delay=timedelta(minutes=90),
        open_trade_reminder_threshold=timedelta(hours=36),
        daily_attention_digest_enabled=False,
        daily_attention_digest_time=time(21, 30),
        timezone_name="Europe/Moscow",
        last_reminder_local_date=date(2026, 9, 7),
    )
    restored = reminder_settings_from_orm(reminder_settings_to_orm(settings))
    assert restored == settings


def test_existing_settings_update_persists_last_delivery_date():
    account = AccountId.generate()
    old = ReminderSettings(account_id=account, timezone_name="UTC")
    existing = reminder_settings_to_orm(old)
    updated = ReminderSettings(
        account_id=account,
        timezone_name="Europe/Moscow",
        last_reminder_local_date=date(2026, 9, 7),
    )
    session = _Session(existing)

    asyncio.run(SqlAlchemyReminderSettingsRepository(session).save(updated))

    assert existing.timezone_name == "Europe/Moscow"
    assert existing.last_reminder_local_date == date(2026, 9, 7)
    assert session.flushed == 1
