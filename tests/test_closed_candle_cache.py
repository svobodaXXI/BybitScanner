import json
import logging
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.paper_http_server import PaperHttpHandler, SerializedPaperRuntime


class _Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value


class _Fetch:
    """Fake network fetch that records the calling thread."""

    def __init__(self, result=lambda symbol: {"time_ms": 60_000, "symbol": symbol}):
        self.result = result
        self.calls = []

    def __call__(self, symbol):
        self.calls.append((symbol, threading.get_ident()))
        return self.result(symbol)


def _owner_provider(fetch, clock, *, owner=True):
    return CachedClosedCandleProvider(
        fetch, max_age_s=90, clock=clock, is_owner_thread=lambda: owner,
    )


def test_fresh_entry_is_served_to_owner_without_fetch():
    fetch, clock = _Fetch(), _Clock()
    cache = _owner_provider(fetch, clock)
    cache._fetch_and_store("BTCUSDT")
    clock.value += 90

    assert cache("BTCUSDT") == {"time_ms": 60_000, "symbol": "BTCUSDT"}
    assert len(fetch.calls) == 1
    assert cache.metrics() == {"candle_cache_hits": 1, "candle_cache_misses_owner": 0}


def test_owner_miss_on_empty_or_stale_fetches_once_stores_and_warns(caplog):
    fetch, clock = _Fetch(), _Clock()
    cache = _owner_provider(fetch, clock)

    with caplog.at_level(logging.WARNING, logger="terminal.runtime.closed_candle_cache"):
        assert cache("BTCUSDT") is not None  # empty -> previous behaviour: fetch in place
        assert len(fetch.calls) == 1
        assert cache("BTCUSDT") is not None  # now cached
        assert len(fetch.calls) == 1

        clock.value += 91  # stale
        assert cache("BTCUSDT") is not None
        assert len(fetch.calls) == 2
        clock.value += 1
        assert cache("BTCUSDT") is not None  # refreshed entry is fresh again
        assert len(fetch.calls) == 2

    warnings = [r.getMessage() for r in caplog.records]
    assert warnings == [
        "candle cache miss on owner thread symbol=BTCUSDT",
        "candle cache miss on owner thread symbol=BTCUSDT",
    ]
    assert cache.metrics() == {"candle_cache_hits": 2, "candle_cache_misses_owner": 2}


def test_owner_miss_warning_is_rate_limited_per_symbol(caplog):
    fetch, clock = _Fetch(result=lambda symbol: None), _Clock()
    cache = _owner_provider(fetch, clock)
    with caplog.at_level(logging.WARNING, logger="terminal.runtime.closed_candle_cache"):
        for _ in range(3):
            assert cache("BTCUSDT") is None  # network unavailable -> None, as before
            clock.value += 10
        cache("ETHUSDT")
        clock.value += 60
        cache("BTCUSDT")
    assert [r.getMessage() for r in caplog.records] == [
        "candle cache miss on owner thread symbol=BTCUSDT",
        "candle cache miss on owner thread symbol=ETHUSDT",
        "candle cache miss on owner thread symbol=BTCUSDT",
    ]
    assert len(fetch.calls) == 5  # every miss still fetches


def test_stale_entry_and_unavailable_network_returns_none():
    results = iter([{"time_ms": 60_000}, None])
    fetch, clock = _Fetch(result=lambda symbol: next(results)), _Clock()
    cache = _owner_provider(fetch, clock)
    cache._fetch_and_store("BTCUSDT")
    clock.value += 91
    assert cache("BTCUSDT") is None


def test_non_owner_call_always_fetches_and_fills_the_cache():
    fetch, clock = _Fetch(), _Clock()
    owner = {"value": False}
    cache = CachedClosedCandleProvider(
        fetch, clock=clock, is_owner_thread=lambda: owner["value"],
    )
    cache("BTCUSDT")
    cache("BTCUSDT")
    assert len(fetch.calls) == 2  # the monitor thread keeps refreshing

    owner["value"] = True
    assert cache("BTCUSDT") == {"time_ms": 60_000, "symbol": "BTCUSDT"}
    assert len(fetch.calls) == 2


def test_unbound_provider_behaves_like_plain_fetch():
    fetch = _Fetch()
    cache = CachedClosedCandleProvider(fetch)
    cache("BTCUSDT")
    cache("BTCUSDT")
    assert len(fetch.calls) == 2


def test_warm_up_ignores_errors():
    def fetch(symbol):
        if symbol == "BADUSDT":
            raise RuntimeError("network down")
        return {"time_ms": 60_000}

    cache = CachedClosedCandleProvider(fetch, is_owner_thread=lambda: True)
    cache.warm(["BADUSDT", "BTCUSDT", "BTCUSDT"])
    assert cache("BTCUSDT") == {"time_ms": 60_000}
    assert cache.metrics()["candle_cache_hits"] == 1


class _CandleRuntime:
    """Owned runtime stub: binds the cache to the owner thread like PaperRuntime."""

    SYMBOLS = ("AUSDT", "BUSDT", "CUSDT", "DUSDT", "EUSDT")

    def __init__(self, fetch):
        owner = threading.get_ident()
        self.robot_closed_candle_cache = CachedClosedCandleProvider(fetch)
        self.robot_closed_candle_cache.bind_owner_thread(lambda: threading.get_ident() == owner)

    def robot_approved_candidate_symbols(self):
        return self.SYMBOLS

    def close(self):
        return None


def test_warm_up_runs_off_the_owner_thread_and_owner_then_hits_the_cache():
    fetch = _Fetch()
    runtime = SerializedPaperRuntime(lambda: _CandleRuntime(fetch))
    try:
        runtime.warm_robot_closed_candles()
        owner_ident = runtime._thread.ident
        assert sorted(symbol for symbol, _ in fetch.calls) == list(_CandleRuntime.SYMBOLS)
        assert all(ident != owner_ident for _, ident in fetch.calls)

        candles = runtime.call(lambda owned: [
            owned.robot_closed_candle_cache(symbol) for symbol in _CandleRuntime.SYMBOLS
        ])
        assert all(candle is not None for candle in candles)
        assert len(fetch.calls) == 5  # no fetch on the owner thread

        metrics = runtime.protection_ingress_metrics()
        assert metrics["candle_cache_hits"] == 5
        assert metrics["candle_cache_misses_owner"] == 0
    finally:
        runtime.close()


def test_robot_command_routes_warm_candles_on_the_handler_thread_before_queuing():
    class RecordingRuntime:
        def __init__(self):
            self.log = []

        def warm_robot_closed_candles(self):
            self.log.append(("warm", threading.get_ident()))

        def call(self, operation, timeout=15.0):
            self.log.append(("call", threading.get_ident()))
            raise RuntimeError("owner unavailable")

    runtime = RecordingRuntime()
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = runtime
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for route in ("/api/robot/synchronize-pending-entries", "/api/robot/reconcile"):
            runtime.log.clear()
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{route}",
                data=json.dumps({}).encode(), headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                urllib.request.urlopen(request)
            except urllib.error.HTTPError:
                pass
            assert [kind for kind, _ in runtime.log] == ["warm", "call"], route
            assert runtime.log[0][1] == runtime.log[1][1]  # same handler thread
            assert runtime.log[0][1] != threading.get_ident()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_warm_up_failure_does_not_block_the_command():
    class FailingWarmRuntime:
        calls = 0

        def warm_robot_closed_candles(self):
            raise RuntimeError("network down")

        def call(self, operation, timeout=15.0):
            FailingWarmRuntime.calls += 1
            raise RuntimeError("owner unavailable")

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = FailingWarmRuntime()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/robot/reconcile",
            data=b"{}", headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError:
            pass
        assert FailingWarmRuntime.calls == 1
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
