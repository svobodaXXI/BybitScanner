"""Search the explicit Instrument catalog for Telegram selection."""

from dataclasses import dataclass

from app.application.ports.repositories import InstrumentRepository
from app.core.instruments.instrument import Instrument


@dataclass(frozen=True, slots=True)
class SearchInstrumentsCommand:
    query: str
    limit: int = 20

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must not be empty")
        if type(self.limit) is not int or not 1 <= self.limit <= 50:
            raise ValueError("limit must be an integer between 1 and 50")


@dataclass(frozen=True, slots=True)
class SearchInstrumentsResult:
    instruments: tuple[Instrument, ...]


class SearchInstruments:
    def __init__(self, instrument_repository: InstrumentRepository) -> None:
        self._instruments = instrument_repository

    async def execute(self, command: SearchInstrumentsCommand) -> SearchInstrumentsResult:
        if not isinstance(command, SearchInstrumentsCommand):
            raise TypeError("command must be SearchInstrumentsCommand")
        result = await self._instruments.search(command.query, limit=command.limit)
        return SearchInstrumentsResult(tuple(result))
