"""Persistence port for per-account Attention reminder settings."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.monitoring import ReminderSettings


@runtime_checkable
class ReminderSettingsRepository(Protocol):
    async def get(self, account_id: AccountId) -> ReminderSettings | None:
        ...

    async def save(self, settings: ReminderSettings) -> None:
        ...
