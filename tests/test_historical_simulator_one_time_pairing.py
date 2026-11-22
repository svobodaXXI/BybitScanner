"""Fail-closed one-time simulator pairing codes; no PAPER or VPS IO."""
import unittest

from terminal.diary.simulator_launch_relay import (
    PAIR_SECONDS, SimulatorLaunchRelay, RelayForbidden, RelayUnavailable,
)


class PairCodeTests(unittest.TestCase):
    def setUp(self):
        self.time = 1000.0
        self.relay = SimulatorLaunchRelay(
            origin="https://example.test", devices={
                "owner-pc": "A" * 64, "owner-laptop": "B" * 64,
            }, clock=lambda: self.time,
        )

    def issue(self, device="owner-pc"):
        return self.relay.issue_pair_code(
            device_id=device, request_origin="https://example.test",
            fetch_site="same-origin")

    def claim(self, code, device="owner-pc", origin="", fetch_site=""):
        return self.relay.claim_pair_code(
            device_id=device, code=code, origin=origin, fetch_site=fetch_site)

    def test_authenticated_code_is_single_use_and_does_not_expose_token(self):
        info = self.issue()
        code = info["code"]
        self.assertEqual(len(code), 24)
        self.assertNotIn("token", info)
        self.assertEqual(info["expires_in_seconds"], PAIR_SECONDS)
        self.assertEqual(self.claim(code), {"device_id": "owner-pc", "token": "A" * 64})
        with self.assertRaises(RelayForbidden):
            self.claim(code)

    def test_wrong_device_wrong_code_and_browser_origin_fail_closed(self):
        code = self.issue()["code"]
        for kw in (
            {"device": "owner-laptop"},
            {"origin": "https://evil.example"},
            {"fetch_site": "cross-site"},
        ):
            with self.subTest(kw=kw), self.assertRaises(RelayForbidden):
                self.claim(code, **kw)
        with self.assertRaises(RelayForbidden):
            self.claim("A" * 24)
        # Invalid guesses must never consume a legitimate owner code.
        self.assertEqual(self.claim(code)["token"], "A" * 64)

    def test_exact_expiry_and_reissue_invalidate_old_code(self):
        first = self.issue()["code"]
        second = self.issue()["code"]
        self.assertNotEqual(first, second)
        with self.assertRaises(RelayForbidden):
            self.claim(first)
        self.time += PAIR_SECONDS
        with self.assertRaises(RelayForbidden):
            self.claim(second)

    def test_no_unauthenticated_code_issue_or_unknown_slot(self):
        with self.assertRaises(RelayForbidden):
            self.relay.issue_pair_code(
                device_id="owner-pc", request_origin="",
                fetch_site="")
        with self.assertRaises(RelayUnavailable):
            self.issue("owner-unknown")


if __name__ == "__main__":
    unittest.main()
