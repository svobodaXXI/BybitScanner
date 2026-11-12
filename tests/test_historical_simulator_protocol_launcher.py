"""Strict, no-execution tests for Windows Simulator launch URI."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from research.local_replay_viewer import protocol_launcher as adapter


EPISODE = "te_" + "a" * 24
GOOD_URI = f"bybitscanner-simulator://open?episode={EPISODE}"


class SimulatorProtocolTests(unittest.TestCase):
    def test_parses_only_typed_episode_locator(self):
        self.assertEqual(adapter.parse_open_uri(GOOD_URI), EPISODE)
        bad = (
            "", "https://example.org/", "bybitscanner-simulator://open",
            "bybitscanner-simulator://open?episode=anything",
            GOOD_URI + "&command=calc.exe",
            GOOD_URI + "&episode=" + EPISODE,
            GOOD_URI + "#other",
            GOOD_URI.replace("//open?", "//evil?"),
            GOOD_URI.replace("te_", "../"),
            GOOD_URI.replace("te_", "TE_"),
            GOOD_URI.replace("a" * 24, "A" * 24),
            GOOD_URI.replace("open?", "open/anything?"),
            GOOD_URI + "%26bad",
            "bybitscanner-simulator://open?episode=%2Fetc%2Fpasswd",
        )
        for uri in bad:
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                adapter.parse_open_uri(uri)

    def test_valid_uri_launches_only_fixed_application(self):
        with patch.object(adapter, "launch_local_viewer") as launch:
            self.assertEqual(adapter.main([GOOD_URI]), 0)
            launch.assert_called_once_with(EPISODE)

    def test_untrusted_uri_never_launches(self):
        with patch.object(adapter, "launch_local_viewer") as launch:
            for uri in (GOOD_URI + "&path=C:\\Windows", "https://localhost/open"):
                self.assertEqual(adapter.main([uri]), 2)
            launch.assert_not_called()

    def test_registration_requires_explicit_local_action(self):
        with patch.object(adapter, "register_windows_protocol") as register:
            self.assertEqual(adapter.main(["--register"]), 0)
            register.assert_called_once_with()
        with patch.object(adapter, "register_windows_protocol") as register:
            self.assertEqual(adapter.main([]), 2)
            register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
