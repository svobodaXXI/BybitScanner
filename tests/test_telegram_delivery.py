import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import notification


class TelegramRecipientNormalizationTests(unittest.TestCase):
    def test_legacy_chat_id_fallback(self):
        with patch.object(notification.config, "TELEGRAM_CHAT_IDS", ()), \
                patch.object(notification.config, "TELEGRAM_CHAT_ID", "123"):
            self.assertEqual(notification.get_telegram_chat_ids(), ("123",))

    def test_duplicate_and_empty_ids_are_removed_in_order(self):
        configured = ("", " 123 ", None, "456", "123", "   ", 456)

        with patch.object(
            notification.config,
            "TELEGRAM_CHAT_IDS",
            configured,
        ):
            self.assertEqual(
                notification.get_telegram_chat_ids(),
                ("123", "456"),
            )


class TelegramSignalDeliveryTests(unittest.TestCase):
    def signal(self):
        return {
            "symbol": "BTCUSDT",
            "pattern": "Falling Wedge",
            "final_score": 80,
            "timeframe": "5",
            "confirmation": {
                "direction": "LONG",
                "confirmed": True,
            },
        }

    def test_two_recipients_receive_text_and_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "BTCUSDT_analysis.png"
            chart.write_bytes(b"test-image")

            with patch.object(
                notification.config,
                "TELEGRAM_CHAT_IDS",
                ("owner", "friend"),
            ), patch.object(
                notification,
                "CHARTS_DIR",
                directory,
            ), patch.object(
                notification,
                "send_message",
                return_value={"ok": True},
            ) as message_mock, patch.object(
                notification,
                "send_photo",
                return_value={"ok": True},
            ) as photo_mock:
                delivered = notification.send_signal(self.signal())

        self.assertTrue(delivered)
        self.assertEqual(
            [item.args[1] for item in message_mock.call_args_list],
            ["owner", "friend"],
        )
        self.assertEqual(
            [item.args[1] for item in photo_mock.call_args_list],
            ["owner", "friend"],
        )

    def test_first_recipient_failure_does_not_block_second(self):
        with patch.object(
            notification.config,
            "TELEGRAM_CHAT_IDS",
            ("owner", "friend"),
        ), patch.object(
            notification,
            "send_message",
            side_effect=[RuntimeError("owner unavailable"), {"ok": True}],
        ) as message_mock, patch.object(
            notification.os.path,
            "exists",
            return_value=False,
        ):
            delivered = notification.send_signal(self.signal())

        self.assertFalse(delivered)
        self.assertEqual(message_mock.call_count, 2)
        self.assertEqual(message_mock.call_args_list[1].args[1], "friend")

    def test_second_recipient_failure_does_not_cancel_first(self):
        with patch.object(
            notification.config,
            "TELEGRAM_CHAT_IDS",
            ("owner", "friend"),
        ), patch.object(
            notification,
            "send_message",
            side_effect=[{"ok": True}, {"ok": False, "description": "blocked"}],
        ) as message_mock, patch.object(
            notification.os.path,
            "exists",
            return_value=False,
        ):
            delivered = notification.send_signal(self.signal())

        self.assertFalse(delivered)
        self.assertEqual(message_mock.call_count, 2)
        self.assertEqual(message_mock.call_args_list[0].args[1], "owner")


class ScanFinishedDeliveryTests(unittest.TestCase):
    def test_scan_finished_is_sent_to_all_recipients(self):
        with patch.object(main, "get_symbols", return_value=[]), patch.object(
            notification.config,
            "TELEGRAM_CHAT_IDS",
            ("owner", "friend"),
        ), patch.object(
            notification,
            "send_message",
            return_value={"ok": True},
        ) as message_mock:
            main.main()

        self.assertEqual(message_mock.call_count, 2)
        self.assertEqual(
            [item.args[1] for item in message_mock.call_args_list],
            ["owner", "friend"],
        )
        for item in message_mock.call_args_list:
            self.assertIn("SCAN FINISHED", item.args[2])


if __name__ == "__main__":
    unittest.main()
