import asyncio
import pytest

from app.application import SearchInstruments, SearchInstrumentsCommand
from app.core.instruments import Instrument, InstrumentId


class FakeInstrumentRepository:
    def __init__(self, items):
        self.items = tuple(items)
        self.calls = []

    async def search(self, query, *, limit=20):
        self.calls.append((query, limit))
        return self.items[:limit]

    async def get_by_id(self, instrument_id):
        return next((item for item in self.items if item.instrument_id == instrument_id), None)


def test_search_instruments_delegates_catalog_query_and_preserves_multiple_matches():
    items = (
        Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin / Tether"),
        Instrument(InstrumentId.generate(), "BTCUSD", "Bitcoin / Dollar"),
    )
    repository = FakeInstrumentRepository(items)
    result = asyncio.run(SearchInstruments(repository).execute(SearchInstrumentsCommand("btc")))
    assert result.instruments == items
    assert repository.calls == [("btc", 20)]


def test_search_instruments_allows_empty_catalog_for_retry():
    repository = FakeInstrumentRepository(())
    result = asyncio.run(SearchInstruments(repository).execute(SearchInstrumentsCommand("unknown")))
    assert result.instruments == ()


def test_search_instruments_rejects_blank_query():
    with pytest.raises(ValueError):
        SearchInstrumentsCommand("   ")
