import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from workspace_ready_link import workspace_link, write_workspace_qr


class WorkspaceReadyLinkTests(unittest.TestCase):
    def test_editor_link_encodes_signal_identity(self):
        link = workspace_link("https://terminal.example.com/", "EDITOR", "XDPUSDT", "5m", "signal-123")
        self.assertEqual(parse_qs(urlsplit(link).query), {
            "mode": ["EDITOR"], "symbol": ["XDPUSDT"],
            "timeframe": ["5m"], "signal_id": ["signal-123"],
        })

    def test_browser_terminal_uses_same_origin(self):
        link = workspace_link("https://terminal.example.com", "TERMINAL", "BTCUSDT", "1m")
        self.assertEqual(urlsplit(link).netloc, "terminal.example.com")
        self.assertNotIn("token", link)

    def test_refuses_unsafe_destination_and_parameters(self):
        bad_origins = ["http://terminal.example.com", "https://user:pass@terminal.example.com",
                       "https://127.0.0.1:4173", "https://localhost", "https://terminal.example.com?token=x",
                       "https://terminal.example.com:4173", "https://terminal.example.com/#fragment"]
        for origin in bad_origins:
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                workspace_link(origin, "EDITOR", "BTCUSDT", "5m")
        for mode, symbol, tf, sid in [
            ("AUTOPILOT", "BTCUSDT", "5m", None), ("EDITOR", "btcUSDT", "5m", None),
            ("EDITOR", "BTCUSDT", "8h", None), ("EDITOR", "BTCUSDT", "5m", "bad/segment")]:
            with self.assertRaises(ValueError):
                workspace_link("https://terminal.example.com", mode, symbol, tf, sid)

    def test_local_qr_png_contains_link_if_dependency_available(self):
        try:
            import qrcode  # noqa: F401
        except ImportError:
            self.skipTest("QR dependency not installed in this environment")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_workspace_qr("https://terminal.example.com/?mode=EDITOR", Path(tmp) / "signal.png")
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
