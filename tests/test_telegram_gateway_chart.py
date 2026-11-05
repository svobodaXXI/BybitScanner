"""Focused fail-closed Gateway chart upload checks."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import telegram_bot
import telegram_gateway_client as gateway


class GatewayChartTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "BYBITSCANNER_TELEGRAM_GATEWAY_URL": "https://gateway.example/v1/send",
            "BYBITSCANNER_TELEGRAM_GATEWAY_SECRET": "s" * 48,
            "TELEGRAM_CHAT_ID": "12345",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    @patch("telegram_gateway_client.requests.Session")
    def test_chart_transport_uses_gateway(self, session_factory):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chart.png"
            path.write_bytes(b"small-test-image")
            response = MagicMock(status_code=200)
            response.json.return_value = {"ok": True}
            session_factory.return_value.post.return_value = response
            result = telegram_bot.send_photo("token", "12345", str(path), caption="chart")
            self.assertTrue(result["ok"])
            args = session_factory.return_value.post.call_args
            self.assertTrue(args.args[0].endswith("/v1/photo-card"))
            self.assertEqual(args.kwargs["files"]["photo"][1], b"small-test-image") 
            self.assertEqual(args.kwargs["data"]["caption"], "chart")
            self.assertFalse(session_factory.return_value.trust_env)

    @patch("telegram_gateway_client.requests.Session")
    def test_wrong_recipient_rejected_before_network(self, session_factory):
        with self.assertRaises(gateway.TelegramGatewayError):
            gateway.send_photo_upload("other", "anything.png")
        session_factory.assert_not_called()

    @patch("telegram_gateway_client.requests.Session")
    def test_oversize_rejected_before_network(self, session_factory):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "chart.png"
            path.write_bytes(b"x" * 2000001)
            with self.assertRaises(gateway.TelegramGatewayError):
                gateway.send_photo_upload("12345", str(path))
        session_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
