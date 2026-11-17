"""Offline proof that a paired local agent only opens typed Machine Time IDs."""
from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.local_replay_viewer import launch_bridge_agent as agent


EPISODE = "te_" + "a" * 24
REQUEST = "b" * 32


class MockOpener:
    def __init__(self, answers):
        self.answers = list(answers)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if timeout != 5:
            raise AssertionError("unbounded HTTP timeout")
        data = io.BytesIO(json.dumps(self.answers.pop(0)).encode("utf-8"))
        data.status = 200
        return data


class PairedAdapterTests(unittest.TestCase):
    def setUp(self):
        probe = patch.object(agent, "viewer_is_running", return_value=False)
        probe.start()
        self.addCleanup(probe.stop)
        self.config = {
            "origin": "https://example.test", "device_id": "owner-pc",
            "token": "A" * 64,
        }

    def test_default_remains_disabled_without_config(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "launch-bridge.json"
            self.assertIsNone(agent.read_config(path))
            with patch.object(agent, "CONFIG_PATH", path), patch.object(
                    agent, "read_config", return_value=None):
                self.assertEqual(agent.main(["--install-if-configured"]), 0)

    def test_rejects_invalid_local_pairing_and_untrusted_redirect_origins(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "launch-bridge.json"
            def load(raw):
                path.write_text(json.dumps(raw), encoding="utf-8")
                return agent.read_config(path)
            valid = {"schema": agent.SCHEMA, **self.config}
            self.assertEqual(load(valid), self.config)
            for bad in (
                {**valid, "origin": "http://example.test"},
                {**valid, "origin": "https://example.test/login"},
                {**valid, "origin": "https://example.test@evil.test"},
                {**valid, "token": "short"},
                {**valid, "device_id": "../../other"},
                {**valid, "command": "powershell"},
            ):
                with self.subTest(bad=bad), self.assertRaises(agent.AgentConfigError):
                    load(bad)

    def test_owner_pinned_pairing_is_verified_then_saved_only_once(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "simulator-v2-data"
            folder.mkdir()
            config_path = folder / "launch-bridge.json"
            (folder / "trusted-statistics-origin.txt").write_text(
                "https://example.test\n", encoding="ascii",
            )
            with patch.object(agent, "CONFIG_PATH", config_path), \
                 patch.object(agent, "_send", return_value={"ok": True, "state": "IDLE"}) as probe, \
                 patch.object(agent, "install_if_configured", return_value=True) as install:
                agent.pair_device("owner-pc", "A" * 64)
                self.assertEqual(agent.read_config(), self.config)
                self.assertEqual(json.loads(config_path.read_text())["schema"], agent.SCHEMA)
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(probe.call_args.kwargs["path"],
                    "/api/diary/simulator-bridge/poll?device_id=owner-pc&viewer_running=0")
                # Same pairing is idempotent and never rewrites the file.
                content = config_path.read_bytes()
                agent.pair_device("owner-pc", "A" * 64)
                self.assertEqual(config_path.read_bytes(), content)
                self.assertEqual(probe.call_count, 1)
                self.assertEqual(install.call_count, 2)
                with self.assertRaisesRegex(agent.AgentConfigError, "existing_device_pairing_preserved"):
                    agent.pair_device("owner-laptop", "B" * 64)
                self.assertEqual(config_path.read_bytes(), content)

    def test_pairing_rejects_missing_origin_or_unverified_token_without_side_effects(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "simulator-v2-data"
            folder.mkdir()
            config_path = folder / "launch-bridge.json"
            pinned = folder / "trusted-statistics-origin.txt"
            with patch.object(agent, "CONFIG_PATH", config_path), \
                 patch.object(agent, "install_if_configured") as install:
                with self.assertRaises(agent.AgentConfigError):
                    agent.pair_device("owner-pc", "A" * 64)
                pinned.write_text("https://evil.test/path\n")
                with self.assertRaises(agent.AgentConfigError):
                    agent.pair_device("owner-pc", "A" * 64)
                pinned.write_text("https://example.test\n")
                with patch.object(agent, "_send", return_value={"ok": True, "state": "QUEUED"}):
                    with self.assertRaises(agent.AgentConfigError):
                        agent.pair_device("owner-pc", "A" * 64)
                for token in ("short", "A" * 63 + "&"):
                    with self.assertRaises(agent.AgentConfigError):
                        agent.pair_device("owner-pc", token)
                self.assertFalse(config_path.exists())
                install.assert_not_called()

    def test_polls_only_fixed_https_endpoint_and_acks_exact_single_id(self):
        opener = MockOpener([
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": REQUEST, "episode_id": EPISODE},
            {"ok": True, "state": "LAUNCHED"},
        ])
        launched = []
        self.assertEqual(
            agent.poll_once(self.config, opener=opener, launch=launched.append),
            "OPEN_REQUESTED",
        )
        self.assertEqual(launched, [EPISODE])
        self.assertEqual(len(opener.requests), 2)
        get, post = opener.requests
        self.assertEqual(
            get.full_url,
            "https://example.test/api/diary/simulator-bridge/poll?device_id=owner-pc&viewer_running=0",
        )
        self.assertEqual(get.get_method(), "GET")
        self.assertEqual(post.full_url, "https://example.test/api/diary/simulator-bridge/ack")
        self.assertEqual(post.get_method(), "POST")
        self.assertEqual(json.loads(post.data.decode("utf-8")), {
            "device_id": "owner-pc", "request_id": REQUEST, "launched": True,
        })
        self.assertNotIn(self.config["token"], get.full_url + post.full_url)
        self.assertEqual(
            get.get_header("X-bybitscanner-simulator-device-token"), self.config["token"],
        )

    def test_reports_existing_local_viewer_without_sending_process_details(self):
        with patch.object(agent, "viewer_is_running", return_value=True):
            opener = MockOpener([{"ok": True, "state": "IDLE"}])
            self.assertEqual(agent.poll_once(self.config, opener=opener), "IDLE")
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(opener.requests[0].full_url,
                         "https://example.test/api/diary/simulator-bridge/poll?device_id=owner-pc&viewer_running=1")

    def test_forged_commands_never_reach_launcher_or_ack(self):
        for instruction in (
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": REQUEST, "episode_id": "calc.exe"},
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": REQUEST, "episode_id": EPISODE, "path": "C:\\Temp"},
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": "not_an_id", "episode_id": EPISODE},
            {"ok": True, "state": "RUN_SHELL", "command": "powershell"},
        ):
            opener = MockOpener([instruction])
            launches = []
            with self.subTest(instruction=instruction), self.assertRaises(agent.AgentConfigError):
                agent.poll_once(self.config, opener=opener, launch=launches.append)
            self.assertFalse(launches)
            self.assertEqual(len(opener.requests), 1)

    def test_open_failure_is_reported_without_retry(self):
        opener = MockOpener([
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": REQUEST, "episode_id": EPISODE},
            {"ok": True, "state": "FAILED"},
        ])
        def failed(_):
            raise OSError("Browser unavailable")
        self.assertEqual(
            agent.poll_once(self.config, opener=opener, launch=failed),
            "OPEN_FAILED",
        )
        ack = json.loads(opener.requests[1].data)
        self.assertIs(ack["launched"], False)

    def test_wrong_ack_cannot_claim_launch(self):
        opener = MockOpener([
            {"ok": True, "state": "OPEN_EPISODE",
             "request_id": REQUEST, "episode_id": EPISODE},
            {"ok": True, "state": "FAILED"},
        ])
        with self.assertRaises(agent.AgentConfigError):
            agent.poll_once(self.config, opener=opener, launch=lambda _: None)


if __name__ == "__main__":
    unittest.main()
