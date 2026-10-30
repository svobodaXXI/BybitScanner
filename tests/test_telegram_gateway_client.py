"""Contract checks for the opt-in send-only Telegram Gateway."""
import os
import unittest
from unittest.mock import patch, MagicMock

import telegram_bot
import telegram_gateway_client as gateway


class TelegramGatewayTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "BYBITSCANNER_TELEGRAM_GATEWAY_URL": "https://relay.example.org/v1/send",
            "BYBITSCANNER_TELEGRAM_GATEWAY_SECRET": "x" * 48,
            "TELEGRAM_CHAT_ID": "12345",
            "HTTPS_PROXY": "socks5h://127.0.0.1:10809",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    @patch("telegram_gateway_client.requests.Session")
    def test_send_uses_gateway_without_legacy_proxy(self, session_cls):
        response = MagicMock(status_code=200)
        def result():
            args = session_cls.return_value.post.call_args
            return {"ok": True, "event_id": args.kwargs["json"]["event_id"],
                    "stage": "accepted_by_telegram_api", "telegram_message_id": 99}
        response.json.side_effect = result
        session_cls.return_value.post.return_value = response

        result = telegram_bot.send_message("unused-token", "12345", "hello")
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["message_id"], 99)
        self.assertIs(session_cls.return_value.trust_env, False)
        self.assertTrue(session_cls.return_value.post.call_args.args[0].endswith("/v1/send"))

    @patch("telegram_gateway_client.requests.Session")
    def test_forbid_unapproved_recipient_and_invalid_keyboard(self, session_cls):
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "99999", "hello")
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "12345", "hello", "invalid keyboard")
        session_cls.assert_not_called()

    @patch("telegram_gateway_client.requests.Session")
    def test_photo_with_keyboard_delivers_image_then_separate_actions(self, session_cls):
        from tempfile import TemporaryDirectory
        from pathlib import Path

        response = MagicMock(status_code=200)
        def result():
            call = session_cls.return_value.post.call_args
            if call.args[0].endswith("/v1/photo-upload"):
                return {"ok": True, "result": {"message_id": 11}}
            return {"ok": True, "event_id": call.kwargs["json"]["event_id"],
                    "stage": "accepted_by_telegram_api", "telegram_message_id": 12}
        response.json.side_effect = result
        session_cls.return_value.post.return_value = response
        with TemporaryDirectory() as root:
            path = Path(root) / "signal.png"
            path.write_bytes(b"PNG")
            markup = {"inline_keyboard": [[{"text": "К сигналу", "callback_data": "signal:123"}]]}
            sent = gateway.send_photo_upload("12345", path, caption="Scanner", reply_markup=markup)
        self.assertTrue(sent["ok"])
        self.assertTrue(sent["keyboard_delivered"])
        calls = session_cls.return_value.post.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].args[0].endswith("/v1/photo-upload"))
        self.assertTrue(calls[1].args[0].endswith("/v1/send"))
        self.assertEqual(calls[1].kwargs["json"]["reply_markup"], markup)

    @patch("telegram_gateway_client.requests.Session")
    def test_archived_photo_file_id_allows_separate_keyboard(self, session_cls):
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True, "result": {"message_id": 55}}
        session_cls.return_value.post.return_value = response
        markup = {"inline_keyboard": [[{"text": "TradingView", "url": "https://example.org"}]]}
        with patch.object(gateway, "send_text", return_value={"ok": True}) as send_menu:
            sent = gateway.send_photo_file_id("12345", "existing-file-id", reply_markup=markup)
        self.assertTrue(sent["ok"])
        self.assertTrue(sent["keyboard_delivered"])
        send_menu.assert_called_once_with("12345", "📎 Действия к графику выше",
                                          reply_markup=markup)
        self.assertEqual(session_cls.return_value.post.call_count, 1)

    @patch("telegram_gateway_client.requests.Session")
    def test_photo_success_menu_failure_does_not_retry_photo(self, session_cls):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True, "result": {"message_id": 11}}
        session_cls.return_value.post.return_value = response
        with TemporaryDirectory() as root:
            path = Path(root) / "signal.png"
            path.write_bytes(b"PNG")
            with patch.object(gateway, "send_text", side_effect=gateway.TelegramGatewayError("offline")):
                sent = gateway.send_photo_upload("12345", path, reply_markup={"inline_keyboard": []})
        self.assertTrue(sent["ok"])
        self.assertFalse(sent["keyboard_delivered"])
        self.assertEqual(session_cls.return_value.post.call_count, 1)

    @patch("telegram_gateway_client.requests.Session")
    def test_fail_closed_no_direct_fallback(self, session_cls):
        session_cls.return_value.post.side_effect = gateway.requests.ConnectionError()
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "12345", "hello")
        self.assertEqual(session_cls.return_value.post.call_count, 2)




if __name__ == "__main__":
    unittest.main()
