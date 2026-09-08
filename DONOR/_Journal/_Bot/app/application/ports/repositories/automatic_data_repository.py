"""Persistence ports for generic automatic data."""

from typing import Protocol, runtime_checkable

from app.core.automatic_data import AutomaticFactorObservation
from app.core.accounts.account_id import AccountId


@runtime_checkable
class AutomaticFactorObservationRepository(Protocol):
    async def save(self, observation: AutomaticFactorObservation) -> None: ...
    async def list_for_trade(self, trade_id) -> tuple[AutomaticFactorObservation, ...]: ...
    async def list(self, factor_id: str, trade_ids=()) -> tuple[AutomaticFactorObservation, ...]: ...


@runtime_checkable
class AutomaticFactorSettingsRepository(Protocol):
    async def list(self, account_id: AccountId) -> dict[str, bool]: ...
    async def set_enabled(self, account_id: AccountId, factor_id: str, enabled: bool) -> None: ...
