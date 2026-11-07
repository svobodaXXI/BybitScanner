import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from workspace_ready_telegram import send_ready_workspace


class WorkspaceReadyTelegramTests(unittest.TestCase):
    def payload(self, directory):
        return dict(token="test-token", owner_chat_id="owner", base_url="https://terminal.example.com",
                    mode="EDITOR", symbol="BTCUSDT", timeframe="5m", signal_id="signal-1",
                    gateway_ready=True, access_policy_verified=True, qr_directory=Path(directory))

    @patch("workspace_ready_telegram.send_ready_workspace")
    @patch("workspace_ready_telegram.verify_workspace_gateway", return_value=False)
    def test_checked_entrypoint_blocks_unverified_gateway(self, probe, send):
        from workspace_ready_telegram import send_ready_workspace_checked
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                send_ready_workspace_checked(
                    "test-token", "owner", access_client_id="id",
                    access_client_secret="secret", base_url="https://terminal.example.com",
                    mode="EDITOR", symbol="BTCUSDT", timeframe="5m",
                    signal_id=None, qr_directory=Path(tmp))
        send.assert_not_called()

    @patch("workspace_ready_telegram.send_photo", return_value={"ok": True, "result": {"message_id": 42}})
    @patch("workspace_ready_telegram.write_workspace_qr")
    def test_owner_receives_link_and_qr_only_after_ready(self, qr, send):
        with tempfile.TemporaryDirectory() as tmp:
            send_ready_workspace(**self.payload(tmp))
        self.assertTrue(qr.called)
        self.assertEqual(send.call_args.args[1], "owner")
        button = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertIn("mode=EDITOR", button["url"])
        self.assertIn("signal_id=signal-1", button["url"])
        self.assertNotIn("token=", button["url"])

    @patch("workspace_ready_telegram.send_photo")
    @patch("workspace_ready_telegram.write_workspace_qr")
    def test_unverified_gateway_cannot_generate_qr_or_send_ready(self, qr, send):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("gateway_ready", "access_policy_verified"):
                kwargs = self.payload(tmp)
                kwargs[key] = False
                with self.assertRaises(RuntimeError):
                    send_ready_workspace(**kwargs)
        qr.assert_not_called()
        send.assert_not_called()

    @patch("workspace_ready_telegram.send_photo")
    @patch("workspace_ready_telegram.write_workspace_qr")
    def test_truthy_but_unverified_readiness_never_sends_ready(self, qr, send):
        with tempfile.TemporaryDirectory() as tmp:
            for key in ("gateway_ready", "access_policy_verified"):
                for invalid in ("false", "true", 1, [], {"verified": True}):
                    with self.subTest(key=key, invalid=invalid):
                        kwargs = self.payload(tmp)
                        kwargs[key] = invalid
                        with self.assertRaises(RuntimeError):
                            send_ready_workspace(**kwargs)
        qr.assert_not_called()
        send.assert_not_called()

    @patch("workspace_ready_telegram.send_photo", return_value={"ok": False})
    @patch("workspace_ready_telegram.write_workspace_qr")
    def test_telegram_failure_is_not_reported_as_success(self, qr, send):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "not confirmed"):
                send_ready_workspace(**self.payload(tmp))

    @patch("workspace_ready_telegram.send_photo")
    @patch("workspace_ready_telegram.write_workspace_qr")
    def test_ambiguous_gateway_success_does_not_claim_qr_delivered(self, qr, send):
        with tempfile.TemporaryDirectory() as tmp:
            for response in (
                {"ok": True},
                {"ok": True, "result": {}},
                {"ok": True, "result": {"message_id": None}},
                {"ok": True, "result": {"message_id": ""}},
                {"ok": True, "result": {"message_id": "42"}},
                {"ok": True, "result": {"message_id": True}},
                {"ok": True, "result": {"message_id": 0}},
                {"ok": True, "result": {"message_id": -1}},
                {"ok": True, "result": []},
                None,
            ):
                with self.subTest(response=response):
                    send.return_value = response
                    with self.assertRaisesRegex(RuntimeError, "not confirmed"):
                        send_ready_workspace(**self.payload(tmp))
            send.return_value = {"ok": True, "result": {"message_id": 48}}
            result = send_ready_workspace(**self.payload(tmp))
            self.assertEqual(result["result"]["message_id"], 48)
            self.assertEqual(send.call_args.args[1], "owner")
            self.assertIn("mode=EDITOR",
                          send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["url"])


if __name__ == "__main__":
    unittest.main()
