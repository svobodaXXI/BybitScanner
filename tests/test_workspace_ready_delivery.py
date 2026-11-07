import contextlib
import io
import json
import sys
import types
import unittest
from unittest.mock import patch
from tools import workspace_ready_delivery as worker

ENV = {
    "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://terminal.example.com",
    "BYBITSCANNER_ACCESS_CLIENT_ID": "client",
    "BYBITSCANNER_ACCESS_CLIENT_SECRET": "secret",
    "BYBITSCANNER_TELEGRAM_OWNER_ID": "owner",
    "BYBITSCANNER_TELEGRAM_BOT_TOKEN": "token",
}

class WorkspaceReadyDeliveryTests(unittest.TestCase):
    @patch.dict(worker.os.environ, {}, clear=True)
    @patch.object(worker, "send_ready_workspace_checked")
    def test_without_secrets_does_not_send(self, send):
        self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen", side_effect=OSError("offline"))
    @patch.object(worker, "send_ready_workspace_checked")
    def test_local_server_unavailable_does_not_send(self, send, probe):
        self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_html_without_healthy_api_does_not_send(self, send, probe):
        page = probe.return_value.__enter__.return_value
        page.status = 200
        page.read.return_value = b'{"ok": false}'
        self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_only_authenticated_gateway_sender_receives_request(self, send, qr, probe):
        response = probe.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps({"ok": True}).encode()
        self.assertTrue(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["symbol"], "BTCUSDT")
        self.assertEqual(send.call_args.kwargs["access_client_secret"], "secret")
        qr.assert_called_once()

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_source_identity_is_kept_in_verified_mobile_qr(self, send, qr, probe):
        response = probe.return_value.__enter__.return_value
        response.status = 200
        response.read.return_value = json.dumps({"ok": True}).encode()
        signal = "source-original:" + "a" * 24
        self.assertTrue(worker.deliver_if_verified(
            "EDITOR", "BTCUSDT", "5m", signal_id=signal))
        self.assertEqual(send.call_args.kwargs["signal_id"], signal)
        self.assertIn("signal_id=source-original%3A", qr.call_args.args[0])

GATEWAY_ENV = {key: value for key, value in ENV.items() if "TELEGRAM" not in key}


def healthy(probe):
    response = probe.return_value.__enter__.return_value
    response.status = 200
    response.read.return_value = json.dumps({"ok": True}).encode()


class TelegramIdentityFallbackTests(unittest.TestCase):
    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_single_owner_config_reused_when_dedicated_pair_missing(self, send, qr, probe):
        healthy(probe)
        cfg = types.SimpleNamespace(
            TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID=" 4242 ",
            TELEGRAM_CHAT_IDS=("other-chat", "broadcast"),
        )
        output = io.StringIO()
        with patch.dict(sys.modules, {"config": cfg}), contextlib.redirect_stdout(output):
            self.assertTrue(worker.deliver_if_verified(
                "EDITOR", "BTCUSDT", "5m", signal_id="source-original:" + "a" * 24))
        self.assertEqual(send.call_args.args, ("cfg-token", "4242"))
        self.assertEqual(send.call_args.kwargs["access_client_secret"], "secret")
        self.assertEqual(send.call_args.kwargs["signal_id"], "source-original:" + "a" * 24)
        self.assertNotIn("cfg-token", output.getvalue())
        qr.assert_called_once()
        self.assertIn("signal_id=source-original%3A", qr.call_args.args[0])

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_complete_dedicated_pair_wins_even_if_config_is_broken(self, send, qr, probe):
        healthy(probe)
        with patch.dict(sys.modules, {"config": None}):
            self.assertTrue(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        self.assertEqual(send.call_args.args, ("token", "owner"))

    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_missing_or_incomplete_config_fails_closed_before_http(self, send, probe):
        for cfg in (
            None,
            types.SimpleNamespace(TELEGRAM_TOKEN="x", TELEGRAM_CHAT_ID=""),
            types.SimpleNamespace(TELEGRAM_TOKEN="", TELEGRAM_CHAT_ID="123"),
            types.SimpleNamespace(TELEGRAM_CHAT_IDS=("other",)),
            types.SimpleNamespace(TELEGRAM_TOKEN="x", TELEGRAM_CHAT_ID=True),
        ):
            with self.subTest(cfg=cfg), patch.dict(sys.modules, {"config": cfg}):
                self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()
        probe.assert_not_called()

    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_partially_configured_dedicated_pair_does_not_mix_owner_identities(self, send, probe):
        cfg = types.SimpleNamespace(TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID="cfg-owner")
        for extra in (
            {"BYBITSCANNER_TELEGRAM_BOT_TOKEN": "different-bot"},
            {"BYBITSCANNER_TELEGRAM_OWNER_ID": "different-owner"},
        ):
            with self.subTest(extra=extra), patch.dict(worker.os.environ, {**GATEWAY_ENV, **extra}, clear=True), patch.dict(sys.modules, {"config": cfg}):
                self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()
        probe.assert_not_called()

    @patch.dict(worker.os.environ, {}, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_config_cannot_replace_authenticated_https_requirement(self, send, probe):
        cfg = types.SimpleNamespace(TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID="owner")
        with patch.dict(sys.modules, {"config": cfg}):
            self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()
