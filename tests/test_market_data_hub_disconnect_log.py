"""WS-DIAG-1: a market-data WebSocket disconnect leaves one safe diagnostic line."""

import re
import unittest

from terminal.market_data.hub import MarketDataHub
from tests.test_terminal_market_data_hub import _Registry, _WebSocket, _context

_SECRETS = ("alice", "s3cret", "abc123", "AAEKsecretTOKENvalue_99")


class _SecretFailingWebSocket(_WebSocket):
    def recv(self):
        raise OSError(
            "proxy socks5h://alice:s3cret@127.0.0.1:10808/x?token=abc123 refused;\n"
            "bot1234567:AAEKsecretTOKENvalue_99"
        )


class DisconnectLogTests(unittest.TestCase):
    def test_disconnect_logs_utc_class_safe_reason_and_generation(self):
        first, second = _SecretFailingWebSocket(), _WebSocket()
        sockets = iter((first, second))
        hub = MarketDataHub(
            _Registry(), _context,
            connection_factory=lambda url, timeout: next(sockets), reconnect_delay=0,
        )
        context = hub.subscribe("BTCUSDT")
        disconnects = []
        context.add_disconnect_listener("test", lambda generation, reason: disconnects.append(
            (generation, reason)))
        with self.assertLogs("terminal.market_data.hub", level="WARNING") as captured:
            hub.start()
            self.assertTrue(second.subscribed.wait(timeout=2))
            hub.close()

        lines = [line for line in captured.output if "WebSocket disconnected" in line]
        self.assertEqual(len(lines), 1, captured.output)
        line = lines[0]
        self.assertIn("error_class=OSError", line)
        self.assertIn("contexts=1", line)
        self.assertIn("generations=BTCUSDT:1", line)
        self.assertRegex(line, r"utc=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}\+00:00")
        self.assertIn("socks5h://<redacted>@127.0.0.1:10808/x?<redacted>", line)
        self.assertIn("bot<redacted>", line)
        self.assertNotIn("\n", line)
        for secret in _SECRETS:
            self.assertNotIn(secret, line)
        # The reconnect path itself is unchanged.
        self.assertEqual(context.reconnect_count, 1)
        self.assertEqual(disconnects, [(1, "OSError")])
        self.assertEqual(second.sent[0]["args"], first.sent[0]["args"])


if __name__ == "__main__":
    unittest.main()
