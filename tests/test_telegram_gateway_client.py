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
    def test_photo_with_keyboard_is_one_gateway_request(self, session_cls):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True, "result": {"message_id": 11}}
        session_cls.return_value.post.return_value = response
        markup = {"inline_keyboard": [[{"text": "К сигналу", "callback_data": "signal:123"}]]}
        with TemporaryDirectory() as root:
            path = Path(root) / "signal.png"
            path.write_bytes(b"PNG")
            result = gateway.send_photo_upload("12345", path, caption="🪞 MIRROR · ALCHUSDT · 5m", reply_markup=markup)
        self.assertTrue(result["ok"])
        self.assertEqual(session_cls.return_value.post.call_count, 1)
        args = session_cls.return_value.post.call_args
        self.assertTrue(args.args[0].endswith("/v1/photo-card"))
        self.assertEqual(args.kwargs["data"]["caption"], "🪞 MIRROR · ALCHUSDT · 5m")
        self.assertEqual(args.kwargs["files"]["photo"][1], b"PNG")
        import json
        self.assertEqual(json.loads(args.kwargs["data"]["reply_markup"]), markup)

    @patch("telegram_gateway_client.requests.Session")
    def test_file_id_repost_with_keyboard_is_one_gateway_request(self, session_cls):
        response = MagicMock(status_code=200)
        response.json.return_value = {"ok": True, "result": {"message_id": 55}}
        session_cls.return_value.post.return_value = response
        markup = {"inline_keyboard": [[{"text": "TradingView", "url": "https://example.org"}]]}
        result = gateway.send_photo_file_id("12345", "existing-file-id", caption="🔁 ДУБЛИРОВАНИЕ", reply_markup=markup)
        self.assertTrue(result["ok"])
        self.assertEqual(session_cls.return_value.post.call_count, 1)
        args = session_cls.return_value.post.call_args
        self.assertTrue(args.args[0].endswith("/v1/photo-card"))
        self.assertEqual(args.kwargs["json"]["caption"], "🔁 ДУБЛИРОВАНИЕ")
        self.assertEqual(args.kwargs["json"]["reply_markup"], markup)

    @patch("telegram_gateway_client.requests.Session")
    def test_photo_failure_has_no_split_fallback_or_duplicate_upload(self, session_cls):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        response = MagicMock(status_code=404)
        response.json.return_value = {"ok": False, "error": "not_found"}
        session_cls.return_value.post.return_value = response
        with TemporaryDirectory() as root:
            path = Path(root) / "signal.png"
            path.write_bytes(b"PNG")
            with patch.object(gateway, "send_text") as send_text:
                with self.assertRaises(gateway.TelegramGatewayError):
                    gateway.send_photo_upload("12345", path, caption="🪞 MIRROR", reply_markup={"inline_keyboard": []})
                send_text.assert_not_called()
        self.assertEqual(session_cls.return_value.post.call_count, 1)

    @patch("telegram_gateway_client.requests.Session")
    def test_fail_closed_no_direct_fallback(self, session_cls):
        session_cls.return_value.post.side_effect = gateway.requests.ConnectionError()
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "12345", "hello")
        self.assertEqual(session_cls.return_value.post.call_count, 2)




if __name__ == "__main__":
    unittest.main()
