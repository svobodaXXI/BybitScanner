from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.application.statistics.metric_registry import StatisticsLayout


@runtime_checkable
class StatisticsLayoutRepository(Protocol):
    async def get(self, account_id: AccountId) -> StatisticsLayout | None: ...
    async def save(self, account_id: AccountId, layout: StatisticsLayout) -> None: ...
