"""Domain/ORM conversion for reminder settings."""

from datetime import datetime, timezone, timedelta

from app.core.monitoring import ReminderSettings
from app.infrastructure.persistence.models.reminder_settings import ReminderSettingsORM


def reminder_settings_to_orm(settings: ReminderSettings) -> ReminderSettingsORM:
    if settings.account_id is None:
        raise ValueError("persisted ReminderSettings require account_id")
    return ReminderSettingsORM(
        account_id=settings.account_id.value,
        incomplete_delay_seconds=int(settings.incomplete_reminder_delay.total_seconds()),
        open_threshold_seconds=int(settings.open_trade_reminder_threshold.total_seconds()),
        daily_digest_enabled=settings.daily_attention_digest_enabled,
        daily_digest_time=settings.daily_attention_digest_time.replace(tzinfo=None),
        timezone_name=settings.timezone_name,
        last_reminder_local_date=settings.last_reminder_local_date,
        updated_at=datetime.now(timezone.utc),
    )


def reminder_settings_from_orm(model: ReminderSettingsORM) -> ReminderSettings:
    from app.core.accounts.account_id import AccountId

    return ReminderSettings(
        account_id=AccountId(model.account_id),
        incomplete_reminder_delay=timedelta(seconds=model.incomplete_delay_seconds),
        open_trade_reminder_threshold=timedelta(seconds=model.open_threshold_seconds),
        daily_attention_digest_enabled=model.daily_digest_enabled,
        daily_attention_digest_time=model.daily_digest_time,
        timezone_name=model.timezone_name,
        last_reminder_local_date=model.last_reminder_local_date,
    )
