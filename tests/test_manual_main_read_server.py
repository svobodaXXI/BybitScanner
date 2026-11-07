"""Offline tests: MAIN HTTP reads, no order routes, existing ingress owner-auth."""
from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from terminal.runtime.manual_main_read_server import (
    HOST, MainReadHandler, checked_main_state_dir,
)


class FakeMainAccounts:
    def __init__(self):
        self.refreshed = []

    def catalog(self):
        return {"accounts": [{"id": "bybit-abc", "display_name": "MAIN",
                               "provider": "BYBIT", "environment": "MAINNET",
                               "status": "DISCONNECTED"}]}

    def summary(self, account_id):
        if account_id != "bybit-abc":
            raise LookupError()
        return {"account_id": account_id, "positions": [{"symbol": "BTCUSDT"}], "orders": []}

    def provision(self, display_name, api_key, api_secret):
        if not display_name or not api_key or not api_secret:
            raise ValueError("invalid")
        self.provisioned = (display_name, api_key, api_secret)
        return {"account_id": "bybit-abc", "created": True}

    def refresh(self, account_id):
        if account_id != "bybit-abc":
            raise LookupError()
        self.refreshed.append(account_id)
        return self.summary(account_id)


class MainReadGatewayTests(unittest.TestCase):
    def setUp(self):
        self.app = FakeMainAccounts()
        handler = type("TestMainReadHandler", (MainReadHandler,), {"accounts": self.app})
        self.server = ThreadingHTTPServer((HOST, 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://{HOST}:{self.server.server_address[1]}"
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 1)

    def request(self, path, *, method="GET", body=None):
        request = Request(self.url + path, method=method, data=body)
        try:
            with urlopen(request, timeout=2) as response:
                return response.status, json.load(response), response.headers
        except HTTPError as exc:
            return exc.code, json.load(exc), exc.headers

    def test_allowlist_supports_catalog_summary_and_read_refresh(self):
        status, catalog, headers = self.request("/api/manual-main/accounts")
        self.assertEqual(status, 200)
        self.assertEqual(catalog["accounts"][0]["provider"], "BYBIT")
        self.assertEqual(headers["Cache-Control"], "no-store")
        status, detail, _ = self.request("/api/manual-main/accounts/bybit-abc/summary")
        self.assertEqual((status, detail["summary"]["positions"][0]["symbol"]), (200, "BTCUSDT"))
        status, refreshed, _ = self.request(
            "/api/manual-main/accounts/bybit-abc/refresh", method="POST", body=b"",
        )
        self.assertEqual((status, refreshed["summary"]["account_id"]), (200, "bybit-abc"))
        self.assertEqual(self.app.refreshed, ["bybit-abc"])
        status, health, _ = self.request("/api/manual-main/health")
        self.assertEqual((status, health["trading_enabled"]), (200, False))

    def test_no_trading_or_credential_post_and_no_paper_routes(self):
        for path in ("/api/manual-main/order",
                     "/api/live/market", "/api/market", "/api/manual-main/close-all"):
            status, result, _ = self.request(path, method="POST", body=b"{}")
            self.assertEqual(status, 405)
            self.assertEqual(result["error"], "read_only_gateway")
        status, result, _ = self.request("/api/manual-main/accounts/bybit-abc/refresh",
                                         method="POST", body=b'{"api_key":"secret"}')
        self.assertEqual((status, result["error"]), (400, "unexpected_payload"))
        self.assertEqual(self.app.refreshed, [])
        for path in ("/api/accounts", "/api/manual-main/accounts/paper/summary",
                     "/api/manual-main/accounts/bybit-%2Fetc/summary"):
            status, _, _ = self.request(path)
            self.assertEqual(status, 404)

    def test_same_origin_provisioning_and_no_secret_echo(self):
        payload = json.dumps({"display_name": "Main", "api_key": "private-key", "api_secret": "private-secret"}).encode()
        # Without a matching HTTPS origin, credential parsing is never reached.
        status, result, _ = self.request("/api/manual-main/accounts", method="POST", body=payload)
        self.assertEqual((status, result["error"]), (403, "origin_required"))
        self.assertFalse(hasattr(self.app, "provisioned"))
        status, result, _ = self.request_with_origin(payload)
        self.assertEqual((status, result["account_id"]), (201, "bybit-abc"))
        self.assertNotIn("private-key", str(result))
        self.assertNotIn("private-secret", str(result))
        self.assertEqual(self.app.provisioned, ("Main", "private-key", "private-secret"))
        for invalid in (b"{}", b"[]", b"{", b"{}" + b"x" * 9000):
            status, result, _ = self.request_with_origin(invalid)
            self.assertNotEqual(status, 201)
            self.assertNotIn("private-secret", str(result))

    def request_with_origin(self, body):
        req = Request(self.url + "/api/manual-main/accounts", data=body, method="POST",
                      headers={"Content-Type": "application/json",
                               "Origin": "https://127.0.0.1:" + str(self.server.server_address[1])})
        try:
            with urlopen(req, timeout=2) as response:
                return response.status, json.load(response), response.headers
        except HTTPError as exc:
            return exc.code, json.load(exc), exc.headers

    def test_private_main_state_directory_does_not_alias_paper_parent(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            main = base / "main"
            main.mkdir(mode=0o700)
            paper = base / "paper"
            paper.mkdir(mode=0o700)
            with patch.dict(os.environ, {"BYBITSCANNER_PAPER_DB": str(paper / "paper.sqlite3")}):
                self.assertEqual(checked_main_state_dir(str(main)), main)
                with self.assertRaisesRegex(RuntimeError, "collision"):
                    checked_main_state_dir(str(paper))
            main.chmod(0o755)
            with self.assertRaisesRegex(RuntimeError, "not_private"):
                checked_main_state_dir(str(main))
            with self.assertRaises(RuntimeError):
                checked_main_state_dir("")
            with self.assertRaises(RuntimeError):
                checked_main_state_dir("relative-directory")

    def test_manual_main_systemd_unit_is_separate_and_not_autostarted(self):
        unit = Path("deploy/systemd/bybitscanner-manual-main-read.service").read_text()
        self.assertIn("StateDirectory=bybitscanner-manual-main", unit)
        self.assertIn("StateDirectoryMode=0700", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("Restart=no", unit)
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("BYBITSCANNER_PAPER_DB", unit)
        self.assertNotIn("stop_robot_runtime", unit)
        self.assertNotIn("bybitscanner-paper-backend.service", unit)
        self.assertIn("terminal.runtime.manual_main_read_server", unit)

    def test_nginx_routing_requires_telegram_owner_auth(self):
        config = Path("deploy/terminal_ingress/nginx-authenticated.conf").read_text()
        route = config.split("location ^~ /api/manual-main/ {", 1)[1].split("}", 1)[0]
        self.assertIn("auth_request /_auth;", route)
        self.assertIn("proxy_pass http://127.0.0.1:8771;", route)
        self.assertLess(config.index("location ^~ /api/manual-main/"), config.index("location /api/"))
        self.assertNotIn("listen 0.0.0.0", config)


if __name__ == "__main__":
    unittest.main()
