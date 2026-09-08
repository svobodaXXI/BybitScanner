"""Port for reversible Journal inclusion state."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.imports import JournalTradeState, JournalTradeStateRecord
from app.core.trades.trade_id import TradeId


@runtime_checkable
class TradeJournalStateRepository(Protocol):
    async def get(self, trade_id: TradeId) -> JournalTradeStateRecord | None:
        ...

    async def save(self, state: JournalTradeStateRecord) -> None:
        ...

    async def list(self, *, account_id: AccountId, state: JournalTradeState | None = None, limit: int = 100, offset: int = 0) -> tuple[JournalTradeStateRecord, ...]:
        ...

    async def count(self, *, account_id: AccountId, state: JournalTradeState | None = None) -> int:
        ...
