"""Contract checks for the opt-in send-only Telegram Gateway."""
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import telegram_bot
import telegram_gateway_client as gateway


class TelegramGatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {
            "BYBITSCANNER_TELEGRAM_OUTBOX_DB": self.tmp.name + "/telegram.sqlite3",
            "BYBITSCANNER_TELEGRAM_GATEWAY_URL": "https://relay.example.org/v1/send",
            "BYBITSCANNER_TELEGRAM_GATEWAY_SECRET": "x" * 48,
            "TELEGRAM_CHAT_ID": "12345",
            "HTTPS_PROXY": "socks5h://127.0.0.1:10809",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

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
    def test_fail_closed_no_direct_fallback(self, session_cls):
        session_cls.return_value.post.side_effect = gateway.requests.ConnectionError()
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "12345", "hello")
        self.assertEqual(session_cls.return_value.post.call_count, 2)


    @patch("telegram_gateway_client.requests.Session")
    def test_failed_gateway_retains_uncertain_alert(self, session_cls):
        session_cls.return_value.post.side_effect = gateway.requests.ConnectionError()
        with self.assertRaises(gateway.TelegramGatewayError):
            telegram_bot.send_message("unused-token", "12345", "important alert")
        import telegram_gateway_outbox
        self.assertEqual(telegram_gateway_outbox.counts().get("UNKNOWN"), None)

    @patch("telegram_gateway_client.requests.Session")
    def test_success_is_recorded_as_api_accepted(self, session_cls):
        response = MagicMock(status_code=200)
        def result():
            event_id = session_cls.return_value.post.call_args.kwargs["json"]["event_id"]
            return {"ok": True, "event_id": event_id,
                    "stage": "accepted_by_telegram_api", "telegram_message_id": 123}
        response.json.side_effect = result
        session_cls.return_value.post.return_value = response
        telegram_bot.send_message("unused-token", "12345", "important alert")
        import telegram_gateway_outbox
        self.assertEqual(telegram_gateway_outbox.counts().get("ACCEPTED"), None)


if __name__ == "__main__":
    unittest.main()
