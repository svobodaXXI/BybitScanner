import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


# config.py is intentionally local/ignored because it contains machine-specific
# credentials.  The repository verifier runs in a tracked-only worktree, so this
# focused unit test must provide only the import-time configuration surface it
# owns instead of depending on a developer machine's secret-bearing config.py.
# Mirrors the same stub pattern already used by test_telegram_robot_control.py
# and test_telegram_robot_handoff.py, extended with the extra attributes
# main.py/analyzer/bybit_api need at import time.
config_stub = types.ModuleType("config")
config_stub.TELEGRAM_TOKEN = "test-token"
config_stub.TELEGRAM_CHAT_ID = "42"
config_stub.TELEGRAM_CHAT_IDS = ("42",)
config_stub.TELEGRAM_ENABLED = True
config_stub.TELEGRAM_TEST_MODE = False
config_stub.TIMEFRAME = "1"
config_stub.CANDLE_LIMIT = 200
config_stub.MODE = "hunter"
config_stub.MIN_SCORE = 30
config_stub.MAX_SYMBOLS = None
config_stub.BYBIT_CATEGORY = "linear"
sys.modules["config"] = config_stub

import main
import notification


class TelegramSignalFormattingTests(unittest.TestCase):
    def _result(self, **overrides):
        base = {
            "symbol": "1000NEIROCTOUSDT",
            "pattern": "Falling Wedge",
            "final_score": 78,
            "timeframe": "1",
            "confirmation": {"breakout": False, "retest": False},
            "quality": {"quality": "Watch"},
        }
        base.update(overrides)
        return base

    def test_first_line_has_status_circle_and_scanner_symbol(self):
        message = notification.format_signal(self._result())

        first_line = message.splitlines()[0]
        self.assertEqual(first_line, "Сканер: 1000NEIROCTOUSDT 🟢")

    def test_full_card_matches_the_approved_target_example(self):
        message = notification.format_signal(self._result(
            confirmation={"breakout": True, "retest": False},
            quality={"quality": "A Setup"},
        ))

        self.assertEqual(
            message,
            "Сканер: 1000NEIROCTOUSDT 🟠\n"
            "Паттерн: Нисходящий клин\n"
            "Таймфрейм: 1м\n"
            "\n"
            "Баллы: 78",
        )

    def test_no_separate_signal_type_line(self):
        message = notification.format_signal(self._result())

        self.assertNotIn("BybitCleanScanner", message)
        self.assertNotIn("CONFIRMED", message)
        self.assertNotIn("EARLY SIGNAL", message)

    def test_no_direction_line(self):
        message = notification.format_signal(self._result(
            confirmation={"breakout": True, "retest": False, "direction": "LONG"},
        ))

        self.assertNotIn("Направление", message)
        self.assertNotIn("LONG", message)

    def test_timeframe_line_uses_russian_compact_rendering(self):
        message = notification.format_signal(self._result(timeframe="5"))

        self.assertIn("Таймфрейм: 5м", message)

    def test_score_is_the_last_line(self):
        message = notification.format_signal(self._result(final_score=91))

        self.assertEqual(message.splitlines()[-1], "Баллы: 91")

    def test_stage_forming_when_not_mature_and_no_breakout(self):
        circle = notification.signal_stage_circle(self._result(
            confirmation={"breakout": False, "retest": False},
            quality={"quality": "Weak Setup"},
        ))
        self.assertEqual(circle, "🟢")

    def test_stage_mature_pre_breakout_when_structure_valid_but_no_breakout(self):
        circle = notification.signal_stage_circle(self._result(
            confirmation={"breakout": False, "retest": False},
            quality={"quality": "B Setup"},
        ))
        self.assertEqual(circle, "🟡")

    def test_stage_post_breakout_waiting_retest(self):
        circle = notification.signal_stage_circle(self._result(
            confirmation={"breakout": True, "retest": False},
            quality={"quality": "A Setup"},
        ))
        self.assertEqual(circle, "🟠")

    def test_stage_post_retest_late_entry(self):
        circle = notification.signal_stage_circle(self._result(
            confirmation={"breakout": True, "retest": True},
            quality={"quality": "Elite Setup"},
        ))
        self.assertEqual(circle, "🔴")

    def test_tradingview_url_keeps_authoritative_full_symbol(self):
        keyboard = notification.build_tradingview_keyboard(
            "CROUSDT",
            "5",
            include_review_actions=False,
        )

        tradingview_url = keyboard[
            "inline_keyboard"
        ][0][0]["url"]
        self.assertIn("CROUSDT", tradingview_url)


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
                notification.config,
                "TELEGRAM_CHAT_ID",
                "owner",
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

        owner_keyboard = (
            photo_mock.call_args_list[0]
            .kwargs["reply_markup"]["inline_keyboard"]
        )
        friend_keyboard = (
            photo_mock.call_args_list[1]
            .kwargs["reply_markup"]["inline_keyboard"]
        )

        self.assertEqual(len(owner_keyboard), 3)
        self.assertEqual(
            [button["text"] for row in owner_keyboard for button in row],
            [
                "📈 Open TradingView",
                "📌 В разбор",
                "✅ Хороший",
                "❌ Геометрия",
                "⚓ Anchor/START",
            ],
        )
        self.assertEqual(len(friend_keyboard), 1)
        self.assertEqual(
            [button["text"] for button in friend_keyboard[0]],
            ["📈 Open TradingView"],
        )

    def test_two_non_owner_recipients_receive_only_tradingview(self):
        with tempfile.TemporaryDirectory() as directory:
            chart = Path(directory) / "BTCUSDT_analysis.png"
            chart.write_bytes(b"test-image")

            with patch.object(
                notification.config,
                "TELEGRAM_CHAT_IDS",
                ("owner", "friend-one", "friend-two"),
            ), patch.object(
                notification.config,
                "TELEGRAM_CHAT_ID",
                "owner",
            ), patch.object(
                notification,
                "CHARTS_DIR",
                directory,
            ), patch.object(
                notification,
                "send_message",
                return_value={"ok": True},
            ), patch.object(
                notification,
                "send_photo",
                return_value={"ok": True},
            ) as photo_mock:
                delivered = notification.send_signal(self.signal())

        self.assertTrue(delivered)
        self.assertEqual(photo_mock.call_count, 3)

        for photo_call in photo_mock.call_args_list[1:]:
            keyboard = photo_call.kwargs[
                "reply_markup"
            ]["inline_keyboard"]
            self.assertEqual(len(keyboard), 1)
            self.assertEqual(
                [button["text"] for button in keyboard[0]],
                ["📈 Open TradingView"],
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


class ScanStartedDeliveryTests(unittest.TestCase):
    def test_scan_started_message_reports_mode_score_and_symbol_count(self):
        message = main.build_scan_started_message(
            "hunter",
            60,
            18,
        )

        self.assertIn("Сканер запущен", message)
        self.assertIn("Mode: hunter", message)
        self.assertIn("Minimum Score: 60", message)
        self.assertIn("Symbols: 18", message)

    def test_scan_started_message_reflects_different_parameters(self):
        message = main.build_scan_started_message(
            "sniper",
            75,
            758,
        )

        self.assertIn("Mode: sniper", message)
        self.assertIn("Minimum Score: 75", message)
        self.assertIn("Symbols: 758", message)

    def test_scan_started_is_sent_to_all_recipients(self):
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

        started_calls = [
            item
            for item in message_mock.call_args_list
            if "Сканер запущен" in item.args[2]
        ]

        self.assertEqual(len(started_calls), 2)
        self.assertEqual(
            [item.args[1] for item in started_calls],
            ["owner", "friend"],
        )
        for item in started_calls:
            self.assertIn("Symbols: 0", item.args[2])


class ScanFinishedDeliveryTests(unittest.TestCase):
    def test_scan_finished_message_reports_zero_approved_signals(self):
        message = main.build_scan_finished_message(
            0,
            0,
            10,
            1,
            2,
        )

        self.assertEqual(message.splitlines()[0], "🏁 Сканирование завершено")
        self.assertIn("Найдено сигналов: 0", message)
        self.assertIn("Отправлено в Telegram: 0", message)
        self.assertIn("Просканировано тикеров: 10", message)

    def test_scan_finished_message_reports_three_approved_signals(self):
        message = main.build_scan_finished_message(
            3,
            2,
            5,
            1,
            2,
        )

        self.assertEqual(message.splitlines()[0], "🏁 Сканирование завершено")
        self.assertIn("Найдено сигналов: 3", message)
        self.assertIn("Отправлено в Telegram: 2", message)
        self.assertIn("Просканировано тикеров: 5", message)

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

        finished_calls = [
            item
            for item in message_mock.call_args_list
            if "Сканирование завершено" in item.args[2]
        ]

        self.assertEqual(len(finished_calls), 2)
        self.assertEqual(
            [item.args[1] for item in finished_calls],
            ["owner", "friend"],
        )
        for item in finished_calls:
            self.assertIn("Сканирование завершено", item.args[2])
            self.assertIn("Найдено сигналов: 0", item.args[2])


if __name__ == "__main__":
    unittest.main()
