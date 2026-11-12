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
        # Pre-window public bars warm only the causal hourly detector.
        # They must never appear in the requested 1-day visual replay.
        candles = [
            dict(time=start+i*FIVE_MINUTES_MS, open="100", high="102",
                 low="98", close="101", volume="1")
            for i in range(-local.GEOMETRY_PRELOAD_BARS, 288)
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
        self.assertEqual(first["geometry_warmup_hours"], 72)
        self.assertEqual(first["events"][0]["candle"]["start_ms"], start)
        self.assertTrue(all(e["time_ms"] > start for e in first["events"]))
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

    def call(self, port: int, method: str, path: str, host: str | None = None, *,
             body: bytes | None = None, extra_headers: dict[str, str] | None = None):
        connection = HTTPConnection("127.0.0.1", port, timeout=3)
        try:
            headers = {"Host": host} if host else {}
            if extra_headers:
                headers.update(extra_headers)
            connection.request(method, path, body=body, headers=headers)
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


    def test_public_m5_selected_detectors_are_get_only_no_paper_routes(self):
        with self.running_server() as (port, calls):
            path = ("/local-replay/history?symbol=BTCUSDT&start=2026-01-01"
                    "&end=2026-01-02&strategies=WEDGE_FALLING,IKIGAI_BOX")
            status, data, _ = self.call(port, "GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["mode"], "MARKET_ONLY")
            self.assertEqual(calls, [{
                "symbol": "BTCUSDT", "start": "2026-01-01", "end": "2026-01-02",
                "strategies": ("WEDGE_FALLING", "IKIGAI_BOX"),
            }])
            for strategies in ("IKIGAI_BOX,IKIGAI_BOX", "UNKNOWN", "WEDGE_FALLING,PAPER"):
                status, _, _ = self.call(port, "GET", path.split("&strategies=")[0]
                                        + "&strategies=" + strategies)
                self.assertEqual(status, 400)
            status, _, _ = self.call(port, "POST", path, body=b"{}")
            self.assertEqual(status, 405)
            status, _, _ = self.call(port, "GET", "/api/robot/status")
            self.assertEqual(status, 404)
            self.assertEqual(len(calls), 1)

    def test_simulation_capability_never_claims_verified_archive_on_presence_alone(self):
        with TemporaryDirectory() as tmp:
            with patch.object(local, "SIM_DATA", Path(tmp)):
                info = local.local_simulation_status()
                self.assertEqual(info["namespace"], "SIMULATION")
                self.assertFalse(info["can_attempt"])
                self.assertFalse(info["archive_files_present"])
                self.assertFalse(info["wedge_risk_profile_present"])
                with self.assertRaisesRegex(ValueError, "отсутствует"):
                    local.run_local_simulation({
                        "symbol": "BTCUSDT",
                        "start_utc": "2026-10-01T00:00",
                        "end_utc_inclusive": "2026-10-01T01:00",
                        "selected_strategies": ["IKIGAI_BOX"],
                        "initial_balance": "1000",
                    })
                with self.assertRaisesRegex(ValueError, "отсутствует"):
                    local.run_local_simulation({
                        "symbol": "BTCUSDT",
                        "start_utc": "2026-10-01T00:00",
                        "end_utc_inclusive": "2026-10-01T01:00",
                        "selected_strategies": ["WEDGE_FALLING"],
                        "initial_balance": "1000",
                    })

    def test_manifest_hint_prefills_only_a_complete_local_second_day(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "m1-cache").mkdir()
            (folder / "wedge-risk.json").write_text("{}", encoding="utf-8")
            manifest = {
                "schema": "SIMULATOR_V2_PUBLIC_TRADES_DERIVED_M1_RANGE_V1",
                "symbol": "XRPUSDT", "days": 3,
                "start_ms": 1788998400000, "end_ms": 1789257600000,
            }
            (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(local, "SIM_DATA", folder):
                info = local.local_simulation_status()
                self.assertEqual(info["archive_hint"], {
                    "symbol": "XRPUSDT",
                    "start_utc": "2026-09-11T00:00",
                    "end_utc_inclusive": "2026-09-11T23:59",
                })
                manifest["end_ms"] += 60000  # Non-contiguous/inconsistent metadata.
                (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                self.assertNotIn("archive_hint", local.local_simulation_status())

    def test_wedge_simulation_post_is_loopback_origin_locked_and_never_paper(self):
        with self.running_server() as (port, calls):
            status, data, _ = self.call(port, "GET", "/local-replay/simulation/status")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(data)["namespace"], "SIMULATION")
            payload = json.dumps({
                "symbol": "BTCUSDT",
                "start_utc": "2026-10-01T00:00",
                "end_utc_inclusive": "2026-10-01T00:10",
                "selected_strategies": ["WEDGE_FALLING"],
                "initial_balance": "1000",
            }).encode("utf-8")
            valid_headers = {
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "X-Local-Simulation": "wedge",
            }
            for headers in (
                {"Origin": "https://malicious.example", **{
                    k: v for k,v in valid_headers.items() if k != "Origin"
                }},
                {k: v for k, v in valid_headers.items() if k != "X-Local-Simulation"},
                {**valid_headers, "Sec-Fetch-Site": "cross-site"},
            ):
                with self.subTest(headers=headers):
                    code, _, _ = self.call(
                        port, "POST", "/local-replay/simulation/wedge",
                        body=payload, extra_headers=headers,
                    )
                    self.assertEqual(code, 403)
            with patch.object(local, "run_local_simulation", return_value={
                "namespace": "SIMULATION", "virtual_fills": 0,
                "scenario_type": "ORIGINAL_WEDGE_SCANNER_ROBOT_LOCAL_OHLC_SIMULATION",
            }) as invoked:
                code, data, _ = self.call(
                    port, "POST", "/local-replay/simulation/wedge",
                    body=payload, extra_headers=valid_headers,
                )
                self.assertEqual(code, 200)
                self.assertEqual(json.loads(data)["virtual_fills"], 0)
                invoked.assert_called_once_with(json.loads(payload))
            code, _, _ = self.call(
                port, "POST", "/local-replay/history",
                body=payload, extra_headers=valid_headers,
            )
            self.assertEqual(code, 405)
            code, _, _ = self.call(port, "GET", "/api/orders")
            self.assertEqual(code, 404)
            self.assertEqual(calls, [])

    def test_wedge_simulation_rejects_unsupported_content_and_active_lock(self):
        with self.running_server() as (port, calls):
            sample = b'{"selected_strategies":["WEDGE_FALLING"]}'
            headers = {
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "X-Local-Simulation": "wedge",
            }
            with local.SIM_LOCK:
                status, _, _ = self.call(
                    port, "POST", "/local-replay/simulation/wedge",
                    body=sample, extra_headers=headers,
                )
                self.assertEqual(status, 409)
            status, _, _ = self.call(
                port, "POST", "/local-replay/simulation/wedge",
                body=sample, extra_headers=headers,
            )
            self.assertEqual(status, 422)
            status, _, _ = self.call(
                port, "POST", "/local-replay/simulation/wedge",
                body=sample, extra_headers={**headers, "Content-Type": "text/plain"},
            )
            self.assertEqual(status, 403)
            self.assertEqual(calls, [])



class LocalTakerShadowEntryTests(unittest.TestCase):
    def test_fixed_local_archive_opt_in_passes_only_to_wedge(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "raw-trades").mkdir()
            (root / "manifest.json").write_text("{}", encoding="utf-8")
            (root / "wedge-risk.json").write_text(
                json.dumps({"scanner": {}, "risk": {"terms_source": "test"}}),
                encoding="utf-8",
            )
            params = {
                "symbol": "BTCUSDT", "start_utc": "2026-10-01T01:00",
                "end_utc_inclusive": "2026-10-01T01:02",
                "selected_strategies": ["WEDGE_FALLING"],
                "initial_balance": "1000",
            }
            # The local HTTP test must not import Scanner dependencies or
            # pretend to test the real research engine (its own CI does that).
            from types import ModuleType
            from unittest.mock import Mock
            stub = ModuleType("research.simulator_v2.wedge_cli")
            stub.MAX_MANIFEST_BYTES = 125_000
            stub.parse_manifest = Mock()
            runner = Mock()
            runner.return_value.to_payload.return_value = {"namespace": "SIMULATION"}
            stub.run_from_time_machine_config = runner
            with (
                patch.object(local, "SIM_DATA", root),
                patch.object(local, "local_simulation_status", return_value={"can_attempt": True}),
                patch.dict("sys.modules", {"research.simulator_v2.wedge_cli": stub}),
            ):
                response = local.run_local_simulation(params)
                self.assertEqual(response["namespace"], "SIMULATION")
                self.assertEqual(
                    runner.call_args.kwargs["flow_archive_dir"],
                    root / "raw-trades",
                )
                self.assertEqual(
                    runner.call_args.kwargs["config"]["selected_strategies"],
                    ["WEDGE_FALLING"],
                )
                runner.reset_mock()
                # Box does not silently use the Wedge-only research tape.
                local.run_local_simulation({
                    **params, "selected_strategies": ["IKIGAI_BOX"],
                })
                self.assertIsNone(runner.call_args.kwargs["flow_archive_dir"])
                runner.reset_mock()
                (root / "raw-trades").rmdir()
                local.run_local_simulation(params)
                self.assertIsNone(runner.call_args.kwargs["flow_archive_dir"])
                runner.reset_mock()
                (root / "raw-trades").write_text("not a folder", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unsafe local raw taker"):
                    local.run_local_simulation(params)
                runner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
