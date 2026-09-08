"""Port for account/exchange-scoped import settings."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.imports import ExchangeImportSettings


@runtime_checkable
class ExchangeImportSettingsRepository(Protocol):
    async def get(self, *, account_id: AccountId, exchange: str) -> ExchangeImportSettings | None:
        ...

    async def save(self, settings: ExchangeImportSettings) -> None:
        ...
