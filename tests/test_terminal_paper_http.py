import json
import tempfile
import threading
import time
import urllib.request
from decimal import Decimal
from http.server import ThreadingHTTPServer
from pathlib import Path

from terminal.domain.models import Category, Price, Quantity, Symbol
from terminal.exchange.events import InstrumentSnapshot
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_http_server import (
    PaperHttpHandler,
    PublicOrderBookBuffer,
    PublicTradeBuffer,
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
            test_public_trades_aggregate_side_window_notional_and_sweep_ticks,
        )
    )
