import json
import tempfile
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

from terminal.runtime.paper_http_server import PaperHttpHandler
from terminal.runtime.paper_runtime import PaperRuntime


def test_market_post_completes_with_one_durable_execution():
    with tempfile.TemporaryDirectory() as temp:
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
        server = HTTPServer(("127.0.0.1", 0), PaperHttpHandler)
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
            assert len(runtime.store.load_executions()) == 1
        finally:
            server.server_close()
            runtime.close()


def test_health_get_returns_exact_paper_status():
    with tempfile.TemporaryDirectory() as temp:
        runtime = PaperRuntime(Path(temp) / "paper.sqlite3")
        server = HTTPServer(("127.0.0.1", 0), PaperHttpHandler)
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


import unittest


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for test in (
            test_market_post_completes_with_one_durable_execution,
            test_health_get_returns_exact_paper_status,
        )
    )
