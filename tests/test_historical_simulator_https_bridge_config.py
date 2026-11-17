"""Static ingress allowlist contract; no Nginx reload or network operations."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SimulatorFactsIngressTests(unittest.TestCase):
    def test_migration_phase_a_keeps_facts_unexposed(self):
        """Static stage-A source must retain only the reviewed poll/ack surface."""
        cfg = (ROOT / "deploy/terminal_ingress/nginx-authenticated.conf").read_text()
        self.assertEqual(cfg.count("location = /api/diary/simulator-bridge/poll {"), 1)
        self.assertEqual(cfg.count("location = /api/diary/simulator-bridge/ack {"), 1)
        self.assertNotIn("location = /api/diary/simulator-bridge/facts {", cfg)
        self.assertNotIn("X-BybitScanner-Simulator-Device-Token", cfg)
        poll = re.search(
            r"location = /api/diary/simulator-bridge/poll \\{(.*?)\\n    \\}",
            cfg, re.DOTALL,
        )
        ack = re.search(
            r"location = /api/diary/simulator-bridge/ack \\{(.*?)\\n    \\}",
            cfg, re.DOTALL,
        )
        self.assertIsNotNone(poll)
        self.assertIsNotNone(ack)
        self.assertIn("limit_except GET { deny all; }", poll.group(1))
        self.assertIn("limit_except POST { deny all; }", ack.group(1))
        for route in (poll.group(1), ack.group(1)):
            self.assertIn("proxy_pass http://127.0.0.1:8765;", route)
            self.assertIn('proxy_set_header Cookie "";', route)
            self.assertIn('proxy_set_header Authorization "";', route)
            self.assertNotIn("auth_request", route)
            self.assertNotIn("allow all", route)
        self.assertIn("location /api/ {\\n        auth_request /_auth;", cfg)
        self.assertNotIn("location = /api/diary/simulator-bridge/request {", cfg)
        self.assertNotIn("location = /api/diary/simulator-bridge/pair {", cfg)

    def test_unauthenticated_legacy_http_denies_every_bridge_path(self):
        legacy = (ROOT / "deploy/nginx/bybitscanner.conf").read_text()
        self.assertIn("location ^~ /api/diary/simulator-bridge/ {\n        return 404;", legacy)


if __name__ == "__main__":
    unittest.main()
