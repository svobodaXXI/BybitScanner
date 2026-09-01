import json
import os
import tempfile
import threading
import time
import urllib.request
import urllib.error
from dataclasses import replace
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from terminal.domain.models import (
    Category, OrderId, OrderSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.market_data.workspace_errors import WorkspaceCandidateNotReady
from terminal.runtime.paper_http_server import (
    BYBIT_WEBSOCKET_CONNECT_TIMEOUT,
    PaperHttpHandler,
    MarketDataSession,
    PublicKlineBuffer,
    PublicOrderBookBuffer,
    PublicTradeBuffer,
    PublicTradeKlineBuffer,
    SerializedPaperRuntime,
    WorkspaceMarketDataManager,
    configure_bybit_proxy_environment,
    create_bybit_rest_session,
    create_bybit_websocket_connection,
    validate_bybit_proxy,
)
from terminal.runtime.paper_runtime import PaperRuntime
from terminal.exchange.bybit_account_validation import ValidatedBybitAccount
from terminal.exchange.bybit_account_validation import AccountValidationError
from terminal.persistence.credential_store import CredentialStoreError, DpapiCredentialStore
from terminal.persistence.live_account_store import LiveAccountProjectionStore


def test_bybit_proxy_is_optional_and_machine_configurable(monkeypatch):
    monkeypatch.delenv("BYBITSCANNER_BYBIT_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    assert configure_bybit_proxy_environment() == ""
    assert create_bybit_rest_session().proxies == {}

    proxy = "socks5h://127.0.0.1:10808"
    monkeypatch.setenv("BYBITSCANNER_BYBIT_PROXY", proxy)
    assert configure_bybit_proxy_environment() == proxy
    assert os.environ["ALL_PROXY"] == proxy
    assert create_bybit_rest_session().proxies == {"http": proxy, "https": proxy}


def test_empty_bybit_proxy_override_disables_inherited_all_proxy(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks5h://127.0.0.1:9999")
    monkeypatch.setenv("all_proxy", "socks5h://127.0.0.1:9999")
    monkeypatch.setenv("BYBITSCANNER_BYBIT_PROXY", "")
    assert configure_bybit_proxy_environment() == ""
    assert "ALL_PROXY" not in os.environ
    assert "all_proxy" not in os.environ


def test_bybit_websocket_uses_configured_socks_proxy(monkeypatch):
    captured = {}
    secure_socket = object()

    class Connection:
        def settimeout(self, timeout):
            captured["read_timeout"] = timeout

    class ProxySocket:
        def set_proxy(self, *args, **kwargs):
            captured["set_proxy"] = (args, kwargs)

        def settimeout(self, timeout):
            captured["socket_timeout"] = timeout

        def connect(self, address):
            captured["connect"] = address

        def close(self):
            captured["closed"] = True

    def connect(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return Connection()

    monkeypatch.setenv(
        "BYBITSCANNER_BYBIT_PROXY", "socks5h://127.0.0.1:10808",
    )
    proxy_socket = ProxySocket()
    class SslContext:
        def wrap_socket(self, sock, *, server_hostname):
            captured["wrap_socket"] = (sock, server_hostname)
            return secure_socket

    monkeypatch.setattr("terminal.runtime.paper_http_server.socks.socksocket", lambda: proxy_socket)
    monkeypatch.setattr("terminal.runtime.paper_http_server.ssl.create_default_context", SslContext)
    monkeypatch.setattr("terminal.runtime.paper_http_server.websocket.create_connection", connect)
    create_bybit_websocket_connection("wss://stream.bybit.com/v5/public/linear", timeout=1)
    assert captured["url"] == "wss://stream.bybit.com/v5/public/linear"
    assert captured["timeout"] == BYBIT_WEBSOCKET_CONNECT_TIMEOUT
    assert captured["socket"] is secure_socket
    assert captured["socket_timeout"] == BYBIT_WEBSOCKET_CONNECT_TIMEOUT
    assert captured["read_timeout"] == 1
    assert captured["connect"] == ("stream.bybit.com", 443)
    assert captured["wrap_socket"] == (proxy_socket, "stream.bybit.com")
    assert captured["set_proxy"][1] == {
        "rdns": True, "username": None, "password": None,
    }


def test_configured_bybit_proxy_fails_clearly_when_unavailable(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr("terminal.runtime.paper_http_server.socket.create_connection", unavailable)
    with pytest.raises(RuntimeError, match="Configured Bybit SOCKS proxy is unavailable"):
        validate_bybit_proxy("socks5h://127.0.0.1:10808", timeout=0.01)

    with pytest.raises(RuntimeError, match="must be a socks5"):
        validate_bybit_proxy("socks5h://127.0.0.1:not-a-port")


def test_bybit_websocket_connect_timeout_remains_bounded(monkeypatch):
    class Socket:
        closed = False

        def set_proxy(self, *args, **kwargs):
            return None

        def settimeout(self, timeout):
            assert timeout == BYBIT_WEBSOCKET_CONNECT_TIMEOUT

        def connect(self, address):
            raise TimeoutError("SOCKS handshake exceeded connect budget")

        def close(self):
            self.closed = True

    proxy_socket = Socket()
    monkeypatch.setenv("BYBITSCANNER_BYBIT_PROXY", "socks5h://127.0.0.1:10808")
    monkeypatch.setattr("terminal.runtime.paper_http_server.socks.socksocket", lambda: proxy_socket)
    with pytest.raises(TimeoutError, match="exceeded connect budget"):
        create_bybit_websocket_connection(
            "wss://stream.bybit.com/v5/public/linear", timeout=1,
        )
    assert proxy_socket.closed is True


def test_direct_websocket_preserves_existing_fast_path(monkeypatch):
    captured = {}
    connection = object()
    monkeypatch.delenv("BYBITSCANNER_BYBIT_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    monkeypatch.setattr(
        "terminal.runtime.paper_http_server.websocket.create_connection",
        lambda url, **kwargs: captured.update({"url": url, **kwargs}) or connection,
    )
    assert create_bybit_websocket_connection("wss://stream.bybit.com", timeout=1) is connection
    assert captured == {"url": "wss://stream.bybit.com", "timeout": 1}


def test_bybit_websocket_closes_tls_socket_when_handshake_fails(monkeypatch):
    class Socket:
        def set_proxy(self, *args, **kwargs):
            return None

        def settimeout(self, timeout):
            return None

        def connect(self, address):
            return None

        def close(self):
            return None

    class SecureSocket:
        closed = False

        def close(self):
            self.closed = True

    secure_socket = SecureSocket()
    monkeypatch.setenv("BYBITSCANNER_BYBIT_PROXY", "socks5h://127.0.0.1:10808")
    monkeypatch.setattr("terminal.runtime.paper_http_server.socks.socksocket", Socket)
    monkeypatch.setattr(
        "terminal.runtime.paper_http_server.ssl.create_default_context",
        lambda: type("Context", (), {"wrap_socket": lambda self, *args, **kwargs: secure_socket})(),
    )
    monkeypatch.setattr(
        "terminal.runtime.paper_http_server.websocket.create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("handshake failed")),
    )
    with pytest.raises(RuntimeError, match="handshake failed"):
        create_bybit_websocket_connection("wss://stream.bybit.com/v5/public/linear", timeout=1)
    assert secure_socket.closed is True


class _SwitchBook:
    def __init__(self, ready: bool) -> None:
        self.ready = ready
        self.consumer = None

    def wait_until_ready(self, timeout: float) -> bool:
        assert timeout == 0.01
        return self.ready

    def set_update_consumer(self, consumer) -> None:
        self.consumer = consumer


class _SwitchSession:
    def __init__(self, symbol: str, ready: bool, previous=None) -> None:
        self.symbol = symbol
        self.public_orderbook = _SwitchBook(ready)
        self.public_trades = object()
        self.public_klines = {}
        self.generation = 0
        self.closed = False
        self.previous_closed_during_readiness = None
        self._previous = previous

    def wait_until_ready(self, timeout: float) -> bool:
        self.previous_closed_during_readiness = (
            self._previous.closed if self._previous is not None else None
        )
        return self.public_orderbook.wait_until_ready(timeout)

    def close(self) -> None:
        self.closed = True


class _SwitchProvider:
    def __init__(self, buffer) -> None:
        self.buffer = buffer

    def set_buffer(self, buffer) -> None:
        self.buffer = buffer


class _SwitchRuntime:
    def enqueue_book_update(self, book_update_id: str) -> None:
        return None


class _InstrumentRegistryStub:
    def __init__(self, instruments: list[dict[str, str]]) -> None:
        self._instruments = instruments

    def get(self, symbol: str):
        normalized = symbol.strip().upper()
        for item in self._instruments:
            if item["symbol"] == normalized:
                return type("Instrument", (), {"tick_size": Decimal(item["tick_size"])})()
        raise LookupError(normalized)

    def api_projection(self) -> list[dict[str, str]]:
        return list(self._instruments)


def _instrument_registry(instruments: list[dict[str, str]]) -> _InstrumentRegistryStub:
    return _InstrumentRegistryStub(instruments)


class _BlockingTrades:
    def __init__(self) -> None:
        self.snapshot_started = threading.Event()
        self.release_snapshot = threading.Event()

    def snapshot_after(self, after: int) -> list[dict]:
        self.snapshot_started.set()
        assert self.release_snapshot.wait(timeout=1)
        return [{"id": "late-btc", "seq": 1, "symbol": "BTCUSDT"}]

    def close(self) -> None:
        return None


def _ready_market_session(symbol: str, sequence: int) -> MarketDataSession:
    book = PublicOrderBookBuffer(symbol, depth=2)
    assert book.apply_message({
        "topic": f"orderbook.2.{symbol}",
        "type": "snapshot",
        "ts": sequence,
        "data": {
            "u": sequence,
            "seq": sequence,
            "b": [[str(sequence), "2"]],
            "a": [[str(sequence + 1), "3"]],
        },
    }) == "APPLIED"
    trades = PublicTradeBuffer(symbol, aggregation_window_ms=0)
    trades.add_trades([{
        "id": f"{symbol}-{sequence}",
        "seq": sequence,
        "timestamp": sequence,
        "symbol": symbol,
        "side": "BUY",
        "price": str(sequence),
        "quantity": "1",
    }])
    trades.flush()
    return MarketDataSession(symbol, book, trades, {})


def _read_sse_payload(response) -> dict:
    while True:
        line = response.readline()
        if not line:
            raise AssertionError("SSE stream ended before delivering data")
        if line.startswith(b"data:"):
            return json.loads(line.removeprefix(b"data:"))


def _assert_sse_terminates(response) -> None:
    while True:
        line = response.readline()
        if not line:
            return
        assert not line.startswith(b"data:")


def _assert_inactive_request(url: str) -> None:
    try:
        urllib.request.urlopen(url)
    except urllib.error.HTTPError as error:
        assert error.code == 409
        assert json.load(error)["error"] == "inactive_workspace_symbol"
    else:
        raise AssertionError("inactive workspace consumer request was not rejected")


def test_workspace_switch_is_ready_before_atomic_swap_and_stale_consumer_cannot_reactivate():
    btc = _SwitchSession("BTCUSDT", True)
    eth = _SwitchSession("ETHUSDT", True, btc)
    provider = _SwitchProvider(btc.public_orderbook)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        provider,
        _SwitchRuntime(),
        btc,
        session_factory=lambda symbol, tick_size: eth,
        readiness_timeout=0.01,
    )

    active = manager.switch("ethusdt")

    assert active is eth
    assert eth.previous_closed_during_readiness is False
    assert btc.closed is True
    assert provider.buffer is eth.public_orderbook
    assert eth.public_orderbook.consumer is not None
    assert manager.get_active("ETHUSDT") == (eth, 2)
    try:
        manager.get_active("BTCUSDT")
    except LookupError:
        pass
    else:
        raise AssertionError("stale BTC consumer was not rejected")
    assert manager.get_active("ETHUSDT") == (eth, 2)

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.market_data = manager
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/public-trades?symbol=BTCUSDT",
            )
        except urllib.error.HTTPError as error:
            assert error.code == 409
            assert json.load(error)["error"] == "inactive_workspace_symbol"
        else:
            raise AssertionError("stale HTTP consumer request was not rejected")
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_workspace_consumers_follow_active_generation_across_rapid_symbol_return():
    btc = _ready_market_session("BTCUSDT", 100)
    eth = _ready_market_session("ETHUSDT", 200)
    returned_btc = _ready_market_session("BTCUSDT", 300)
    candidates = iter((eth, returned_btc))
    provider = _SwitchProvider(btc.public_orderbook)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        provider,
        _SwitchRuntime(),
        btc,
        session_factory=lambda symbol, tick_size: next(candidates),
        readiness_timeout=0.01,
    )

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.market_data = manager
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    btc_book_stream = urllib.request.urlopen(
        f"{base_url}/api/public-orderbook/stream?symbol=BTCUSDT",
    )
    btc_trade_stream = urllib.request.urlopen(
        f"{base_url}/api/public-trades/stream?symbol=BTCUSDT",
    )
    try:
        assert _read_sse_payload(btc_book_stream)["generation"] == 1
        assert _read_sse_payload(btc_trade_stream)["generation"] == 1

        assert manager.switch("ETHUSDT") is eth
        assert manager.is_current(btc, 1) is False
        assert manager.is_current(eth, 2) is True
        _assert_sse_terminates(btc_book_stream)
        _assert_sse_terminates(btc_trade_stream)

        with urllib.request.urlopen(
            f"{base_url}/api/public-orderbook/stream?symbol=ETHUSDT",
        ) as eth_book_stream, urllib.request.urlopen(
            f"{base_url}/api/public-trades/stream?symbol=ETHUSDT",
        ) as eth_trade_stream:
            eth_book = _read_sse_payload(eth_book_stream)
            eth_tape = _read_sse_payload(eth_trade_stream)
            assert eth_book["symbol"] == "ETHUSDT"
            assert eth_book["generation"] == 2
            assert eth_book["state"] == "READY"
            assert eth_book["bids"] and eth_book["asks"]
            assert eth_tape["symbol"] == "ETHUSDT"
            assert eth_tape["generation"] == 2
            assert eth_tape["trades"]
            assert {trade["symbol"] for trade in eth_tape["trades"]} == {"ETHUSDT"}

            _assert_inactive_request(
                f"{base_url}/api/public-orderbook/stream?symbol=BTCUSDT",
            )
            _assert_inactive_request(
                f"{base_url}/api/public-trades?symbol=BTCUSDT",
            )

            assert manager.switch("BTCUSDT") is returned_btc
            assert manager.is_current(eth, 2) is False
            assert manager.is_current(returned_btc, 3) is True
            _assert_sse_terminates(eth_book_stream)
            _assert_sse_terminates(eth_trade_stream)

        with urllib.request.urlopen(
            f"{base_url}/api/public-orderbook/stream?symbol=BTCUSDT",
        ) as returned_book_stream, urllib.request.urlopen(
            f"{base_url}/api/public-trades?symbol=BTCUSDT",
        ) as returned_tape_response:
            returned_book = _read_sse_payload(returned_book_stream)
            returned_tape = json.load(returned_tape_response)
            assert returned_book["symbol"] == "BTCUSDT"
            assert returned_book["generation"] == 3
            assert returned_book["state"] == "READY"
            assert returned_book["bids"] and returned_book["asks"]
            assert returned_tape["symbol"] == "BTCUSDT"
            assert returned_tape["generation"] == 3
            assert returned_tape["trades"]
            assert {trade["symbol"] for trade in returned_tape["trades"]} == {"BTCUSDT"}

        _assert_inactive_request(
            f"{base_url}/api/public-trades?symbol=ETHUSDT",
        )
    finally:
        btc_book_stream.close()
        btc_trade_stream.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_inflight_stale_trade_request_fails_closed_after_generation_changes():
    btc = _ready_market_session("BTCUSDT", 100)
    blocking_trades = _BlockingTrades()
    btc.public_trades = blocking_trades
    eth = _ready_market_session("ETHUSDT", 200)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        _SwitchProvider(btc.public_orderbook),
        _SwitchRuntime(),
        btc,
        session_factory=lambda symbol, tick_size: eth,
        readiness_timeout=0.01,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.market_data = manager
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.start()
    response: dict[str, object] = {}

    def request_btc_trades() -> None:
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/public-trades?symbol=BTCUSDT",
            )
        except urllib.error.HTTPError as error:
            response["status"] = error.code
            response["payload"] = json.load(error)

    request_thread = threading.Thread(target=request_btc_trades)
    request_thread.start()
    try:
        assert blocking_trades.snapshot_started.wait(timeout=1)
        assert manager.switch("ETHUSDT") is eth
        blocking_trades.release_snapshot.set()
        request_thread.join(timeout=1)
        assert not request_thread.is_alive()
        assert response == {
            "status": 409,
            "payload": {"ok": False, "error": "inactive_workspace_symbol"},
        }
        assert manager.get_active("ETHUSDT") == (eth, 2)
    finally:
        blocking_trades.release_snapshot.set()
        request_thread.join(timeout=1)
        server.shutdown()
        server_thread.join(timeout=5)
        server.server_close()


def test_workspace_switch_timeout_preserves_ready_active_session_and_provider():
    btc = _SwitchSession("BTCUSDT", True)
    eth = _SwitchSession("ETHUSDT", False, btc)
    provider = _SwitchProvider(btc.public_orderbook)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        provider,
        _SwitchRuntime(),
        btc,
        session_factory=lambda symbol, tick_size: eth,
        readiness_timeout=0.01,
    )

    try:
        manager.switch("ETHUSDT")
    except WorkspaceCandidateNotReady as error:
        assert error.envelope(request_id="switch-1")["retryable"] is True
    else:
        raise AssertionError("unready candidate switch did not fail closed")

    assert eth.closed is True
    assert btc.closed is False
    assert provider.buffer is btc.public_orderbook
    assert manager.get_active("BTCUSDT") == (btc, 1)


def test_workspace_switch_http_preserves_structured_semantic_failure():
    btc = _SwitchSession("BTCUSDT", True)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([{"symbol": "BTCUSDT", "tick_size": "0.5"}]),
        _SwitchProvider(btc.public_orderbook), _SwitchRuntime(), btc,
        readiness_timeout=0.01,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.market_data = manager
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/api/workspace/symbol",
        data=json.dumps({"symbol": "NOTUSDT"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Request-ID": "switch-42"},
        method="POST",
    )
    try:
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            assert error.code == 400
            payload = json.load(error)
        else:
            raise AssertionError("unsupported instrument request succeeded")
        assert payload["error"] == "unsupported_instrument"
        assert payload["workspace_error"] == {
            "code": "unsupported_instrument",
            "stage": "instrument_lookup",
            "requested_symbol": "NOTUSDT",
            "active_symbol": "BTCUSDT",
            "retryable": False,
            "request_id": "switch-42",
            "message": "Unsupported Workspace instrument: NOTUSDT",
        }
        assert manager.get_active("BTCUSDT") == (btc, 1)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_workspace_state_endpoint_is_read_only_and_reports_authoritative_state():
    btc = _SwitchSession("BTCUSDT", True)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([{"symbol": "BTCUSDT", "tick_size": "0.5"}]),
        _SwitchProvider(btc.public_orderbook), _SwitchRuntime(), btc,
        readiness_timeout=0.01,
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.market_data = manager
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/api/workspace/state"
    before = manager.get_active("BTCUSDT")
    try:
        with urllib.request.urlopen(url) as response:
            first = json.load(response)
        with urllib.request.urlopen(url) as response:
            second = json.load(response)
        assert first == second
        assert first["ok"] is True
        assert first["workspace"]["requested_symbol"] == "BTCUSDT"
        assert first["workspace"]["active_symbol"] == "BTCUSDT"
        assert first["workspace"]["active_generation"] == 1
        assert first["workspace"]["switch_state"] == "READY"
        assert first["workspace"]["pending_symbol"] is None
        assert first["workspace"]["last_error"] is None
        assert first["workspace"]["readiness"]["ready"] is True
        assert first["workspace"]["streams"]["session_count"] == 0
        assert manager.get_active("BTCUSDT") == before
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_workspace_activation_failure_rolls_back_provider_and_active_generation():
    btc = _SwitchSession("BTCUSDT", True)
    eth = _SwitchSession("ETHUSDT", True, btc)
    provider = _SwitchProvider(btc.public_orderbook)
    original_set_consumer = btc.public_orderbook.set_update_consumer
    calls = 0

    def fail_once(consumer) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("consumer detach failed")
        original_set_consumer(consumer)

    btc.public_orderbook.set_update_consumer = fail_once
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        provider, _SwitchRuntime(), btc,
        session_factory=lambda symbol, tick_size: eth,
        readiness_timeout=0.01,
    )
    try:
        manager.switch("ETHUSDT")
    except Exception as error:
        assert error.code == "upstream_market_data_failure"
    else:
        raise AssertionError("activation failure was accepted")
    assert provider.buffer is btc.public_orderbook
    assert manager.get_active("BTCUSDT") == (btc, 1)
    assert eth.closed is True


def test_workspace_candidate_wait_does_not_block_current_read_only_consumers():
    btc = _SwitchSession("BTCUSDT", True)
    candidate_waiting = threading.Event()
    release_candidate = threading.Event()
    eth = _SwitchSession("ETHUSDT", True, btc)

    def wait_until_ready(timeout: float) -> bool:
        candidate_waiting.set()
        assert release_candidate.wait(timeout=1)
        return True

    eth.wait_until_ready = wait_until_ready
    provider = _SwitchProvider(btc.public_orderbook)
    manager = WorkspaceMarketDataManager(
        _instrument_registry([
            {"symbol": "BTCUSDT", "tick_size": "0.5"},
            {"symbol": "ETHUSDT", "tick_size": "0.05"},
        ]),
        provider,
        _SwitchRuntime(),
        btc,
        session_factory=lambda symbol, tick_size: eth,
        readiness_timeout=1,
    )
    switched = threading.Thread(target=lambda: manager.switch("ETHUSDT"))
    switched.start()
    assert candidate_waiting.wait(timeout=1)

    assert manager.get_active("BTCUSDT") == (btc, 1)
    assert manager.is_current(btc, 1) is True
    assert btc.closed is False

    release_candidate.set()
    switched.join(timeout=1)
    assert not switched.is_alive()
    assert manager.get_active("ETHUSDT") == (eth, 2)


class StaticBookProvider:
    def get_book(self, symbol: Symbol) -> NormalizedOrderBook:
        return NormalizedOrderBook(
            symbol=symbol,
            bids=(PriceLevel(Price(Decimal("64249.5")), Quantity(Decimal("10"))),),
            asks=(PriceLevel(Price(Decimal("64250.5")), Quantity(Decimal("10"))),),
            health=BookHealth.READY,
            received_at_ms=int(time.time() * 1000),
            available_depth=1,
        )

    def get_current_book_update(
        self, symbol: Symbol,
    ) -> tuple[str, NormalizedOrderBook]:
        return "BTCUSDT:20:10", self.get_book(symbol)


def _runtime_owner(
    path: Path, *, credential_store=None, account_validator=None,
    account_manager=None, live_account_store=None, live_account_store_path=None,
    book_provider=None,
) -> SerializedPaperRuntime:
    instrument = InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )
    return SerializedPaperRuntime(lambda: PaperRuntime(
        path,
        book_provider=book_provider or StaticBookProvider(),
        instrument_snapshot=instrument,
        instrument_provider=lambda symbol: replace(instrument, symbol=symbol),
        credential_store=credential_store,
        account_validator=account_validator,
        account_manager=account_manager,
        live_account_store=(
            LiveAccountProjectionStore(live_account_store_path)
            if live_account_store_path is not None else live_account_store
        ),
    ))


def test_market_post_completes_with_one_durable_execution():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        response = {}

        def post_market():
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/market",
                data=json.dumps(
                    {
                        "client_action_id": "http-market-buy-1",
                        "symbol": "BTCUSDT",
                        "side": "Buy",
                        "volume": {"unit": "usdt", "amount": "321"},
                        "sizing_reference_price": "64250",
                        "slippage_type": "Percent",
                        "slippage_value": "0.5",
                    }
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as result:
                response["status"] = result.status
                response["body"] = json.load(result)

        client = threading.Thread(target=post_market)
        client.start()
        try:
            server.handle_request()
            client.join(timeout=5)

            assert not client.is_alive()
            assert response["status"] == 200
            assert response["body"]["status"] == "completed", response["body"]
            assert response["body"]["paper_state"]["state_revision"] == 1
            execution_count = runtime.call(
                lambda owned: len(owned.store.load_executions())
            )
            assert execution_count == 1
        finally:
            server.server_close()
            runtime.close()


def test_full_close_response_contains_revisioned_flat_state():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        def post(path: str, payload: dict) -> dict:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            opened = post("/api/market", {
                "client_action_id": "full-close-open-1",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "volume": {"unit": "usdt", "amount": "321"},
                "sizing_reference_price": "64250",
                "slippage_type": "Percent",
                "slippage_value": "0.5",
            })
            assert opened["paper_state"]["state_revision"] == 1

            closed = post("/api/full-close", {
                "client_action_id": "full-close-1",
                "symbol": "BTCUSDT",
            })
            assert closed["status"] == "completed"
            assert closed["paper_state"]["position_side"] == "Flat"
            assert closed["paper_state"]["position_quantity"] == "0"
            assert closed["paper_state"]["state_revision"] == 2
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()


def test_open_positions_get_returns_all_open_symbols_for_current_account():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        def post(symbol: str, action: str) -> None:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/market",
                data=json.dumps({
                    "client_action_id": action, "symbol": symbol, "side": "Buy",
                    "volume": {"unit": "usdt", "amount": "321"},
                    "sizing_reference_price": "64250",
                    "slippage_type": "Percent", "slippage_value": "0.5",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request) as response:
                assert json.load(response)["status"] == "completed"

        try:
            post("BTCUSDT", "http-inventory-btc")
            post("ETHUSDT", "http-inventory-eth")
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/open-positions"
            ) as response:
                payload = json.load(response)
            assert payload["ok"] is True
            assert payload["account_id"] == "paper"
            assert [item["symbol"] for item in payload["positions"]] == [
                "BTCUSDT", "ETHUSDT",
            ]
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()


def test_close_all_post_closes_authoritative_inventory_once():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        def post(path: str, payload: dict) -> dict:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            for symbol in ("BTCUSDT", "ETHUSDT"):
                post("/api/market", {
                    "client_action_id": f"http-bulk-open-{symbol.lower()}",
                    "symbol": symbol, "side": "Buy",
                    "volume": {"unit": "usdt", "amount": "321"},
                    "sizing_reference_price": "64250",
                    "slippage_type": "Percent", "slippage_value": "0.5",
                })
            result = post("/api/close-all", {"client_action_id": "http-bulk-close-1"})
            assert result["ok"] is True
            assert len(result["results"]) == 2
            assert result["positions"] == []
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()


def test_limit_post_returns_completed_and_creates_active_order():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        response = {}

        def post_limit():
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/limit",
                data=json.dumps({
                    "client_action_id": "http-limit-buy-1",
                    "symbol": "BTCUSDT",
                    "side": "Buy",
                    "volume": {"unit": "usdt", "amount": "321"},
                    "sizing_reference_price": "64000",
                    "limit_price": "64000",
                    "time_in_force": "GTC",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as result:
                response["status"] = result.status
                response["body"] = json.load(result)

        client = threading.Thread(target=post_limit)
        client.start()
        try:
            server.handle_request()
            client.join(timeout=5)

            assert not client.is_alive()
            assert response["status"] == 200
            assert response["body"]["status"] == "completed", response["body"]
            assert len(response["body"]["paper_state"]["active_limit_orders"]) == 1
            assert response["body"]["paper_state"]["state_revision"] == 1
            state = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            assert len(state["active_limit_orders"]) == 1
        finally:
            server.server_close()
            runtime.close()


def test_limit_mutations_return_revisioned_resulting_authoritative_state():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        def post(path: str, payload: dict) -> dict:
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}{path}",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as response:
                assert response.status == 200
                return json.load(response)

        try:
            created = post("/api/limit", {
                "client_action_id": "state-create-1",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "volume": {"unit": "usdt", "amount": "321"},
                "sizing_reference_price": "64000",
                "limit_price": "64000",
                "time_in_force": "GTC",
            })
            order_id = created["order_id"]
            assert created["status"] == "completed"
            assert created["paper_state"]["state_revision"] == 1
            assert [item["order_id"] for item in created["paper_state"]["active_limit_orders"]] == [order_id]

            duplicate_create = post("/api/limit", {
                "client_action_id": "state-create-1",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "volume": {"unit": "usdt", "amount": "321"},
                "sizing_reference_price": "64000",
                "limit_price": "64000",
                "time_in_force": "GTC",
            })
            assert duplicate_create["reason_code"] == "duplicate_action"
            assert duplicate_create["paper_state"]["state_revision"] == 1

            amended = post("/api/limit/amend", {
                "client_action_id": "state-amend-1",
                "symbol": "BTCUSDT",
                "order_id": order_id,
                "limit_price": "63900",
            })
            assert amended["paper_state"]["state_revision"] == 2
            assert amended["paper_state"]["active_limit_orders"][0]["price"] == "63900"

            duplicate_amend = post("/api/limit/amend", {
                "client_action_id": "state-amend-1",
                "symbol": "BTCUSDT",
                "order_id": order_id,
                "limit_price": "63900",
            })
            assert duplicate_amend["reason_code"] == "duplicate_action"
            assert duplicate_amend["paper_state"]["state_revision"] == 2

            noop_amend = post("/api/limit/amend", {
                "client_action_id": "state-amend-noop-1",
                "symbol": "BTCUSDT",
                "order_id": order_id,
                "limit_price": "63900",
            })
            assert noop_amend["reason_code"] == "duplicate_action"
            assert noop_amend["paper_state"]["state_revision"] == 2

            cancelled = post("/api/limit/cancel", {
                "client_action_id": "state-cancel-1",
                "symbol": "BTCUSDT",
                "order_id": order_id,
            })
            assert cancelled["reason_code"] == "cancelled"
            assert cancelled["paper_state"]["state_revision"] == 3
            assert cancelled["paper_state"]["active_limit_orders"] == []

            repeated = post("/api/limit/cancel", {
                "client_action_id": "state-cancel-2",
                "symbol": "BTCUSDT",
                "order_id": order_id,
            })
            assert repeated["reason_code"] == "already_absent"
            assert repeated["paper_state"]["state_revision"] == 3
            assert repeated["paper_state"]["active_limit_orders"] == []
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()


def test_health_get_returns_exact_paper_status():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        response = {}

        def get_health():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/health"
            ) as result:
                response["status"] = result.status
                response["body"] = json.load(result)

        client = threading.Thread(target=get_health)
        client.start()
        try:
            server.handle_request()
            client.join(timeout=5)

            assert not client.is_alive()
            assert response["status"] == 200
            assert response["body"] == {"ok": True, "mode": "paper"}
        finally:
            server.server_close()
            runtime.close()


def test_accounts_get_returns_authoritative_credential_free_catalog():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        response = {}

        def get_accounts():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/accounts"
            ) as result:
                response["status"] = result.status
                response["body"] = json.load(result)

        client = threading.Thread(target=get_accounts)
        client.start()
        try:
            server.handle_request()
            client.join(timeout=5)
            assert response == {"status": 200, "body": {
                "ok": True,
                "active_account_id": "paper",
                "session_generation": 1,
                "accounts": [{
                    "id": "paper",
                    "display_name": "Paper / Virtual",
                    "provider": "PAPER",
                    "environment": "PAPER",
                    "status": "READY",
                }],
            }}
            serialized = json.dumps(response["body"]).lower()
            assert "secret" not in serialized
            assert "credential" not in serialized
        finally:
            server.server_close()
            runtime.close()


def test_accounts_get_fails_closed_for_broken_catalog():
    class BrokenCatalogRuntime:
        def call(self, operation):
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = BrokenCatalogRuntime()
    response = {}

    def get_accounts():
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/accounts"
            )
        except urllib.error.HTTPError as error:
            response["status"] = error.code
            response["body"] = json.load(error)

    client = threading.Thread(target=get_accounts)
    client.start()
    try:
        server.handle_request()
        client.join(timeout=5)
        assert response == {
            "status": 503,
            "body": {"ok": False, "error": "account_catalog_unavailable"},
        }
    finally:
        server.server_close()


def test_accounts_get_allow_lists_fields_and_drops_credential_material():
    class CatalogRuntime:
        def call(self, operation):
            return {
                "active_account_id": "paper",
                "session_generation": 1,
                "api_secret": "must-not-cross-boundary",
                "accounts": [{
                    "id": "paper",
                    "display_name": "Paper / Virtual",
                    "provider": "PAPER",
                    "environment": "PAPER",
                    "status": "READY",
                    "credentialRef": "internal-only",
                }],
            }

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = CatalogRuntime()
    response = {}

    def get_accounts():
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/api/accounts"
        ) as result:
            response.update(json.load(result))

    client = threading.Thread(target=get_accounts)
    client.start()
    try:
        server.handle_request()
        client.join(timeout=5)
        serialized = json.dumps(response).lower()
        assert "secret" not in serialized
        assert "credential" not in serialized
        assert set(response["accounts"][0]) == {
            "id", "display_name", "provider", "environment", "status",
        }
    finally:
        server.server_close()


def test_add_bybit_account_persists_inactive_account_without_generation_change():
    class Protector:
        def protect(self, value): return value[::-1]
        def unprotect(self, value): return value[::-1]

    class Validator:
        def validate(self, credentials):
            return ValidatedBybitAccount("TESTNET", True)

    with tempfile.TemporaryDirectory() as temp:
        credential_path = Path(temp) / "accounts.dpapi"
        runtime = _runtime_owner(
            Path(temp) / "paper.sqlite3",
            credential_store=DpapiCredentialStore(credential_path, Protector()),
            account_validator=Validator(),
        )
        try:
            created = runtime.call(lambda owner: owner.add_bybit_account("Test", "key", "secret"))
            replayed = runtime.call(lambda owner: owner.add_bybit_account("Test", "key", "secret"))
            catalog = runtime.call(lambda owner: owner.account_catalog())
            assert created["created"] is True
            assert replayed == {"account_id": created["account_id"], "created": False}
            assert catalog["active_account_id"] == "paper"
            assert catalog["session_generation"] == 1
            assert len(catalog["accounts"]) == 2
            assert catalog["accounts"][1]["environment"] == "TESTNET"
            assert catalog["accounts"][1]["status"] == "READ_ONLY"
            serialized = json.dumps(catalog).lower()
            assert "secret" not in serialized and '"api_key"' not in serialized
        finally:
            runtime.close()


def test_fresh_trading_capable_validation_is_ready_but_restart_is_disconnected():
    class Protector:
        def protect(self, value): return value[::-1]
        def unprotect(self, value): return value[::-1]

    class Validator:
        def validate(self, credentials): return ValidatedBybitAccount("MAINNET", False)

    class MustNotValidateOnStartup:
        def validate(self, credentials): raise AssertionError("startup must not claim fresh validation")

    with tempfile.TemporaryDirectory() as temp:
        credential_path = Path(temp) / "accounts.dpapi"
        database_path = Path(temp) / "paper.sqlite3"
        runtime = _runtime_owner(
            database_path,
            credential_store=DpapiCredentialStore(credential_path, Protector()),
            account_validator=Validator(),
        )
        try:
            runtime.call(lambda owner: owner.add_bybit_account("Main", "key", "secret"))
            fresh = runtime.call(lambda owner: owner.account_catalog())
            assert fresh["accounts"][1]["status"] == "READY"
            assert fresh["active_account_id"] == "paper"
            assert fresh["session_generation"] == 1
        finally:
            runtime.close()

        restarted = _runtime_owner(
            database_path,
            credential_store=DpapiCredentialStore(credential_path, Protector()),
            account_validator=MustNotValidateOnStartup(),
        )
        try:
            catalog = restarted.call(lambda owner: owner.account_catalog())
            assert catalog["accounts"][1]["status"] == "DISCONNECTED"
            assert catalog["active_account_id"] == "paper"
            assert catalog["session_generation"] == 1
            serialized = json.dumps(catalog).lower()
            assert "secret" not in serialized and '"api_key"' not in serialized
        finally:
            restarted.close()


def test_account_post_never_echoes_credentials_on_validation_failure():
    class Runtime:
        def call(self, operation):
            raise AccountValidationError("internal detail must stay private")

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = Runtime()
    response = {}

    def post():
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/accounts",
            data=json.dumps({"display_name": "Main", "api_key": "submitted-key", "api_secret": "submitted-secret"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response.update(json.load(error))

    client = threading.Thread(target=post)
    client.start()
    try:
        server.handle_request()
        client.join(timeout=5)
        assert response == {"ok": False, "error": "bybit_validation_failed"}
        assert "submitted" not in json.dumps(response)
    finally:
        server.server_close()


def test_account_post_rejects_malformed_payload_without_runtime_call():
    class Runtime:
        def call(self, operation):
            raise AssertionError("runtime must not receive malformed credentials")

    server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
    server.runtime = Runtime()
    response = {}

    def post():
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/accounts",
            data=json.dumps({"display_name": "Main", "api_key": "key"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response["status"] = error.code
            response["body"] = json.load(error)

    client = threading.Thread(target=post)
    client.start()
    try:
        server.handle_request()
        client.join(timeout=5)
        assert response == {"status": 400, "body": {"ok": False, "error": "invalid_account_payload"}}
    finally:
        server.server_close()


def test_storage_failure_does_not_add_account():
    class FailingStore:
        def load(self): return ()
        def save(self, accounts): raise CredentialStoreError("write failed")

    class Validator:
        def validate(self, credentials): return ValidatedBybitAccount("MAINNET", False)

    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3", credential_store=FailingStore(), account_validator=Validator())
        try:
            with pytest.raises(CredentialStoreError):
                runtime.call(lambda owner: owner.add_bybit_account("Main", "key", "secret"))
            catalog = runtime.call(lambda owner: owner.account_catalog())
            assert [item["id"] for item in catalog["accounts"]] == ["paper"]
        finally:
            runtime.close()


def test_threaded_http_serializes_concurrent_paper_mutations():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        server = ThreadingHTTPServer(("127.0.0.1", 0), PaperHttpHandler)
        server.runtime = runtime
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        responses: list[dict] = []
        states: list[dict] = []

        def post_market(side: str, action_id: str):
            request = urllib.request.Request(
                f"http://127.0.0.1:{server.server_port}/api/market",
                data=json.dumps({
                    "client_action_id": action_id,
                    "symbol": "BTCUSDT",
                    "side": side,
                    "volume": {"unit": "usdt", "amount": "321"},
                    "sizing_reference_price": "64250",
                    "slippage_type": "Percent",
                    "slippage_value": "0.5",
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request) as result:
                responses.append(json.load(result))

        def get_paper_state():
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/paper-state?symbol=BTCUSDT"
            ) as result:
                states.append(json.load(result))

        clients = [
            threading.Thread(target=post_market, args=("Buy", "concurrent-buy")),
            threading.Thread(target=post_market, args=("Sell", "concurrent-sell")),
            threading.Thread(target=get_paper_state),
        ]
        try:
            for client in clients:
                client.start()
            for client in clients:
                client.join(timeout=5)
            assert all(not client.is_alive() for client in clients)
            assert len(responses) == 2
            assert len(states) == 1
            assert states[0]["ok"] is True
            assert all(item["status"] == "completed" for item in responses), responses
            assert all(item["reason_code"] != "persistence_failure" for item in responses)
        finally:
            server.shutdown()
            server.server_close()
            runtime.close()


def test_public_orderbook_applies_snapshot_and_incremental_delta():
    book = PublicOrderBookBuffer("ONGUSDT", depth=2)

    assert book.apply_message({
        "topic": "orderbook.2.ONGUSDT",
        "type": "snapshot",
        "ts": 1000,
        "cts": 999,
        "data": {
            "u": 10,
            "seq": 20,
            "b": [["0.105", "30"], ["0.104", "20"], ["0.103", "10"]],
            "a": [["0.106", "40"], ["0.107", "50"], ["0.108", "60"]],
        },
    }) == "APPLIED"

    snapshot = book.snapshot_after(-1, timeout=0)
    assert snapshot["bids"] == [
        {"price": "0.105", "size": "30"},
        {"price": "0.104", "size": "20"},
    ]
    assert snapshot["asks"] == [
        {"price": "0.106", "size": "40"},
        {"price": "0.107", "size": "50"},
    ]
    assert snapshot["timestamp"] == 1000
    assert snapshot["matchingEngineCts"] == 999
    assert snapshot["receivedAt"] >= 1000
    assert snapshot["updateId"] == 10
    assert snapshot["sequence"] == 20
    assert snapshot["version"] == 1
    assert snapshot["bestBid"] == "0.105"
    assert snapshot["bestAsk"] == "0.106"

    assert book.apply_message({
        "topic": "orderbook.2.ONGUSDT",
        "type": "delta",
        "ts": 1001,
        "data": {
            "u": 11,
            "seq": 21,
            "b": [["0.105", "0"], ["0.1045", "25"]],
            "a": [["0.106", "45"]],
        },
    }) == "APPLIED"

    updated = book.snapshot_after(snapshot["version"], timeout=0)
    assert updated["bids"] == [
        {"price": "0.1045", "size": "25"},
        {"price": "0.104", "size": "20"},
    ]
    assert updated["asks"][0] == {"price": "0.106", "size": "45"}
    assert updated["updateId"] == 11
    assert updated["sequence"] == 21


def test_orderbook_update_callback_only_publishes_lightweight_identity():
    book = PublicOrderBookBuffer("ONGUSDT", depth=2)
    publisher_thread = threading.get_ident()
    notifications = []

    def enqueue_only(book_update_id: str) -> None:
        notifications.append((book_update_id, threading.get_ident()))

    book.set_update_consumer(enqueue_only)
    assert book.apply_message({
        "topic": "orderbook.2.ONGUSDT",
        "type": "snapshot",
        "ts": 1000,
        "data": {
            "u": 10,
            "seq": 20,
            "b": [["0.105", "30"]],
            "a": [["0.106", "40"]],
        },
    }) == "APPLIED"

    assert notifications == [("ONGUSDT:20:10", publisher_thread)]


def test_book_update_notification_reaches_serialized_owner_thread():
    publisher_thread = threading.get_ident()

    class RecordingRuntime:
        def __init__(self) -> None:
            self.received = []

        def process_orderbook_update(self, book_update_id: str) -> None:
            self.received.append((book_update_id, threading.get_ident()))

        def close(self) -> None:
            return None

    target = RecordingRuntime()
    runtime = SerializedPaperRuntime(lambda: target)
    try:
        runtime.enqueue_book_update("ONGUSDT:21:11")
        runtime.call(lambda _: None)
        assert target.received == [("ONGUSDT:21:11", runtime._thread.ident)]
        assert target.received[0][1] != publisher_thread
    finally:
        runtime.close()


def test_duplicate_book_update_does_not_repeat_partial_limit_fill():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        try:
            def create_limit(owner: PaperRuntime) -> None:
                owner.store.create_paper_limit(
                    client_action_id="runtime-limit-create-1",
                    request_fingerprint="runtime-limit-fingerprint-1",
                    order_id=OrderId("paper-runtime-limit-1"),
                    order_link_id="paper-runtime-link-1",
                    trading_account_id=TradingAccountId("paper"),
                    symbol=Symbol("BTCUSDT"),
                    side=OrderSide.BUY,
                    price=Decimal("65000"),
                    quantity=Decimal("20"),
                    created_at_ms=900,
                )

            runtime.call(create_limit)
            runtime.enqueue_book_update("BTCUSDT:20:10")
            runtime.enqueue_book_update("BTCUSDT:20:10")
            runtime.call(lambda _: None)

            order = runtime.call(
                lambda owner: owner.store.get_paper_limit(
                    "paper-runtime-limit-1", TradingAccountId("paper"),
                )
            )
            assert order is not None
            assert order.filled_quantity == Decimal("10")
            assert order.status == "partially_filled"
            state = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            assert state["state_revision"] == 2
        finally:
            runtime.close()


def test_runtime_matcher_and_state_ignore_foreign_account_limit():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        try:
            def create_limits(owner: PaperRuntime) -> None:
                for suffix, account in (
                    ("active", TradingAccountId("paper")),
                    ("foreign", TradingAccountId("paper-b")),
                ):
                    owner.store.create_paper_limit(
                        client_action_id=f"matcher-{suffix}",
                        request_fingerprint=f"matcher-fingerprint-{suffix}",
                        order_id=OrderId(f"matcher-order-{suffix}"),
                        order_link_id=f"matcher-link-{suffix}",
                        trading_account_id=account,
                        symbol=Symbol("BTCUSDT"),
                        side=OrderSide.BUY,
                        price=Decimal("65000"),
                        quantity=Decimal("1"),
                        created_at_ms=900,
                    )

            runtime.call(create_limits)
            before = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            assert [item["order_id"] for item in before["active_limit_orders"]] == [
                "matcher-order-active"
            ]

            runtime.enqueue_book_update("BTCUSDT:20:10")
            runtime.call(lambda _: None)

            active = runtime.call(lambda owner: owner.store.get_paper_limit(
                "matcher-order-active", TradingAccountId("paper"),
            ))
            foreign = runtime.call(lambda owner: owner.store.get_paper_limit(
                "matcher-order-foreign", TradingAccountId("paper-b"),
            ))
            after = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            assert active is not None and active.status == "filled"
            assert foreign is not None and foreign.status == "open"
            assert after["active_limit_orders"] == []
            assert after["position_quantity"] == "1"
        finally:
            runtime.close()


def test_full_limit_fill_advances_revision_with_order_and_position_atomically():
    with tempfile.TemporaryDirectory() as temp:
        runtime = _runtime_owner(Path(temp) / "paper.sqlite3")
        try:
            def create_limit(owner: PaperRuntime) -> None:
                owner.store.create_paper_limit(
                    client_action_id="runtime-full-create-1",
                    request_fingerprint="runtime-full-fingerprint-1",
                    order_id=OrderId("paper-runtime-full-1"),
                    order_link_id="paper-runtime-full-link-1",
                    trading_account_id=TradingAccountId("paper"),
                    symbol=Symbol("BTCUSDT"),
                    side=OrderSide.BUY,
                    price=Decimal("65000"),
                    quantity=Decimal("5"),
                    created_at_ms=900,
                )

            runtime.call(create_limit)
            runtime.enqueue_book_update("BTCUSDT:20:10")
            runtime.call(lambda _: None)

            state = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            order = runtime.call(
                lambda owner: owner.store.get_paper_limit(
                    "paper-runtime-full-1", TradingAccountId("paper"),
                )
            )
            assert order is not None
            assert order.status == "filled"
            assert state["active_limit_orders"] == []
            assert state["position_quantity"] == "5"
            assert state["state_revision"] == 2
        finally:
            runtime.close()


class _KlineResponse:
    def __init__(self, candles):
        self._candles = candles

    def raise_for_status(self):
        return None

    def json(self):
        return {"retCode": 0, "result": {"list": self._candles}}


class _KlineSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _KlineResponse(self.responses.pop(0))


def test_public_klines_load_history_update_current_and_append_new_interval():
    session = _KlineSession([
        [
            ["600000", "1.1", "1.3", "1.0", "1.2", "10", "12"],
            ["300000", "1.0", "1.2", "0.9", "1.1", "10", "11"],
        ],
        [
            ["900000", "1.25", "1.4", "1.2", "1.35", "10", "13"],
            ["600000", "1.1", "1.35", "1.0", "1.25", "10", "12"],
            ["300000", "1.0", "1.2", "0.9", "1.1", "10", "11"],
        ],
    ])
    klines = PublicKlineBuffer(
        "ONGUSDT", history_limit=1000,
        tick_size=Decimal("0.00001"), session=session,
    )

    klines.refresh()
    initial = klines.snapshot()
    assert [item["startTime"] for item in initial["candles"]] == [300000, 600000]
    assert initial["candles"][-1]["close"] == "1.2"
    assert initial["state"] == "READY"
    assert initial["tickSize"] == "0.00001"

    klines.refresh()
    updated = klines.snapshot()
    assert [item["startTime"] for item in updated["candles"]] == [
        300000, 600000, 900000,
    ]
    assert updated["candles"][-2]["close"] == "1.25"
    assert updated["candles"][-1]["close"] == "1.35"
    assert session.calls[0][1]["params"] == {
        "category": "linear", "symbol": "ONGUSDT",
        "interval": "5", "limit": 1000,
    }


def test_public_klines_accept_only_supported_native_intervals():
    for interval in ("1", "5", "15", "60", "D"):
        session = _KlineSession([[
            ["300000", "1", "2", "0.5", "1.5", "10", "15"],
        ]])
        klines = PublicKlineBuffer(
            "ONGUSDT", interval=interval, session=session,
        )
        klines.refresh()
        assert klines.interval == interval
        assert len(klines.snapshot()["candles"]) == 1
        assert session.calls[0][1]["params"]["interval"] == interval
    for interval in ("15s", "3", "120", "W", ""):
        try:
            PublicKlineBuffer("ONGUSDT", interval=interval)
        except ValueError:
            pass
        else:
            raise AssertionError(f"unexpected accepted interval: {interval}")


def test_public_trade_15s_klines_use_utc_buckets_and_raw_execution_ohlc():
    klines = PublicTradeKlineBuffer(
        "ONGUSDT", history_limit=3, tick_size=Decimal("0.00001"),
    )
    klines.add_trades([
        {"timestamp": 74999, "price": "2"},
        {"timestamp": 61000, "price": "1"},
        {"timestamp": 68000, "price": "3"},
        {"timestamp": 75000, "price": "4"},
        {"timestamp": 89999, "price": "2.5"},
    ])
    snapshot = klines.snapshot()
    assert snapshot["interval"] == "15s"
    assert snapshot["source"] == "BYBIT_PUBLIC_TRADES"
    assert snapshot["candles"] == [
        {"startTime": 60000, "open": "1", "high": "3", "low": "1", "close": "2"},
        {"startTime": 75000, "open": "4", "high": "4", "low": "2.5", "close": "2.5"},
    ]


def test_public_orderbook_accepts_newer_noncontiguous_and_ignores_stale_delta():
    book = PublicOrderBookBuffer("ONGUSDT", depth=50)
    snapshot_message = {
        "topic": "orderbook.50.ONGUSDT",
        "type": "snapshot",
        "data": {"u": 100, "seq": 200, "b": [["1", "2"]], "a": [["2", "3"]]},
    }
    assert book.apply_message(snapshot_message) == "APPLIED"

    assert book.apply_message({
        "topic": "orderbook.50.ONGUSDT",
        "type": "delta",
        "data": {"u": 99, "seq": 199, "b": [["1", "0"]], "a": []},
    }) == "IGNORED"

    current = book.snapshot_after(-1, timeout=0)
    assert current["state"] == "READY"
    assert current["bids"] == [{"price": "1", "size": "2"}]
    assert current["updateId"] == 100

    assert book.apply_message({
        "topic": "orderbook.50.ONGUSDT",
        "type": "delta",
        "data": {"u": 102, "seq": 205, "b": [["1", "4"]], "a": []},
    }) == "APPLIED"
    newer = book.snapshot_after(current["version"], timeout=0)
    assert newer["state"] == "READY"
    assert newer["bids"] == [{"price": "1", "size": "4"}]
    assert newer["updateId"] == 102
    assert newer["sequence"] == 205


def test_public_trades_aggregate_side_window_notional_and_sweep_ticks():
    trades = PublicTradeBuffer(
        "ONGUSDT",
        tick_size=Decimal("0.00001"),
        aggregation_window_ms=50,
    )
    trades.add_trades([
        {"id": "buy-1", "seq": 1, "timestamp": 1000, "symbol": "ONGUSDT",
         "side": "BUY", "price": "1.59477", "quantity": "10"},
        {"id": "buy-2", "seq": 2, "timestamp": 1020, "symbol": "ONGUSDT",
         "side": "BUY", "price": "1.59478", "quantity": "20"},
        {"id": "buy-3", "seq": 3, "timestamp": 1049, "symbol": "ONGUSDT",
         "side": "BUY", "price": "1.59480", "quantity": "30"},
        {"id": "buy-late", "seq": 4, "timestamp": 1100, "symbol": "ONGUSDT",
         "side": "BUY", "price": "1.59479", "quantity": "7"},
        {"id": "sell-1", "seq": 5, "timestamp": 1101, "symbol": "ONGUSDT",
         "side": "SELL", "price": "1.59476", "quantity": "5"},
    ])
    trades.flush()

    aggregates = trades.snapshot_after(0)
    assert [item["side"] for item in aggregates] == ["BUY", "BUY", "SELL"]
    first = aggregates[0]
    assert first["trade_count"] == 3
    assert first["started_at_ms"] == 1000
    assert first["ended_at_ms"] == 1049
    assert first["total_quantity"] == "60"
    assert Decimal(first["total_notional_usdt"]) == (
        Decimal("1.59477") * 10
        + Decimal("1.59478") * 20
        + Decimal("1.59480") * 30
    )
    assert first["first_execution_price"] == "1.59477"
    assert first["last_execution_price"] == "1.59480"
    assert first["sweep_low_price"] == "1.59477"
    assert first["sweep_high_price"] == "1.59480"
    assert first["swept_price_range"] == "0.00003"
    assert first["swept_ticks"] == 4
    assert aggregates[1]["trade_count"] == 1
    assert aggregates[2]["trade_count"] == 1


def test_finalized_trade_captures_immutable_latest_book_descriptor():
    book = PublicOrderBookBuffer("ONGUSDT", depth=2)
    book.apply_message({
        "topic": "orderbook.2.ONGUSDT", "type": "snapshot", "ts": 1000,
        "data": {"cts": 999, "u": 10, "seq": 20,
                 "b": [["1", "2"]], "a": [["2", "3"]]},
    })
    trades = PublicTradeBuffer(
        "ONGUSDT", book_descriptor_provider=book.latest_descriptor,
    )
    trades.add_trades([{
        "id": "trade-1", "seq": 30, "timestamp": 1010,
        "received_at_ms": 1020, "symbol": "ONGUSDT", "side": "BUY",
        "price": "1.5", "quantity": "1",
    }])
    trades.flush()
    aggregate = trades.snapshot_after(0)[0]
    correlation = aggregate["book_correlation"]
    assert correlation == {
        "basis": "LATEST_BACKEND_KNOWN_AT_FINALIZATION",
        "book_version": 1, "update_id": 10, "sequence": 20,
        "exchange_ts_ms": 1000, "matching_engine_cts_ms": 999,
        "backend_received_at_ms": book.snapshot()["receivedAt"],
        "best_bid": "1", "best_ask": "2",
    }
    assert aggregate["first_trade_seq"] == 30
    assert aggregate["last_trade_seq"] == 30
    assert aggregate["backend_first_received_at_ms"] == 1020
    assert aggregate["backend_last_received_at_ms"] == 1020
    assert aggregate["finalized_at_ms"] >= 1020

    book.apply_message({
        "topic": "orderbook.2.ONGUSDT", "type": "delta", "ts": 1030,
        "data": {"u": 11, "seq": 21, "b": [["1", "4"]], "a": []},
    })
    assert aggregate["book_correlation"] == correlation
    assert aggregate["book_correlation"]["book_version"] == 1


def test_finalized_trade_allows_unavailable_book_correlation():
    book = PublicOrderBookBuffer("ONGUSDT", depth=2)
    trades = PublicTradeBuffer(
        "ONGUSDT", book_descriptor_provider=book.latest_descriptor,
    )
    trades.add_trades([{
        "id": "trade-1", "seq": 1, "timestamp": 1000,
        "symbol": "ONGUSDT", "side": "SELL", "price": "1", "quantity": "1",
    }])
    trades.flush()
    assert trades.snapshot_after(0)[0]["book_correlation"] is None


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_market_post_completes_with_one_durable_execution,
            test_workspace_switch_is_ready_before_atomic_swap_and_stale_consumer_cannot_reactivate,
            test_workspace_consumers_follow_active_generation_across_rapid_symbol_return,
            test_inflight_stale_trade_request_fails_closed_after_generation_changes,
            test_workspace_switch_timeout_preserves_ready_active_session_and_provider,
            test_workspace_switch_http_preserves_structured_semantic_failure,
            test_workspace_state_endpoint_is_read_only_and_reports_authoritative_state,
            test_workspace_activation_failure_rolls_back_provider_and_active_generation,
            test_workspace_candidate_wait_does_not_block_current_read_only_consumers,
            test_health_get_returns_exact_paper_status,
            test_threaded_http_serializes_concurrent_paper_mutations,
            test_public_orderbook_applies_snapshot_and_incremental_delta,
            test_public_orderbook_accepts_newer_noncontiguous_and_ignores_stale_delta,
            test_public_klines_load_history_update_current_and_append_new_interval,
            test_public_klines_accept_only_supported_native_intervals,
            test_public_trade_15s_klines_use_utc_buckets_and_raw_execution_ohlc,
            test_public_trades_aggregate_side_window_notional_and_sweep_ticks,
            test_finalized_trade_captures_immutable_latest_book_descriptor,
            test_finalized_trade_allows_unavailable_book_correlation,
        )
    )
