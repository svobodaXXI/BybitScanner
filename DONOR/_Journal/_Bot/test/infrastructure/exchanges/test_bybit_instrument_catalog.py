import asyncio

from app.core.accounts.account_id import AccountId
from app.infrastructure.exchanges.bybit import (
    BybitInstrumentCatalogSource,
    BybitInstrumentCatalogSync,
    BybitSettings,
    stable_bybit_instrument_id,
)


class PublicClientFake:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    async def get_public(self, path, params):
        self.calls.append((path, dict(params)))
        return self.responses.pop(0)

    async def get(self, path, params):
        raise AssertionError("catalog must use the public client method")


def settings(**changes):
    values = dict(api_key="unused", api_secret="unused", account_id=AccountId.generate(), max_retries=0)
    values.update(changes)
    return BybitSettings(**values)


def catalog_item(symbol, status="Trading"):
    return {
        "symbol": symbol,
        "status": status,
        "baseCoin": symbol[:-4],
        "quoteCoin": "USDT",
    }


def page(items, cursor=None):
    return {"retCode": 0, "result": {"list": items, "nextPageCursor": cursor}}


def test_catalog_source_paginates_public_endpoint_and_builds_stable_ids():
    client = PublicClientFake(page([catalog_item("BTCUSDT")], "cursor-2"), page([catalog_item("ETHUSDT", "PreLaunch"), catalog_item("OLDUSDT", "Settled")]))
    source = BybitInstrumentCatalogSource(settings(page_limit=2), client)
    result = asyncio.run(source.fetch_instruments())
    assert [item.symbol for item in result.instruments] == ["BTCUSDT", "ETHUSDT", "OLDUSDT"]
    assert result.instruments[0].instrument_id == stable_bybit_instrument_id("linear", "BTCUSDT")
    assert result.instruments[0].active is True
    assert result.instruments[2].active is False
    assert client.calls[0][0] == "/v5/market/instruments-info"
    assert client.calls[0][1] == {"category": "linear", "limit": "2"}
    assert client.calls[1][1]["cursor"] == "cursor-2"


class RepositoryFake:
    def __init__(self, session):
        self.saved = []
        self.deactivate_calls = []

    async def save(self, instrument):
        self.saved.append(instrument)

    async def deactivate_missing(self, exchange, market, active_symbols):
        self.deactivate_calls.append((exchange, market, tuple(active_symbols)))
        return 3


def test_catalog_sync_is_explicit_upsert_and_deactivate_without_delete():
    source = BybitInstrumentCatalogSource(
        settings(), PublicClientFake(page([catalog_item("BTCUSDT")]))
    )
    repository = None

    def factory(session):
        nonlocal repository
        repository = RepositoryFake(session)
        return repository

    summary = asyncio.run(BybitInstrumentCatalogSync(source, factory).execute(object()))
    assert summary.fetched == summary.upserted == 1
    assert summary.deactivated == 3
    assert repository.saved[0].symbol == "BTCUSDT"
    assert repository.deactivate_calls == [("BYBIT", "LINEAR", ("BTCUSDT",))]
