import io
import json
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

if __name__ == "__main__":
    unittest.main()
