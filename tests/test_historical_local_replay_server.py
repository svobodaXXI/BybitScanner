"""Local Windows viewer: public kline and loopback-only HTTP boundary tests."""
from contextlib import contextmanager
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from research.historical_candle_feed import FIVE_MINUTES_MS
from research.local_replay_viewer import server as local


class PublicKlineTests(unittest.TestCase):
    def test_public_endpoint_is_unsigned_and_read_only(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                pass

            def read(self, _size):
                return json.dumps({
                    "retCode": 0,
                    "result": {"list": [[
                        "300000", "100", "110", "95", "102", "3.4", "0"
                    ]]},
                }).encode("utf-8")

        def fake_open(request, timeout):
            requests.append((request, timeout))
            return Response()

        with patch.object(local, "urlopen", fake_open):
            records = local.fetch_public_klines("BTCUSDT", "5", 500, end_ms=600_000)
        self.assertEqual(records[0]["time"], "300000")
        self.assertEqual(records[0]["close"], "102")
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        parsed = urlsplit(request.full_url)
        self.assertEqual(parsed.scheme + "://" + parsed.netloc + parsed.path, local.BYBIT_PUBLIC_KLINE)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(parse_qs(parsed.query), {
            "category": ["linear"], "symbol": ["BTCUSDT"],
            "interval": ["5"], "limit": ["500"], "end": ["600000"],
        })
        self.assertNotIn("api_key", parsed.query)
        self.assertNotIn("sign", parsed.query)
        self.assertEqual(timeout, 12)

    def test_api_failure_does_not_create_fake_data(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def read(self, _size): return b'{"retCode":10001,"retMsg":"bad symbol"}'

        with patch.object(local, "urlopen", lambda *args, **kwargs: Response()):
            with self.assertRaisesRegex(ValueError, "rejected"):
                local.fetch_public_klines("BTCUSDT", "5", 1, end_ms=1)

    def test_market_only_history_rejects_future_and_overlong_queries(self):
        counter = []

        def forbidden(*args, **kwargs):
            counter.append((args, kwargs))
            raise AssertionError("network must not be called for invalid query")

        with self.assertRaisesRegex(ValueError, "7 complete"):
            local.load_public_history(
                symbol="BTCUSDT", start="2026-01-01", end="2026-01-09",
                fetch_candles=forbidden,
            )
        with self.assertRaisesRegex(ValueError, "Future"):
            local.load_public_history(
                symbol="BTCUSDT", start="2099-01-01", end="2099-01-02",
                fetch_candles=forbidden,
            )
        with self.assertRaisesRegex(ValueError, "linear"):
            local.load_public_history(
                symbol="../../PAPER", start="2026-01-01", end="2026-01-02",
                fetch_candles=forbidden,
            )
        self.assertEqual(counter, [])

    def test_local_history_uses_closed_bars_no_trade_and_unique_run(self):
        start = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        candles = [
            dict(time=start+i*FIVE_MINUTES_MS, open="100", high="102",
                 low="98", close="101", volume="1")
            for i in range(288)
        ]
        def fake_fetch(_symbol, _interval, limit, *, end_ms):
            return [c for c in candles if c["time"] <= end_ms][-limit:][::-1]

        first = local.load_public_history(
            symbol="BTCUSDT", start="2026-01-01", end="2026-01-02",
            fetch_candles=fake_fetch,
        )
        second = local.load_public_history(
            symbol="BTCUSDT", start="2026-01-01", end="2026-01-02",
            fetch_candles=fake_fetch,
        )
        self.assertEqual(first["mode"], "MARKET_ONLY")
        self.assertEqual(first["source"], "SIMULATION")
        self.assertEqual(len(first["events"]), 288)
        self.assertEqual(first["events"][-1]["candle"]["end_ms"], start+288*FIVE_MINUTES_MS)
        self.assertTrue(all(e["kind"] == "CANDLE_CLOSED" and "trade_id" not in e
                            for e in first["events"]))
        self.assertNotEqual(first["simulation_run_id"], second["simulation_run_id"])


class LoopbackServerTests(unittest.TestCase):
    @contextmanager
    def running_server(self):
        with TemporaryDirectory() as temp:
            dist = Path(temp)
            (dist / "replay.html").write_text("<h1>Local simulation only</h1>", encoding="utf-8")
            (dist / "view.js").write_text("const local=true;", encoding="utf-8")
            requests = []

            def loader(**query):
                requests.append(query)
                return {"source": "SIMULATION", "mode": "MARKET_ONLY",
                        "simulation_run_id": "fixture", "events": []}

            httpd = ThreadingHTTPServer(
                ("127.0.0.1", 0), local.handler_factory(dist, loader),
            )
            worker = Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                yield httpd.server_address[1], requests
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=4)

    def call(self, port: int, method: str, path: str, host: str | None = None):
        connection = HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            headers = {"Host": host} if host else {}
            connection.request(method, path, headers=headers)
            response = connection.getresponse()
            return response.status, response.read(), dict(response.getheaders())
        finally:
            connection.close()

    def test_static_replay_is_available_only_on_loopback_no_repo_file_escape(self):
        with self.running_server() as (port, calls):
            code, html, headers = self.call(port, "GET", "/replay.html")
            self.assertEqual(code, 200)
            self.assertIn(b"Local simulation only", html)
            self.assertEqual(headers["Cache-Control"], "no-store")
            code, _, _ = self.call(port, "GET", "/../../AGENTS.md")
            self.assertEqual(code, 404)
            code, _, _ = self.call(port, "GET", "/replay.html", host="untrusted.example")
            self.assertEqual(code, 403)
            self.assertEqual(calls, [])

    def test_history_is_get_only_without_paper_side_effects(self):
        with self.running_server() as (port, calls):
            path = "/local-replay/history?symbol=BTCUSDT&start=2026-01-01&end=2026-01-02"
            status, data, _ = self.call(port, "GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["source"], "SIMULATION")
            self.assertEqual(calls, [{
                "symbol": "BTCUSDT", "start": "2026-01-01", "end": "2026-01-02",
            }])
            status, _, _ = self.call(port, "POST", path)
            self.assertEqual(status, 405)
            status, _, _ = self.call(port, "GET", "/api/orders")
            self.assertEqual(status, 404)
            status, _, _ = self.call(port, "GET", "/local-replay/history?symbol=BTCUSDT")
            self.assertEqual(status, 400)
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
