import json
import threading
import time
import unittest
from decimal import Decimal

import websocket

from terminal.market_data.hub import MarketDataHub, SymbolContext
from terminal.runtime.paper_http_server import WorkspaceMarketDataManager


class _Instrument:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.strip().upper()
        self.tick_size = Decimal("0.01")


class _Registry:
    def get(self, symbol: str) -> _Instrument:
        normalized = symbol.strip().upper()
        if normalized not in {"BTCUSDT", "ONGUSDT"}:
            raise LookupError(normalized)
        return _Instrument(normalized)


class _Book:
    depth = 1000

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.messages = []
        self.state = "DISCONNECTED"
        self.closed = False
        self.consumer = None

    def apply_message(self, message):
        self.messages.append(message)
        self.state = "READY"
        return "APPLIED"

    def wait_until_ready(self, timeout):
        return self.state == "READY"

    def set_update_consumer(self, consumer):
        self.consumer = consumer

    def snapshot(self):
        ready = self.state == "READY"
        return {
            "state": self.state, "receivedAt": 1, "sequence": 2, "version": 3,
            "updateId": 4, "bids": [{"price": "1", "size": "1"}] if ready else [],
            "asks": [{"price": "2", "size": "1"}] if ready else [],
        }

    def mark_connecting(self):
        self.state = "CONNECTING"

    def mark_disconnected(self):
        self.state = "DISCONNECTED"

    def close(self):
        self.closed = True


class _Trades:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.messages = []
        self.closed = False

    def apply_message(self, message):
        self.messages.append(message)
        return "APPLIED"

    def snapshot_after(self, after):
        return []

    def close(self):
        self.closed = True


class _Kline:
    def __init__(self) -> None:
        self.closed = False

    def snapshot(self):
        return {"receivedAt": 4, "state": "READY", "candles": [{"startTime": 1}]}

    def close(self):
        self.closed = True


def _context(symbol: str, tick_size: Decimal) -> SymbolContext:
    assert tick_size == Decimal("0.01")
    return SymbolContext(symbol, _Book(symbol), _Trades(symbol), {"5": _Kline()})


class _WebSocket:
    def __init__(self) -> None:
        self.sent = []
        self.closed = False
        self.subscribed = threading.Event()

    def send(self, payload):
        self.sent.append(json.loads(payload))
        self.subscribed.set()

    def recv(self):
        time.sleep(0.005)
        raise websocket.WebSocketTimeoutException()

    def close(self):
        self.closed = True


class _FailingWebSocket(_WebSocket):
    def recv(self):
        raise OSError("connection lost")


class _Provider:
    def __init__(self, buffer) -> None:
        self.buffer = buffer

    def set_buffer(self, buffer) -> None:
        self.buffer = buffer


class _Runtime:
    def enqueue_book_update(self, book_update_id):
        return None


def test_hub_uses_one_connection_for_multiple_reusable_symbol_contexts():
    ws = _WebSocket()
    connection_calls = []

    def connect(url, timeout):
        connection_calls.append((url, timeout))
        return ws

    hub = MarketDataHub(_Registry(), _context, connection_factory=connect)
    btc = hub.subscribe("btcusdt")
    ong = hub.subscribe("ONGUSDT")
    assert hub.subscribe("BTCUSDT") is btc

    hub.start()
    assert ws.subscribed.wait(timeout=1)
    deadline = time.time() + 1
    while len(ws.sent) < 2 and time.time() < deadline:
        time.sleep(0.005)

    assert len(connection_calls) == 1
    assert {topic for item in ws.sent for topic in item["args"]} == {
        "orderbook.1000.BTCUSDT", "publicTrade.BTCUSDT",
        "orderbook.1000.ONGUSDT", "publicTrade.ONGUSDT",
    }
    assert hub.list_contexts() == (btc, ong)

    hub._dispatch({"topic": "orderbook.1000.BTCUSDT", "type": "snapshot", "data": {}})
    hub._dispatch({"topic": "publicTrade.ONGUSDT", "data": []})
    assert len(btc.public_orderbook.messages) == 1
    assert len(ong.public_trades.messages) == 1
    assert not ong.public_orderbook.messages
    assert not btc.public_trades.messages

    hub.close()
    assert ws.closed is True
    assert btc.public_orderbook.closed is True
    assert ong.public_trades.closed is True


def test_hub_rejects_unsupported_symbol_without_creating_context():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *args, **kwargs: None)
    try:
        hub.subscribe("ETHUSDT")
    except LookupError:
        pass
    else:
        raise AssertionError("unsupported symbol context was created")
    assert hub.list_contexts() == ()


def test_subscription_ack_makes_quiet_trades_bootstrap_explicitly_valid():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *args, **kwargs: None)
    context = hub.subscribe("BTCUSDT")
    assert context.trade_bootstrap_complete is False

    hub._dispatch({
        "op": "subscribe", "req_id": "workspace:BTCUSDT", "success": True,
    })

    assert context.trades_subscription_state == "SUBSCRIBED"
    assert context.trade_bootstrap_complete is True
    assert context.public_trades.snapshot_after(0) == []
    hub.close()


def test_hub_reconnects_and_resubscribes_existing_contexts():
    first = _FailingWebSocket()
    second = _WebSocket()
    sockets = iter((first, second))
    hub = MarketDataHub(
        _Registry(), _context,
        connection_factory=lambda url, timeout: next(sockets),
        reconnect_delay=0,
    )
    context = hub.subscribe("BTCUSDT")
    hub.start()
    assert second.subscribed.wait(timeout=1)

    assert first.sent[0]["args"] == ["orderbook.1000.BTCUSDT", "publicTrade.BTCUSDT"]
    assert second.sent[0]["args"] == first.sent[0]["args"]
    assert context.reconnect_count == 1
    assert context.subscription_state == "SUBSCRIBING"
    hub._dispatch({"topic": "orderbook.1000.BTCUSDT", "type": "snapshot", "data": {}})
    assert context.subscription_state == "SUBSCRIBED"
    hub.close()


def test_workspace_switch_reuses_hub_context_and_preserves_previous_context():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *args, **kwargs: None)
    btc = hub.subscribe("BTCUSDT")
    ong = hub.subscribe("ONGUSDT")
    btc.public_orderbook.state = "READY"
    ong.public_orderbook.state = "READY"
    for context in (btc, ong):
        context.trades_subscription_state = "SUBSCRIBED"
        context.trade_bootstrap_complete = True
    provider = _Provider(btc.public_orderbook)
    manager = WorkspaceMarketDataManager(
        _Registry(), provider, _Runtime(), btc, hub=hub, readiness_timeout=0.01,
    )
    btc.public_orderbook.set_update_consumer(_Runtime().enqueue_book_update)

    switched = manager.switch("ongusdt")

    assert switched is ong
    assert manager.get_active("ONGUSDT") == (ong, 2)
    assert provider.buffer is ong.public_orderbook
    assert btc.public_orderbook.closed is False
    assert btc.public_orderbook.consumer is None
    assert ong.public_orderbook.consumer is not None
    assert hub.subscribe("BTCUSDT") is btc
    manager.close()


TESTS = (
    test_hub_uses_one_connection_for_multiple_reusable_symbol_contexts,
    test_hub_rejects_unsupported_symbol_without_creating_context,
    test_subscription_ack_makes_quiet_trades_bootstrap_explicitly_valid,
    test_hub_reconnects_and_resubscribes_existing_contexts,
    test_workspace_switch_reuses_hub_context_and_preserves_previous_context,
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(test) for test in TESTS)


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"market data hub tests: {len(TESTS)} passed")
