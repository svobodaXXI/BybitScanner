"""Strict, no-execution tests for Windows Simulator launch URI."""
from __future__ import annotations

import unittest
import ssl
from urllib.error import HTTPError, URLError
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

    def test_pair_uri_accepts_only_existing_slot_and_narrow_token(self):
        pairing = "bybitscanner-simulator://pair?device_id=owner-pc&token=" + "A" * 64
        self.assertEqual(adapter.parse_pair_uri(pairing), ("owner-pc", "A" * 64))
        for bad in (
            pairing + "&command=calc.exe",
            pairing + "#frag",
            pairing + "&token=" + "A" * 64,
            pairing.replace("owner-pc", "../../other"),
            pairing.replace("pair?", "pair/run?"),
            pairing.replace("A" * 64, "SHORT"),
            pairing.replace("bybitscanner-simulator", "http"),
            "bybitscanner-simulator://pair?device_id=owner-pc",
        ):
            with self.subTest(uri=bad), self.assertRaises(ValueError):
                adapter.parse_pair_uri(bad)

    def test_valid_uri_launches_only_fixed_application(self):
        with patch.object(adapter, "launch_local_viewer") as launch:
            self.assertEqual(adapter.main([GOOD_URI]), 0)
            launch.assert_called_once_with(EPISODE)

    def test_untrusted_uri_never_launches(self):
        with patch.object(adapter, "launch_local_viewer") as launch:
            for uri in (GOOD_URI + "&path=C:\\Windows", "https://localhost/open"):
                self.assertEqual(adapter.main([uri]), 2)
            launch.assert_not_called()

    def test_pairing_failure_notice_never_discloses_input(self):
        from research.local_replay_viewer import launch_bridge_agent
        token = "A" * 64
        uri = "bybitscanner-simulator://pair?device_id=owner-laptop&token=" + token
        for error, code in (
            (HTTPError(uri, 403, token, None, None), "HTTP_403"),
            (URLError(ssl.SSLError(token)), "TLS_FAILURE"),
            (URLError(token), "NETWORK_FAILURE"),
            (OSError(token), "LOCAL_OS_OR_IO_FAILURE"),
            (ValueError(token), "PAIRING_VALIDATION_FAILURE"),
        ):
            with self.subTest(code=code), patch.object(adapter.os, "name", "nt"), \
                    patch.object(launch_bridge_agent, "pair_device", side_effect=error), \
                    patch.object(adapter, "_pairing_notice") as notice:
                self.assertEqual(adapter.main([uri]), 2)
                notice.assert_called_once_with("Pairing failed: " + code)

    def test_pairing_success_and_invalid_uri_notice(self):
        from research.local_replay_viewer import launch_bridge_agent
        uri = "bybitscanner-simulator://pair?device_id=owner-laptop&token=" + "A" * 64
        with patch.object(adapter.os, "name", "nt"), \
                patch.object(launch_bridge_agent, "pair_device") as pair, \
                patch.object(adapter, "_pairing_notice") as notice:
            self.assertEqual(adapter.main([uri]), 0)
            pair.assert_called_once_with("owner-laptop", "A" * 64)
            notice.assert_called_once_with("Pairing configuration accepted.")
            notice.reset_mock()
            pair.reset_mock()
            self.assertEqual(adapter.main([uri + "&unexpected=1"]), 2)
            pair.assert_not_called()
            notice.assert_called_once_with("Pairing failed: INVALID_PAIRING_LINK")

    def test_registration_requires_explicit_local_action(self):
        with patch.object(adapter, "register_windows_protocol") as register:
            self.assertEqual(adapter.main(["--register"]), 0)
            register.assert_called_once_with()
        with patch.object(adapter, "register_windows_protocol") as register:
            self.assertEqual(adapter.main([]), 2)
            register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
