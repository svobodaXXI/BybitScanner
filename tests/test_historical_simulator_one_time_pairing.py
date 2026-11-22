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


class LocalPairingClientTests(unittest.TestCase):
    def test_local_claim_never_returns_reusable_token_to_browser(self):
        import io
        import json
        from unittest.mock import patch
        from research.local_replay_viewer import launch_bridge_agent as agent

        class Client:
            def __init__(self):
                self.request = None

            def open(self, request, timeout):
                self.request = request
                self.assert_timeout = timeout
                data = io.BytesIO(json.dumps({
                    "ok": True, "device_id": "owner-pc", "token": "A" * 64,
                }).encode("utf-8"))
                data.status = 200
                return data

        client = Client()
        with patch.object(agent, "read_config", return_value=None), \
             patch.object(agent, "_trusted_statistics_origin", return_value="https://example.test"), \
             patch.object(agent, "pair_device") as persist:
            agent.claim_one_time_pairing_code("owner-pc", "A" * 24, opener=client)
        self.assertEqual(client.assert_timeout, 5)
        self.assertEqual(client.request.full_url,
            "https://example.test/api/diary/simulator-bridge/pair-claim")
        self.assertEqual(client.request.get_method(), "POST")
        self.assertNotIn("A" * 24, client.request.full_url)
        self.assertNotIn("A" * 64, client.request.full_url)
        self.assertEqual(json.loads(client.request.data), {
            "device_id": "owner-pc", "code": "A" * 24,
        })
        persist.assert_called_once_with("owner-pc", "A" * 64)

    def test_existing_local_config_rejects_claim_without_network(self):
        from unittest.mock import patch
        from research.local_replay_viewer import launch_bridge_agent as agent
        with patch.object(agent, "read_config", return_value={"already": "paired"}), \
             patch.object(agent, "_direct_https_opener") as network:
            with self.assertRaises(agent.AgentConfigError):
                agent.claim_one_time_pairing_code("owner-pc", "A" * 24)
            network.assert_not_called()


class LocalPairingHttpTests(unittest.TestCase):
    def test_cross_origin_rejected_and_exact_local_post_has_no_token(self):
        import json
        from http.server import ThreadingHTTPServer
        from threading import Thread
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from unittest.mock import patch
        from research.local_replay_viewer.server import handler_factory
        from research.local_replay_viewer import launch_bridge_agent as agent

        host = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory())
        server_thread = Thread(target=host.serve_forever, daemon=True)
        server_thread.start()
        origin = f"http://127.0.0.1:{host.server_address[1]}"
        payload = json.dumps({"device_id": "owner-pc", "code": "A" * 24}).encode()
        def request(src):
            return Request(origin + "/local-replay/pair-claim", data=payload,
                           headers={"Content-Type": "application/json",
                                    "X-Local-Pair-Code": "explicit-click",
                                    "Origin": src}, method="POST")
        try:
            with patch.object(agent, "claim_one_time_pairing_code") as pair:
                with self.assertRaises(HTTPError) as blocked:
                    urlopen(request("https://attacker.example"), timeout=5)
                self.assertEqual(blocked.exception.code, 403)
                pair.assert_not_called()
                with urlopen(request(origin), timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    data = response.read()
                self.assertEqual(json.loads(data), {"paired": True})
                self.assertNotIn(b"token", data)
                pair.assert_called_once_with("owner-pc", "A" * 24)
        finally:
            host.shutdown()
            host.server_close()
            server_thread.join(timeout=5)


class IngressPairingContractTests(unittest.TestCase):
    def test_new_claim_route_stays_owner_authenticated_until_reviewed_gateway(self):
        from pathlib import Path
        config = (Path(__file__).resolve().parents[1] /
                  "deploy/terminal_ingress/nginx-authenticated.conf").read_text()
        # The local adapter cannot claim on the deployed ingress until the
        # MONOLITH release owner adds a separately reviewed exact exception.
        self.assertNotIn("location = /api/diary/simulator-bridge/pair-claim {", config)
        self.assertNotIn("location = /api/diary/simulator-bridge/pair-code {", config)
        self.assertIn("location /api/ {\n        auth_request /_auth;", config)


if __name__ == "__main__":
    unittest.main()
