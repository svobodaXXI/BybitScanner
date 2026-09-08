"""Read port for the explicit human-readable Instrument catalog."""

from typing import Protocol, runtime_checkable

from app.core.instruments.instrument import Instrument
from app.core.instruments.instrument_id import InstrumentId


@runtime_checkable
class InstrumentRepository(Protocol):
    async def search(self, query: str, *, limit: int = 20) -> tuple[Instrument, ...]:
        """Search active catalog entries by human-readable fields."""
        ...

    async def get_by_id(self, instrument_id: InstrumentId) -> Instrument | None:
        """Return catalog metadata, including inactive historical entries."""
        ...

    async def get_by_exchange_symbol(
        self,
        exchange: str,
        symbol: str,
        *,
        active_only: bool = True,
    ) -> tuple[Instrument, ...]:
        """Return exact exchange/symbol matches so ambiguity is observable."""
        ...
