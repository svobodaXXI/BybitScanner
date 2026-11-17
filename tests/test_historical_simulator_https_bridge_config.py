"""Static ingress allowlist contract; no Nginx reload or network operations."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SimulatorFactsIngressTests(unittest.TestCase):
    def test_device_facts_route_is_exact_and_read_only(self):
        cfg = (ROOT / "deploy/terminal_ingress/nginx-authenticated.conf").read_text()
        match = re.search(
            r"location = /api/diary/simulator-bridge/facts \\{(.*?)\\n    \\}",
            cfg, re.DOTALL,
        )
        self.assertIsNotNone(match)
        route = match.group(1)
        self.assertIn("limit_except GET { deny all; }", route)
        self.assertIn("proxy_pass http://127.0.0.1:8765;", route)
        self.assertIn('proxy_set_header Cookie "";', route)
        self.assertIn('proxy_set_header Authorization "";', route)
        self.assertIn("proxy_set_header X-BybitScanner-Simulator-Device-Token", route)
        self.assertNotIn("auth_request", route)
        self.assertNotIn("allow all", route)
        # Requests, status and pairing remain owner-authenticated only.
        self.assertIn("location /api/ {\\n        auth_request /_auth;", cfg)
        self.assertNotIn("location = /api/diary/simulator-bridge/request {", cfg)
        self.assertNotIn("location = /api/diary/simulator-bridge/pair {", cfg)

    def test_unauthenticated_legacy_http_denies_every_bridge_path(self):
        legacy = (ROOT / "deploy/nginx/bybitscanner.conf").read_text()
        self.assertIn("location ^~ /api/diary/simulator-bridge/ {\\n        return 404;", legacy)


if __name__ == "__main__":
    unittest.main()
