"""Repository port for current Journal Trade records."""

from typing import Protocol, runtime_checkable

from app.core.accounts.account_id import AccountId
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


@runtime_checkable
class TradeRepository(Protocol):
    """Async persistence contract for Trade; aggregate reconstruction is deferred."""

    async def get_by_id(self, trade_id: TradeId) -> Trade | None:
        """Return one trade or None."""
        ...

    async def save(self, trade: Trade) -> None:
        """Upsert the current representation identified by trade.trade_id."""
        ...

    async def list_open(
        self,
        *,
        account_id: AccountId | None = None,
        instrument_id: InstrumentId | None = None,
        include_excluded: bool = False,
    ) -> tuple[Trade, ...]:
        """Return OPEN trades in deterministic implementation-defined ID order."""
        ...

    async def list_all(
        self,
        *,
        account_id: AccountId | None = None,
        instrument_id: InstrumentId | None = None,
        limit: int = 100,
        offset: int = 0,
        include_excluded: bool = False,
    ) -> tuple[Trade, ...]:
        """Return OPEN and CLOSED trades in deterministic order, page-bounded."""
        ...
