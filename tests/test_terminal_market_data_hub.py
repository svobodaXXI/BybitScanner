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
    disconnects = []
    context.add_disconnect_listener(
        "test", lambda generation, reason: disconnects.append((generation, reason)),
    )
    hub.start()
    assert second.subscribed.wait(timeout=1)

    assert first.sent[0]["args"] == ["orderbook.1000.BTCUSDT", "publicTrade.BTCUSDT"]
    assert second.sent[0]["args"] == first.sent[0]["args"]
    assert context.reconnect_count == 1
    assert disconnects == [(1, "OSError")]
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


def test_symbol_context_fans_out_updates_to_independent_named_listeners():
    context = _context("BTCUSDT", Decimal("0.01"))
    received_a = []
    received_b = []
    context.add_update_listener("a", received_a.append)
    context.add_update_listener("b", received_b.append)
    assert context.public_orderbook.consumer == context._dispatch_update
    context._dispatch_update("BTCUSDT:1:1")

    assert received_a == ["BTCUSDT:1:1"]
    assert received_b == ["BTCUSDT:1:1"]

    context.remove_update_listener("a")
    assert context.has_update_listeners() is True
    assert context.public_orderbook.consumer == context._dispatch_update
    context._dispatch_update("BTCUSDT:2:2")
    assert received_a == ["BTCUSDT:1:1"]
    assert received_b == ["BTCUSDT:1:1", "BTCUSDT:2:2"]

    context.remove_update_listener("b")
    assert context.has_update_listeners() is False
    assert context.public_orderbook.consumer is None


def test_symbol_context_fans_out_disconnect_boundaries():
    context = _context("BTCUSDT", Decimal("0.01"))
    received_a = []
    received_b = []
    context.add_disconnect_listener(
        "a", lambda generation, reason: received_a.append((generation, reason)),
    )
    context.add_disconnect_listener(
        "b", lambda generation, reason: received_b.append((generation, reason)),
    )

    context._dispatch_disconnect(3, "OSError")

    assert received_a == [(3, "OSError")]
    assert received_b == [(3, "OSError")]
    assert context.has_listeners() is True

    context.remove_disconnect_listener("a")
    context.remove_disconnect_listener("b")
    assert context.has_listeners() is False


def test_symbol_context_listener_failure_does_not_block_sibling_listener():
    context = _context("BTCUSDT", Decimal("0.01"))
    received = []

    def failing(_book_update_id):
        raise RuntimeError("boom")

    context.add_update_listener("failing", failing)
    context.add_update_listener("ok", received.append)
    context._dispatch_update("BTCUSDT:1:1")

    assert received == ["BTCUSDT:1:1"]


def test_hub_discard_is_deferred_while_an_independent_listener_remains():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *args, **kwargs: None)
    context = hub.subscribe("BTCUSDT")
    context.add_update_listener("robot-protection", lambda _book_update_id: None)

    hub.discard(context)

    assert hub.has_context("BTCUSDT") is True
    assert context.public_orderbook.closed is False

    context.remove_update_listener("robot-protection")
    hub.discard(context)

    assert hub.has_context("BTCUSDT") is False
    assert context.public_orderbook.closed is True


def test_scanner_impulse_source_status_reports_existing_contexts_only_without_orders():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *args, **kwargs: None)
    btc = hub.subscribe("BTCUSDT")
    hub.subscribe("ONGUSDT")
    assert btc.impulse_observation.observe({
        "topic": "publicTrade.BTCUSDT",
        "data": [{"i": "print1", "T": 1000, "seq": 123, "S": "Buy",
                  "p": "100", "v": "2", "s": "BTCUSDT"}],
    })
    before = hub.list_contexts()
    snapshot = hub.impulse_source_diagnostics()
    assert snapshot["scope"] == "EXISTING_HUB_SUBSCRIPTIONS_ONLY"
    assert snapshot["subscribed_contexts"] == 2
    assert snapshot["reported_contexts"] == 2
    assert snapshot["truncated"] is False
    assert snapshot["source_complete"] is False
    assert snapshot["trading_authorized"] is False
    assert hub.list_contexts() == before  # no new subscriptions
    rows = {row["symbol"]: row for row in snapshot["contexts"]}
    assert rows["BTCUSDT"]["observed_prints"] == 1
    assert rows["BTCUSDT"]["last_cross_sequence"] == 123
    assert rows["BTCUSDT"]["continuity"] == "UNPROVEN"
    assert rows["BTCUSDT"]["trading_authorized"] is False
    assert rows["ONGUSDT"]["observed_prints"] == 0
    assert "prints" not in rows["BTCUSDT"]  # no raw execution exposure
    bounded = hub.impulse_source_diagnostics(limit=1)
    assert bounded["truncated"] is True
    assert bounded["reported_contexts"] == 1
    for invalid in (0, 33, True):
        try:
            hub.impulse_source_diagnostics(limit=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid context limit accepted")
    btc.impulse_observation.mark_gap()
    after = hub.impulse_source_diagnostics()
    assert after["contexts"][0]["observed_prints"] == 0
    assert after["contexts"][0]["source_generation"] == 1
    assert after["contexts"][0]["continuity"] == "UNPROVEN"
    hub.close()


def test_flow_only_probe_uses_same_ws_no_book_and_no_protection_callback():
    ws = _WebSocket()
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: ws)
    try:
        hub._ws = ws  # simulate the already-owned WS, without starting threads
        passive = hub.subscribe_flow_only("BTCUSDT")
        assert passive.symbol == "BTCUSDT"
        assert hub.list_contexts() == ()
        assert hub.list_flow_contexts() == (passive,)
        assert passive.impulse_observation.snapshot()["buffer_capacity"] == 1000
        assert ws.sent == [{
            "op": "subscribe", "req_id": "flow:BTCUSDT",
            "args": ["publicTrade.BTCUSDT"],
        }]
        assert hub.subscribe_flow_only("ONGUSDT") is None  # hard budget 1
        hub._dispatch({
            "op": "subscribe", "req_id": "flow:BTCUSDT", "success": True,
        })
        hub._dispatch({
            "topic": "publicTrade.BTCUSDT",
            "data": [{"i": "1", "s": "BTCUSDT", "T": 1000, "seq": 1,
                      "S": "Buy", "p": "100", "v": "1"}],
        })
        assert passive.impulse_observation.snapshot()["observed_prints"] == 1
        assert passive.trade_bootstrap_complete is True
        assert not any("orderbook" in t for row in ws.sent
                       for t in row["args"])
        assert hub.release_flow_only("BTCUSDT") is True
        assert ws.sent[-1]["args"] == ["publicTrade.BTCUSDT"]
        assert ws.sent[-1]["op"] == "unsubscribe"
        assert hub.list_flow_contexts() == ()
        assert hub.list_contexts() == ()
    finally:
        hub.close()


def test_protection_upgrades_passive_source_without_duplicate_trade_or_unsubscribe():
    ws = _WebSocket()
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: ws)
    try:
        hub._ws = ws
        passive = hub.subscribe_flow_only("BTCUSDT")
        hub._dispatch({
            "op": "subscribe", "req_id": "flow:BTCUSDT", "success": True,
        })
        hub._dispatch({
            "topic": "publicTrade.BTCUSDT",
            "data": [{"i": "before-cover", "s": "BTCUSDT", "T": 1000,
                      "seq": 1, "S": "Buy", "p": "100", "v": "1"}],
        })
        book = hub.subscribe("BTCUSDT")  # protection uses canonical subscribe
        assert hub.list_contexts() == (book,)
        assert hub.list_flow_contexts() == (book,)
        assert book.impulse_observation is passive.impulse_observation
        assert book.impulse_observation.snapshot()["observed_prints"] == 1
        assert book.trade_bootstrap_complete is True
        assert ws.sent[-1]["args"] == ["orderbook.1000.BTCUSDT"]
        assert not any(row["op"] == "unsubscribe" for row in ws.sent)
        assert hub.release_flow_only("BTCUSDT") is False
        # Existing protected book listener cannot be removed by flow observer.
        observed = []
        book.add_update_listener("robot-protection", observed.append)
        hub._dispatch({
            "topic": "orderbook.1000.BTCUSDT", "type": "snapshot",
            "data": {"u": 10, "seq": 10, "b": [["100", "1"]],
                     "a": [["101", "1"]]},
            "ts": 5000,
        })
        assert len(book.public_orderbook.messages) == 1
    finally:
        hub.close()



def test_capture_only_probe_preserves_full_protection_context_without_fake_l2():
    """A protected full context must not be converted into passive raw L2."""
    ws = _WebSocket()
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: ws)
    try:
        hub._ws = ws
        protected = hub.subscribe("BTCUSDT")
        callbacks = []
        protected.add_update_listener("robot-protection", callbacks.append)
        before = tuple(ws.sent)

        # A capture-only observer sees the existing full context. It must
        # not replace its protected book or create a second book subscriber.
        assert hub.subscribe_flow_only("BTCUSDT", capture_book=True) is protected
        assert hub.list_flow_contexts() == hub.list_contexts() == (protected,)
        assert not hasattr(protected, "capture_book")
        assert not hasattr(protected, "book_frames")
        assert tuple(ws.sent) == before
        assert hub.release_flow_only("BTCUSDT") is False

        protected._dispatch_update("BTCUSDT:protected")
        assert callbacks == ["BTCUSDT:protected"]
        assert protected.public_orderbook.closed is False
    finally:
        hub.close()


def test_private_protected_ingress_witness_requires_real_snapshot_and_no_new_topic():
    """Research reads existing protected ingress; no second book or WS lease."""
    ws = _WebSocket()
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: ws)
    try:
        hub._ws = ws
        assert hub.begin_protected_research_capture("BTCUSDT") is None
        assert hub.list_contexts() == ()
        full = hub.subscribe("BTCUSDT")
        seen = []
        full.add_update_listener("robot-protection", seen.append)
        before_topics = tuple(ws.sent)
        witness = hub.begin_protected_research_capture("BTCUSDT")
        assert witness is not None and witness.capture_book is True
        assert witness.impulse_observation is full.impulse_observation
        assert hub.begin_protected_research_capture("BTCUSDT") is witness
        assert hub.begin_protected_research_capture("ONGUSDT") is None
        assert hub.subscribe_flow_only("BTCUSDT", capture_book=True) is full
        assert hub.list_flow_contexts() == hub.list_contexts() == (full,)
        assert not hasattr(full, "book_frames")  # no second trading book
        assert tuple(ws.sent) == before_topics

        # An orphan delta cannot bootstrap L2 history.
        def frame(kind, uid):
            return {
                "topic": "orderbook.1000.BTCUSDT", "type": kind,
                "data": {"u": uid, "seq": uid,
                         "b": [["100", "1"]], "a": [["101", "1"]]},
                "cts": 1234 + uid, "ts": 1234 + uid,
            }
        hub._dispatch(frame("delta", 9))
        assert tuple(witness.book_frames) == ()
        assert [f["data"]["u"] for _, f in witness.rest_anchor_candidates] == [9]
        hub._dispatch(frame("snapshot", 10))
        assert tuple(witness.rest_anchor_candidates) == ()
        hub._dispatch(frame("delta", 11))
        assert [item[1]["data"]["u"] for item in witness.book_frames] == [10, 11]
        assert all(isinstance(received_ms, int) and received_ms > 0
                   for received_ms, _ in witness.book_frames)
        assert len(full.public_orderbook.messages) == 3
        full._dispatch_update("robot-still-owned")
        assert seen == ["robot-still-owned"]
        assert hub.end_protected_research_capture("BTCUSDT") is True
        assert tuple(witness.book_frames) == ()
        assert tuple(witness.rest_anchor_candidates) == ()
        assert hub.end_protected_research_capture("BTCUSDT") is False
        hub._dispatch(frame("snapshot", 12))
        assert tuple(witness.book_frames) == ()
        assert full.public_orderbook.closed is False
        assert tuple(ws.sent) == before_topics
    finally:
        hub.close()


def test_private_protected_capture_invalidates_gap_and_overflow():
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: None)
    try:
        hub.subscribe("BTCUSDT")
        witness = hub.begin_protected_research_capture("BTCUSDT")
        assert witness is not None
        snapshot = {"type": "snapshot"}
        delta = {"type": "delta"}
        witness.on_book(100, snapshot, "APPLIED")
        assert len(witness.book_frames) == 1
        witness.reset()  # disconnect must not retain previous generation
        witness.on_book(101, delta, "APPLIED")
        assert not witness.book_frames
        assert len(witness.rest_anchor_candidates) == 1
        witness.reset()
        assert not witness.rest_anchor_candidates
        witness.on_book(102, snapshot, "APPLIED")
        for n in range(1024):
            witness.on_book(103 + n, delta, "APPLIED")
        assert not witness.book_frames  # do not evict the initial snapshot
        witness.on_book(1128, delta, "APPLIED")
        assert not witness.book_frames
        witness.on_book(1129, snapshot, "APPLIED")
        assert len(witness.book_frames) == 1
    finally:
        hub.close()


def test_research_rest_tape_snapshot_is_atomic_and_epoch_fenced():
    """A delayed REST response cannot match a pre-reset transport tape."""
    hub = MarketDataHub(_Registry(), _context, connection_factory=lambda *_a, **_k: None)
    try:
        protected = hub.subscribe("BTCUSDT")
        witness = hub.begin_protected_research_capture("BTCUSDT")
        assert witness is not None
        a = witness.rest_anchor_tape_snapshot()
        assert a == {
            "symbol": "BTCUSDT", "depth": 1000, "epoch": 0,
            "active": True, "frames": (), "source_complete": False,
            "trading_authorized": False,
        }
        one = {"topic": "orderbook.1000.BTCUSDT", "type": "delta",
               "data": {"s": "BTCUSDT", "u": 7, "seq": 8}}
        witness.on_book(102, one, "APPLIED")
        before = witness.rest_anchor_tape_snapshot()
        assert before["epoch"] == a["epoch"]
        assert before["frames"] == ((102, one),)
        # A consumer must not rewrite the retained raw tape via snapshot
        # aliases, including dictionaries nested inside vendor data.
        tampered = witness.rest_anchor_tape_snapshot()
        tampered["frames"][0][1]["data"]["u"] = 999
        assert one["data"]["u"] == 7
        assert witness.rest_anchor_tape_snapshot()["frames"] == ((102, one),)
        witness.reset()  # WS reconnection/host boundary
        after = witness.rest_anchor_tape_snapshot()
        assert after["epoch"] > before["epoch"]
        assert after["frames"] == ()
        assert before["frames"] == ((102, one),)  # structural copy stable
        witness.on_book(103, one, "APPLIED")
        assert witness.rest_anchor_tape_snapshot()["epoch"] == after["epoch"]
        witness.on_book(104, {"type": "delta"}, "IGNORED")
        ignored = witness.rest_anchor_tape_snapshot()
        assert ignored["frames"] == ()
        assert ignored["epoch"] > after["epoch"]
        witness.on_book(105, one, "APPLIED")
        source_epoch = witness.rest_anchor_tape_snapshot()["epoch"]
        for i in range(1024):
            witness.on_book(106+i, one, "APPLIED")
        overflow = witness.rest_anchor_tape_snapshot()
        assert overflow["frames"] == ()
        assert overflow["epoch"] > source_epoch
        witness.on_book(1130, one, "APPLIED")
        assert witness.rest_anchor_tape_snapshot()["epoch"] == overflow["epoch"]
        assert hub.end_protected_research_capture("BTCUSDT")
        closed = witness.rest_anchor_tape_snapshot()
        assert closed["active"] is False and closed["frames"] == ()
        assert closed["epoch"] > overflow["epoch"]
        assert protected.public_orderbook.closed is False
    finally:
        hub.close()


TESTS = (
    test_hub_uses_one_connection_for_multiple_reusable_symbol_contexts,
    test_hub_rejects_unsupported_symbol_without_creating_context,
    test_subscription_ack_makes_quiet_trades_bootstrap_explicitly_valid,
    test_hub_reconnects_and_resubscribes_existing_contexts,
    test_workspace_switch_reuses_hub_context_and_preserves_previous_context,
    test_symbol_context_fans_out_updates_to_independent_named_listeners,
    test_symbol_context_fans_out_disconnect_boundaries,
    test_symbol_context_listener_failure_does_not_block_sibling_listener,
    test_hub_discard_is_deferred_while_an_independent_listener_remains,
    test_scanner_impulse_source_status_reports_existing_contexts_only_without_orders,
    test_flow_only_probe_uses_same_ws_no_book_and_no_protection_callback,
    test_protection_upgrades_passive_source_without_duplicate_trade_or_unsubscribe,
    test_capture_only_probe_preserves_full_protection_context_without_fake_l2,
    test_private_protected_ingress_witness_requires_real_snapshot_and_no_new_topic,
    test_private_protected_capture_invalidates_gap_and_overflow,
    test_research_rest_tape_snapshot_is_atomic_and_epoch_fenced,
)


def load_tests(loader, tests, pattern):
    # The existing PAPER CI invokes this named suite explicitly.
    # Include the pure REST/WS research source matcher without touching
    # protected runtime test runners or broad workflow configuration.
    from tests.test_research_l2_rest_anchor import RestWsL2AnchorTests
    combined = unittest.TestSuite(unittest.FunctionTestCase(test) for test in TESTS)
    combined.addTests(loader.loadTestsFromTestCase(RestWsL2AnchorTests))
    return combined


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"market data hub tests: {len(TESTS)} passed")
