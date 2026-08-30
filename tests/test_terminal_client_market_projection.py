from copy import deepcopy
import unittest

from terminal.market_data.client_projection import ClientMarketProjection, StaleProjectionError
from terminal.market_data.hub import SymbolContext
from terminal.runtime.paper_http_server import WorkspaceMarketDataManager


class _Book:
    def __init__(self, symbol="BTCUSDT", depth=6):
        self.symbol = symbol
        self.depth = 1000
        self.data = {
            "symbol": symbol, "state": "READY", "version": 1, "updateId": 10,
            "sequence": 100, "receivedAt": 1000,
            "bids": [{"price": str(100 - i), "size": "1"} for i in range(depth)],
            "asks": [{"price": str(101 + i), "size": "1"} for i in range(depth)],
        }

    def snapshot(self):
        return deepcopy(self.data)


class _Trades:
    def __init__(self):
        self.items = []

    def snapshot_after(self, _after):
        return deepcopy(self.items)


class _Candles:
    def __init__(self, interval="5"):
        self.data = {"state": "READY", "version": 1, "receivedAt": 1000,
                     "interval": interval, "candles": []}

    def snapshot(self):
        return deepcopy(self.data)


def _context():
    return SymbolContext("BTCUSDT", _Book(), _Trades(), {"5": _Candles()})


def _advance(book, *, version=1, update=1, sequence=1):
    book.data["version"] += version
    book.data["updateId"] += update
    book.data["sequence"] += sequence
    book.data["receivedAt"] += 10


def test_book_projection_bounded_snapshot_update_delete_and_no_redundant_snapshot():
    context = _context()
    projection = ClientMarketProjection(context, 7, book_depth=3)
    snapshot = projection.book_event()
    assert snapshot["kind"] == "book_snapshot"
    assert snapshot["workspace_generation"] == 7
    assert len(snapshot["bids"]) == len(snapshot["asks"]) == 3
    assert projection.book_event() is None

    context.public_orderbook.data["bids"][0]["size"] = "2"
    _advance(context.public_orderbook)
    delta = projection.book_event(base_version=snapshot["projection_version"])
    assert delta["kind"] == "book_delta"
    assert {"price": "100", "size": "2"} in delta["bids"]

    context.public_orderbook.data["bids"] = context.public_orderbook.data["bids"][1:]
    _advance(context.public_orderbook)
    delta = projection.book_event(base_version=delta["new_version"])
    assert {"price": "100", "size": "0"} in delta["bids"]
    assert {"price": "97", "size": "1"} in delta["bids"]


def test_book_window_new_better_edge_displacement_and_spread_move():
    context = _context()
    projection = ClientMarketProjection(context, 1, book_depth=2)
    first = projection.book_event()
    context.public_orderbook.data["bids"].append({"price": "101", "size": "4"})
    context.public_orderbook.data["asks"] = [
        {"price": "100.5", "size": "3"}, *context.public_orderbook.data["asks"]
    ]
    _advance(context.public_orderbook)
    delta = projection.book_event(base_version=first["projection_version"])
    assert {"price": "101", "size": "4"} in delta["bids"]
    assert {"price": "99", "size": "0"} in delta["bids"]
    assert {"price": "100.5", "size": "3"} in delta["asks"]
    assert {"price": "102", "size": "0"} in delta["asks"]


def test_book_gap_client_mismatch_and_untrusted_health_require_resnapshot():
    context = _context()
    projection = ClientMarketProjection(context, 1, book_depth=2)
    first = projection.book_event()
    _advance(context.public_orderbook, version=2)
    assert projection.book_event(base_version=first["projection_version"])["kind"] == "book_snapshot"
    _advance(context.public_orderbook)
    assert projection.book_event(base_version=999)["kind"] == "book_snapshot"
    context.public_orderbook.data["state"] = "DEGRADED"
    context.public_orderbook.data["bids"] = []
    _advance(context.public_orderbook)
    health = projection.book_event()
    assert health["kind"] == "book_health" and health["resync_required"] is True
    context.public_orderbook.data.update({
        "state": "READY", "bids": [{"price": "100", "size": "1"}],
    })
    _advance(context.public_orderbook)
    assert projection.book_event()["kind"] == "book_snapshot"


def test_stale_generation_rejected():
    context = _context()
    projection = ClientMarketProjection(context, 3, is_current=lambda _c, generation: generation == 4)
    try:
        projection.book_event()
    except StaleProjectionError:
        pass
    else:
        raise AssertionError("stale generation must fail closed")


def test_trades_bounded_bootstrap_new_only_duplicate_suppression_and_quiet():
    context = _context()
    context.public_trades.items = [
        {"id": str(i), "seq": i, "ended_at_ms": i, "symbol": "BTCUSDT"}
        for i in range(1, 7)
    ]
    projection = ClientMarketProjection(context, 1, trade_limit=3)
    bootstrap = projection.trades_event()
    assert bootstrap["kind"] == "trade_bootstrap"
    assert [item["id"] for item in bootstrap["trades"]] == ["4", "5", "6"]
    assert projection.trades_event() is None

    quiet = ClientMarketProjection(_context(), 1, trade_limit=3)
    assert quiet.trades_event()["trades"] == []
    assert quiet.trades_event() is None
    context.public_trades.items += [
        {"id": "6", "seq": 6, "ended_at_ms": 6},
        {"id": "7", "seq": 7, "ended_at_ms": 7},
    ]
    batch = projection.trades_event()
    assert [item["id"] for item in batch["trades"]] == ["7"]
    assert projection.trades_event() is None


def test_candles_bootstrap_update_append_unchanged_and_timeframe_identity():
    context = _context()
    candles = context.public_klines["5"]
    candles.data["candles"] = [
        {"startTime": i, "open": "1", "high": "2", "low": "1", "close": "1.5"}
        for i in range(1, 1001)
    ]
    projection = ClientMarketProjection(context, 2, candle_limit=1000)
    bootstrap = projection.candles_event("5")
    assert bootstrap["kind"] == "candle_bootstrap"
    assert bootstrap["interval"] == "5" and len(bootstrap["candles"]) == 1000
    candles.data["version"] += 1
    assert projection.candles_event("5") is None
    candles.data["candles"][-1]["close"] = "1.6"
    candles.data["version"] += 1
    update = projection.candles_event("5")
    assert update["candles"] == [{"action": "replace", **candles.data["candles"][-1]}]
    candles.data["candles"].append(
        {"startTime": 1001, "open": "1.6", "high": "2", "low": "1.5", "close": "1.7"}
    )
    candles.data["version"] += 1
    append = projection.candles_event("5")
    assert append["candles"] == [{"action": "append", **candles.data["candles"][-1]}]


def test_candle_history_mismatch_resyncs_and_paper_keeps_full_book():
    context = _context()
    context.public_klines["5"].data["candles"] = [
        {"startTime": 1, "open": "1", "high": "1", "low": "1", "close": "1"},
        {"startTime": 2, "open": "2", "high": "2", "low": "2", "close": "2"},
    ]
    projection = ClientMarketProjection(context, 1, book_depth=2)
    projection.candles_event("5")
    context.public_klines["5"].data["candles"] = [
        {"startTime": 1, "open": "1", "high": "1", "low": "1", "close": "1"},
    ]
    context.public_klines["5"].data["version"] += 1
    assert projection.candles_event("5")["resync"] is True
    projection.book_event()
    assert len(context.public_orderbook.snapshot()["bids"]) == 6


def test_workspace_generation_transition_starts_fresh_bootstrap():
    context = _context()
    first = ClientMarketProjection(context, 1, book_depth=2).book_event()
    second = ClientMarketProjection(context, 2, book_depth=2).book_event()
    assert first["kind"] == second["kind"] == "book_snapshot"
    assert first["workspace_generation"] == 1
    assert second["workspace_generation"] == 2


def test_workspace_manager_projection_uses_controller_owned_active_context():
    context = _context()

    class _Controller:
        def get_active(self, symbol):
            assert symbol == "BTCUSDT"
            return context, 9

        def is_current(self, candidate, generation):
            return candidate is context and generation == 9

    manager = WorkspaceMarketDataManager.__new__(WorkspaceMarketDataManager)
    manager._controller = _Controller()
    projection = manager.client_projection("BTCUSDT")
    assert projection.context is context
    assert projection.book_event()["workspace_generation"] == 9


TESTS = (
    test_book_projection_bounded_snapshot_update_delete_and_no_redundant_snapshot,
    test_book_window_new_better_edge_displacement_and_spread_move,
    test_book_gap_client_mismatch_and_untrusted_health_require_resnapshot,
    test_stale_generation_rejected,
    test_trades_bounded_bootstrap_new_only_duplicate_suppression_and_quiet,
    test_candles_bootstrap_update_append_unchanged_and_timeframe_identity,
    test_candle_history_mismatch_resyncs_and_paper_keeps_full_book,
    test_workspace_generation_transition_starts_fresh_bootstrap,
    test_workspace_manager_projection_uses_controller_owned_active_context,
)


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(test) for test in TESTS)


if __name__ == "__main__":
    for test in TESTS:
        test()
    print("TERMINAL CLIENT MARKET PROJECTION: OK")
