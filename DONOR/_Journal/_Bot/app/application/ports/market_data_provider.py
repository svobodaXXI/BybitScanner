"""Application port for request-driven normalized market-data snapshots."""

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.application.market_data import MarketDataContext
from app.core.instruments.instrument_id import InstrumentId


@runtime_checkable
class MarketDataProvider(Protocol):
    """Fetch only the normalized values needed by the current enrichment."""

    async def get_trade_context(
        self,
        instrument_id: InstrumentId,
        at: datetime,
        *,
        required_keys: tuple[str, ...] = (),
    ) -> MarketDataContext:
        """Return a historical/request-time context for an existing instrument."""
        ...
