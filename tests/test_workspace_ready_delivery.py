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


GATEWAY_ENV = {k: v for k, v in ENV.items() if "TELEGRAM" not in k}


def _config(**values):
    return types.SimpleNamespace(**values)


def _healthy(probe):
    response = probe.return_value.__enter__.return_value
    response.status = 200
    response.read.return_value = json.dumps({"ok": True}).encode()


class TelegramIdentityFallbackTests(unittest.TestCase):
    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_config_identity_is_used_when_dedicated_env_is_absent(self, send, qr, probe):
        _healthy(probe)
        cfg = _config(TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID=" 4242 ",
                      TELEGRAM_CHAT_IDS=("1", "2"))
        out, err = io.StringIO(), io.StringIO()
        with patch.dict(sys.modules, {"config": cfg}),                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertTrue(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        self.assertEqual(send.call_args.args, ("cfg-token", "4242"))
        # The Access service token still comes only from its dedicated env.
        self.assertEqual(send.call_args.kwargs["access_client_secret"], "secret")
        self.assertNotIn("cfg-token", out.getvalue() + err.getvalue())

    @patch.dict(worker.os.environ, ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "write_workspace_qr")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_dedicated_env_wins_over_config(self, send, qr, probe):
        _healthy(probe)
        cfg = _config(TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID="4242")
        with patch.dict(sys.modules, {"config": cfg}):
            self.assertTrue(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        self.assertEqual(send.call_args.args, ("token", "owner"))

    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_missing_config_fails_closed(self, send, probe):
        _healthy(probe)
        with patch.dict(sys.modules, {"config": None}):  # import raises ImportError
            self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()

    @patch.dict(worker.os.environ, GATEWAY_ENV, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_incomplete_config_identity_fails_closed(self, send, probe):
        _healthy(probe)
        for cfg in (_config(TELEGRAM_TOKEN="t", TELEGRAM_CHAT_ID=""),
                    _config(TELEGRAM_TOKEN="", TELEGRAM_CHAT_ID="1"),
                    _config(TELEGRAM_CHAT_IDS=("1",))):
            with patch.dict(sys.modules, {"config": cfg}):
                self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()

    @patch.dict(worker.os.environ, {}, clear=True)
    @patch.object(worker, "urlopen")
    @patch.object(worker, "send_ready_workspace_checked")
    def test_config_identity_never_replaces_https_or_access_requirements(self, send, probe):
        _healthy(probe)
        cfg = _config(TELEGRAM_TOKEN="cfg-token", TELEGRAM_CHAT_ID="4242")
        with patch.dict(sys.modules, {"config": cfg}):
            self.assertFalse(worker.deliver_if_verified("EDITOR", "BTCUSDT", "5m"))
        send.assert_not_called()
        probe.assert_not_called()

if __name__ == "__main__":
    unittest.main()
