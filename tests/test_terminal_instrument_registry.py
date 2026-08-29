from decimal import Decimal
import unittest

from terminal.market_data.instrument_registry import (
    InstrumentRegistry,
    InstrumentRegistryError,
)


def _instrument(symbol: str, **changes) -> dict:
    item = {
        "symbol": symbol,
        "contractType": "LinearPerpetual",
        "status": "Trading",
        "baseCoin": symbol.removesuffix("USDT"),
        "quoteCoin": "USDT",
        "settleCoin": "USDT",
        "priceFilter": {"minPrice": "0.0001", "maxPrice": "1000000", "tickSize": "0.0001"},
        "lotSizeFilter": {
            "minOrderQty": "0.1", "maxOrderQty": "100000",
            "maxMktOrderQty": "50000", "qtyStep": "0.1", "minNotionalValue": "5",
        },
    }
    item.update(changes)
    return item


class _Response:
    def __init__(self, payload: dict, *, fails: bool = False) -> None:
        self.payload = payload
        self.fails = fails

    def raise_for_status(self) -> None:
        if self.fails:
            raise OSError("upstream unavailable")

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, pages) -> None:
        self.pages = iter(pages)
        self.params = []

    def get(self, url, *, params, timeout):
        assert url.endswith("/v5/market/instruments-info")
        assert timeout == 10
        self.params.append(params)
        page = next(self.pages)
        if isinstance(page, BaseException):
            raise page
        return _Response(page)


def _page(items, cursor="") -> dict:
    return {"retCode": 0, "result": {"list": items, "nextPageCursor": cursor}}


def test_registry_paginates_filters_normalizes_and_looks_up_without_refetch():
    session = _Session([
        _page([
            _instrument("BTCUSDT"),
            _instrument("ETHUSDT", quoteCoin="USDC"),
            _instrument("OLDUSDT", status="Settled"),
            _instrument("FUTUREUSDT", contractType="LinearFutures"),
            {"symbol": "BROKENUSDT", "status": "Trading", "quoteCoin": "USDT", "contractType": "LinearPerpetual"},
        ], "page-2"),
        _page([_instrument("ONGUSDT", priceFilter={"minPrice": "0.0001", "maxPrice": "10", "tickSize": "0.00001"})]),
    ])
    registry = InstrumentRegistry(session)

    snapshot = registry.refresh()

    assert session.params == [
        {"category": "linear", "limit": 1000},
        {"category": "linear", "limit": 1000, "cursor": "page-2"},
    ]
    assert [item.symbol for item in snapshot.instruments] == ["BTCUSDT", "ONGUSDT"]
    assert registry.supports(" onGusdt ") is True
    assert registry.supports("ETHUSDT") is False
    assert registry.get("ongusdt").tick_size == Decimal("0.00001")
    assert registry.get("BTCUSDT").quantity_step == Decimal("0.1")
    assert registry.api_projection() == [
        {"symbol": "BTCUSDT", "tick_size": "0.0001"},
        {"symbol": "ONGUSDT", "tick_size": "0.00001"},
    ]
    assert len(session.params) == 2


def test_failed_refresh_preserves_previous_valid_snapshot():
    session = _Session([_page([_instrument("BTCUSDT")]), OSError("page one failed")])
    registry = InstrumentRegistry(session)
    first = registry.refresh()

    try:
        registry.refresh()
    except InstrumentRegistryError:
        pass
    else:
        raise AssertionError("failed refresh was published")

    assert registry.snapshot() is first
    assert registry.get("BTCUSDT") is first.instruments[0]


def test_failure_halfway_through_pagination_publishes_nothing():
    registry = InstrumentRegistry(_Session([
        _page([_instrument("BTCUSDT")], "page-2"),
        OSError("page two failed"),
    ]))

    try:
        registry.refresh()
    except InstrumentRegistryError:
        pass
    else:
        raise AssertionError("partial refresh was published")

    assert registry.list_supported() == ()
    assert registry.supports("BTCUSDT") is False


def test_duplicate_symbol_and_cursor_loop_fail_closed():
    duplicate = InstrumentRegistry(_Session([
        _page([_instrument("BTCUSDT")], "page-2"),
        _page([_instrument("BTCUSDT")]),
    ]))
    loop = InstrumentRegistry(_Session([
        _page([_instrument("BTCUSDT")], "page-2"),
        _page([_instrument("ONGUSDT")], "page-2"),
    ]))

    for registry in (duplicate, loop):
        try:
            registry.refresh()
        except InstrumentRegistryError:
            pass
        else:
            raise AssertionError("ambiguous pagination was accepted")
        assert registry.list_supported() == ()


TESTS = (
    test_registry_paginates_filters_normalizes_and_looks_up_without_refetch,
    test_failed_refresh_preserves_previous_valid_snapshot,
    test_failure_halfway_through_pagination_publishes_nothing,
    test_duplicate_symbol_and_cursor_loop_fail_closed,
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(test) for test in TESTS)


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"instrument registry tests: {len(TESTS)} passed")
