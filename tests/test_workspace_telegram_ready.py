import unittest
from unittest.mock import patch

from workspace_telegram_ready import send_workspace_ready


class WorkspaceTelegramReadyTests(unittest.TestCase):
    def test_requires_both_readiness_and_authenticated_access(self):
        sender = lambda *args, **kwargs: {"ok": True}
        for ready, access in [(False, True), (True, False), (False, False)]:
            with self.assertRaises(ValueError):
                send_workspace_ready(bot_token="fake", owner_chat_id="42",
                    https_origin="https://terminal.example.com", mode="EDITOR",
                    symbol="BTCUSDT", timeframe="5m", ready_verified=ready,
                    access_policy_verified=access, send_photo_func=sender)

    @patch("workspace_telegram_ready.write_workspace_qr")
    def test_owner_gets_same_link_in_caption_and_button(self, qr):
        qr.return_value = "/tmp/fake.png"
        received = []
        def send(*args, **kwargs):
            received.append((args, kwargs))
            return {"ok": True}
        url = send_workspace_ready(bot_token="fake", owner_chat_id="42",
            https_origin="https://terminal.example.com", mode="EDITOR",
            symbol="XDPUSDT", timeframe="5m", signal_id="sg-123",
            ready_verified=True, access_policy_verified=True, send_photo_func=send)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0][0][1], "42")
        self.assertIn(url, received[0][1]["caption"])
        self.assertEqual(received[0][1]["reply_markup"]["inline_keyboard"][0][0]["url"], url)
        self.assertIn("signal_id=sg-123", url)

    @patch("workspace_telegram_ready.write_workspace_qr")
    def test_delivery_failure_is_not_reported_as_ready(self, qr):
        qr.return_value = "/tmp/fake.png"
        with self.assertRaises(RuntimeError):
            send_workspace_ready(bot_token="fake", owner_chat_id="42",
                https_origin="https://terminal.example.com", mode="TERMINAL",
                symbol="BTCUSDT", timeframe="1m", ready_verified=True,
                access_policy_verified=True,
                send_photo_func=lambda *a, **kw: {"ok": False})


if __name__ == "__main__":
    unittest.main()
