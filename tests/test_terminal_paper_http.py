import json
import tempfile
import threading
import time
import urllib.request
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

from terminal.domain.models import (
    Category, OrderId, OrderSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import (
    PaperHttpHandler,
    PublicKlineBuffer,
    PublicOrderBookBuffer,
    PublicTradeBuffer,
    PublicTradeKlineBuffer,
    SerializedPaperRuntime,
)
from terminal.runtime.paper_runtime import PaperRuntime


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


def _runtime_owner(path: Path) -> SerializedPaperRuntime:
    instrument = InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading",
        "BTC", "USDT", "USDT", Decimal("0.5"), Decimal("1000000"),
        Decimal("0.5"), Decimal("0.001"), Decimal("100"), Decimal("50"),
        Decimal("0.001"), Decimal("5"),
    )
    return SerializedPaperRuntime(lambda: PaperRuntime(
        path,
        book_provider=StaticBookProvider(),
        instrument_snapshot=instrument,
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
            execution_count = runtime.call(
                lambda owned: len(owned.store.load_executions())
            )
            assert execution_count == 1
        finally:
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
            state = runtime.call(lambda owner: owner.paper_state("BTCUSDT"))
            assert len(state["active_limit_orders"]) == 1
        finally:
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
                lambda owner: owner.store.get_paper_limit("paper-runtime-limit-1")
            )
            assert order is not None
            assert order.filled_quantity == Decimal("10")
            assert order.status == "partially_filled"
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
