"""SQLAlchemy adapter for per-account reminder settings."""

from sqlalchemy import select

from app.application.ports.repositories import ReminderSettingsRepository
from app.core.accounts.account_id import AccountId

from ..mappers import reminder_settings_from_orm, reminder_settings_to_orm
from ..models.reminder_settings import ReminderSettingsORM
from ._common import require_session


class SqlAlchemyReminderSettingsRepository(ReminderSettingsRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def get(self, account_id: AccountId):
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        model = await self._session.scalar(
            select(ReminderSettingsORM).where(ReminderSettingsORM.account_id == account_id.value)
        )
        return None if model is None else reminder_settings_from_orm(model)

    async def save(self, settings):
        if settings.account_id is None:
            raise ValueError("persisted ReminderSettings require account_id")
        existing = await self._session.scalar(
            select(ReminderSettingsORM).where(ReminderSettingsORM.account_id == settings.account_id.value)
        )
        candidate = reminder_settings_to_orm(settings)
        if existing is None:
            self._session.add(candidate)
        else:
            for name in (
                "incomplete_delay_seconds", "open_threshold_seconds", "daily_digest_enabled",
                "daily_digest_time", "timezone_name", "last_reminder_local_date", "updated_at",
            ):
                setattr(existing, name, getattr(candidate, name))
        await self._session.flush()
