import threading
import time
import unittest

from terminal.market_data.hub import SymbolContext
from terminal.market_data.workspace_controller import WorkspaceController
from terminal.market_data.workspace_errors import (
    UnsupportedWorkspaceInstrument,
    UpstreamWorkspaceMarketDataFailure,
    WorkspaceCandidateNotReady,
    WorkspaceInstrumentBootstrapFailure,
)


class _Book:
    depth = 1000

    def __init__(self, symbol: str, ready: bool = False) -> None:
        self.symbol = symbol
        self.ready = ready
        self.consumer = None
        self.closed = False

    def snapshot(self):
        if not self.ready:
            return {"state": "CONNECTING", "bids": [], "asks": [], "version": 0, "updateId": 0, "sequence": 0}
        return {
            "state": "READY", "bids": [{"price": "1", "size": "1"}],
            "asks": [{"price": "2", "size": "1"}], "version": 1,
            "updateId": 2, "sequence": 3, "receivedAt": 4,
        }

    def wait_until_ready(self, timeout):
        return self.ready

    def set_update_consumer(self, consumer):
        self.consumer = consumer

    def close(self):
        self.closed = True


class _Trades:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.closed = False

    def snapshot_after(self, after):
        return []

    def close(self):
        self.closed = True


class _Candles:
    def __init__(self, ready: bool = False) -> None:
        self.ready = ready
        self.closed = False

    def snapshot(self):
        return {
            "state": "READY" if self.ready else "CONNECTING",
            "candles": [{"startTime": 1}] if self.ready else [],
            "receivedAt": 1,
        }

    def close(self):
        self.closed = True


def _context(symbol: str, ready: bool = False) -> SymbolContext:
    context = SymbolContext(symbol, _Book(symbol, ready), _Trades(symbol), {"5": _Candles(ready)})
    if ready:
        context.subscription_state = "SUBSCRIBED"
        context.book_subscription_state = "SUBSCRIBED"
        context.trades_subscription_state = "SUBSCRIBED"
        context.trade_bootstrap_complete = True
    return context


def _make_ready(context: SymbolContext) -> None:
    context.public_orderbook.ready = True
    context.public_klines["5"].ready = True
    context.subscription_state = "SUBSCRIBED"
    context.book_subscription_state = "SUBSCRIBED"
    context.trades_subscription_state = "SUBSCRIBED"
    context.trade_bootstrap_complete = True


class _Hub:
    def __init__(self, initial: SymbolContext, candidates: dict[str, SymbolContext]) -> None:
        self.contexts = {initial.symbol: initial}
        self.candidates = candidates
        self.discarded = []

    def has_context(self, symbol: str) -> bool:
        return symbol.strip().upper() in self.contexts

    def subscribe(self, symbol: str) -> SymbolContext:
        normalized = symbol.strip().upper()
        if normalized in self.contexts:
            return self.contexts[normalized]
        if normalized not in self.candidates:
            raise LookupError(normalized)
        context = self.candidates[normalized]
        self.contexts[normalized] = context
        return context

    def discard(self, context: SymbolContext) -> None:
        if self.contexts.get(context.symbol) is context:
            del self.contexts[context.symbol]
        self.discarded.append(context)
        context.close()


def test_pending_candidate_does_not_replace_active_until_composite_ready():
    btc = _context("BTCUSDT", True)
    ong = _context("ONGUSDT", False)
    hub = _Hub(btc, {"ONGUSDT": ong})
    activations = []
    controller = WorkspaceController(hub, btc, lambda old, new: activations.append((old, new)), poll_interval=0.001)
    assert controller.ensure_initial_ready(0.01) is btc
    result = {}
    switched = threading.Thread(target=lambda: result.setdefault("context", controller.switch("ONGUSDT", 1)))
    switched.start()
    deadline = time.time() + 1
    while controller.state().pending_candidate is None and time.time() < deadline:
        time.sleep(0.001)

    state = controller.state()
    assert state.requested_symbol == "ONGUSDT"
    assert state.active_symbol == "BTCUSDT"
    assert state.active_generation == 1
    assert state.switch_state == "SYNCING"
    assert controller.get_active("BTCUSDT") == (btc, 1)
    diagnostic = controller.diagnostics()
    assert diagnostic["requested_symbol"] == "ONGUSDT"
    assert diagnostic["active_symbol"] == "BTCUSDT"
    assert diagnostic["active_generation"] == 1
    assert diagnostic["switch_state"] == "SYNCING"
    assert diagnostic["pending_symbol"] == "ONGUSDT"
    assert diagnostic["readiness"]["ready"] is True
    assert diagnostic["upstream"]["subscription_state"] == "SUBSCRIBED"

    _make_ready(ong)
    switched.join(timeout=1)
    assert result["context"] is ong
    assert controller.get_active("ONGUSDT") == (ong, 2)
    assert activations == [(btc, ong)]
    assert controller.is_current(btc, 1) is False
    assert controller.is_current(ong, 2) is True


def test_quiet_trades_are_ready_after_subscription_and_empty_bootstrap():
    context = _context("BTCUSDT", True)
    controller = WorkspaceController(_Hub(context, {}), context, lambda old, new: None)
    assert context.public_trades.snapshot_after(0) == []
    readiness = controller.readiness(context)
    assert readiness.ready is True
    assert readiness.trades_ready is True


def test_initial_workspace_fails_closed_until_composite_ready():
    context = _context("BTCUSDT", False)
    controller = WorkspaceController(
        _Hub(context, {}), context, lambda old, new: None, poll_interval=0.001,
    )
    assert controller.state().switch_state == "SYNCING"
    try:
        controller.ensure_initial_ready(0.005)
    except WorkspaceCandidateNotReady as error:
        assert error.code == "candidate_not_ready"
        assert error.active_symbol == "BTCUSDT"
    else:
        raise AssertionError("unready initial Workspace was accepted")
    assert controller.state().switch_state == "FAILED"
    assert controller.state().last_switch_error.code == "candidate_not_ready"
    _make_ready(context)
    assert controller.ensure_initial_ready(0.01) is context
    assert controller.state().switch_state == "READY"


def test_timeout_preserves_previous_and_discards_new_candidate():
    btc = _context("BTCUSDT", True)
    ong = _context("ONGUSDT", False)
    hub = _Hub(btc, {"ONGUSDT": ong})
    controller = WorkspaceController(hub, btc, lambda old, new: None, poll_interval=0.001)

    try:
        controller.switch("ONGUSDT", 0.005)
    except WorkspaceCandidateNotReady as error:
        assert error.requested_symbol == "ONGUSDT"
        assert error.active_symbol == "BTCUSDT"
    else:
        raise AssertionError("unready candidate became active")

    state = controller.state()
    assert state.active_symbol == "BTCUSDT"
    assert state.active_generation == 1
    assert state.switch_state == "FAILED"
    assert state.pending_candidate is None
    assert state.last_switch_error.code == "candidate_not_ready"
    diagnostic = controller.diagnostics()
    assert diagnostic["requested_symbol"] == "ONGUSDT"
    assert diagnostic["active_symbol"] == "BTCUSDT"
    assert diagnostic["active_generation"] == 1
    assert diagnostic["pending_symbol"] is None
    assert diagnostic["last_error"] == {
        "code": "candidate_not_ready",
        "stage": "candidate_readiness",
        "requested_symbol": "ONGUSDT",
        "active_symbol": "BTCUSDT",
        "retryable": True,
        "request_id": None,
        "message": "Workspace candidate did not reach composite readiness",
    }
    assert hub.discarded == [ong]
    assert controller.is_current(btc, 1) is True


def test_malformed_symbol_and_book_identity_fail_closed():
    btc = _context("BTCUSDT", True)
    controller = WorkspaceController(_Hub(btc, {}), btc, lambda old, new: None)
    for symbol in (None, "   "):
        try:
            controller.switch(symbol, 0.01)
        except UnsupportedWorkspaceInstrument:
            pass
        else:
            raise AssertionError("malformed symbol was accepted")
    try:
        controller.switch("ETHUSDT", 0.01)
    except UnsupportedWorkspaceInstrument as error:
        assert error.envelope(request_id="request-1") == {
            "code": "unsupported_instrument",
            "stage": "instrument_lookup",
            "requested_symbol": "ETHUSDT",
            "active_symbol": "BTCUSDT",
            "retryable": False,
            "request_id": "request-1",
            "message": "Unsupported Workspace instrument: ETHUSDT",
        }
    else:
        raise AssertionError("unsupported symbol was accepted")
    assert controller.state().switch_state == "FAILED"
    assert controller.state().last_switch_error.code == "unsupported_instrument"
    btc.public_orderbook.snapshot = lambda: {
        "state": "READY", "bids": [1], "asks": [2],
        "version": "bad", "updateId": 2, "sequence": 3,
    }
    assert controller.readiness(btc).book_ready is False


def test_bootstrap_and_activation_failures_preserve_previous_active():
    btc = _context("BTCUSDT", True)

    class _FailingHub(_Hub):
        def subscribe(self, symbol: str) -> SymbolContext:
            raise RuntimeError("socket bootstrap failed")

    controller = WorkspaceController(_FailingHub(btc, {}), btc, lambda old, new: None)
    try:
        controller.switch("ETHUSDT", 0.01)
    except WorkspaceInstrumentBootstrapFailure as error:
        assert error.code == "instrument_bootstrap_failure"
        assert error.stage == "instrument_bootstrap"
    else:
        raise AssertionError("bootstrap failure lost its semantic class")
    assert controller.get_active("BTCUSDT") == (btc, 1)

    ong = _context("ONGUSDT", True)
    hub = _Hub(btc, {"ONGUSDT": ong})
    controller = WorkspaceController(
        hub, btc, lambda old, new: (_ for _ in ()).throw(RuntimeError("provider failed")),
    )
    try:
        controller.switch("ONGUSDT", 0.01)
    except UpstreamWorkspaceMarketDataFailure as error:
        assert error.code == "upstream_market_data_failure"
        assert error.active_symbol == "BTCUSDT"
    else:
        raise AssertionError("activation failure lost its semantic class")
    assert controller.get_active("BTCUSDT") == (btc, 1)
    assert controller.state().active_generation == 1


def test_warm_context_reuse_and_bounded_eviction():
    btc = _context("BTCUSDT", True)
    ong = _context("ONGUSDT", True)
    eth = _context("ETHUSDT", True)
    hub = _Hub(btc, {"ONGUSDT": ong, "ETHUSDT": eth})
    controller = WorkspaceController(
        hub, btc, lambda old, new: None,
        warm_context_limit=1, warm_grace_seconds=60,
    )

    assert controller.switch("ONGUSDT", 0.01) is ong
    assert controller.switch("BTCUSDT", 0.01) is btc
    assert controller.switch("ETHUSDT", 0.01) is eth

    assert btc.generation == 3
    assert eth.generation == 4
    assert ong in hub.discarded
    assert btc not in hub.discarded


def test_expired_warm_context_is_discarded_before_next_switch_decision():
    btc = _context("BTCUSDT", True)
    ong = _context("ONGUSDT", True)
    hub = _Hub(btc, {"ONGUSDT": ong})
    controller = WorkspaceController(
        hub, btc, lambda old, new: None,
        warm_context_limit=1, warm_grace_seconds=0.01,
    )
    controller.switch("ONGUSDT", 0.01)
    time.sleep(0.05)

    assert controller.switch("ONGUSDT", 0.01) is ong
    assert btc in hub.discarded


TESTS = (
    test_pending_candidate_does_not_replace_active_until_composite_ready,
    test_quiet_trades_are_ready_after_subscription_and_empty_bootstrap,
    test_initial_workspace_fails_closed_until_composite_ready,
    test_timeout_preserves_previous_and_discards_new_candidate,
    test_malformed_symbol_and_book_identity_fail_closed,
    test_bootstrap_and_activation_failures_preserve_previous_active,
    test_warm_context_reuse_and_bounded_eviction,
    test_expired_warm_context_is_discarded_before_next_switch_decision,
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(test) for test in TESTS)


if __name__ == "__main__":
    for test in TESTS:
        test()
    print(f"workspace controller tests: {len(TESTS)} passed")
