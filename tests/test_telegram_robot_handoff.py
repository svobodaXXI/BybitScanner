import unittest
from unittest.mock import patch

import notification
import telegram_review


class TelegramRobotHandoffTests(unittest.TestCase):
    def test_keyboard_contains_owner_robot_callback(self):
        keyboard = notification.build_tradingview_keyboard(
            "ONGUSDT",
            "1",
            include_review_actions=True,
            robot_candidate_id="abc123",
        )

        rows = keyboard["inline_keyboard"]
        robot_buttons = [
            button
            for row in rows
            for button in row
            if button.get("callback_data", "").startswith("robot:")
        ]

        self.assertEqual(
            robot_buttons,
            [
                {
                    "text": "🤖 Робот",
                    "callback_data": "robot:approve:abc123",
                }
            ],
        )

    def test_robot_callback_parser_is_separate_from_review_parser(self):
        self.assertIsNone(
            telegram_review._parse_callback("robot:approve:abc123")
        )
        self.assertEqual(
            telegram_review._parse_robot_callback(
                "robot:approve:abc123"
            ),
            {
                "kind": "robot",
                "action": "approve",
                "candidate_id": "abc123",
            },
        )

    def test_owner_callback_approves_candidate_once(self):
        callback_query = {
            "id": "callback-1",
            "data": "robot:approve:abc123",
            "from": {
                "id": 42,
                "username": "owner",
            },
            "message": {
                "message_id": 100,
                "chat": {"id": 42},
            },
        }

        approved_record = {
            "candidate_id": "abc123",
            "symbol": "ONGUSDT",
        }

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "approve_candidate",
            return_value=(approved_record, True),
        ) as approve_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        approve_mock.assert_called_once()
        args, kwargs = approve_mock.call_args
        self.assertEqual(args, ("abc123",))
        self.assertEqual(
            kwargs["approval"]["source"],
            "telegram_robot_button",
        )
        self.assertEqual(kwargs["approval"]["message_id"], 100)
        answer_mock.assert_called_once_with(
            "callback-1",
            "Робот: сигнал принят ✅",
        )

    def test_non_owner_robot_callback_is_rejected(self):
        callback_query = {
            "id": "callback-2",
            "data": "robot:approve:abc123",
            "from": {"id": 99},
            "message": {
                "message_id": 101,
                "chat": {"id": 99},
            },
        }

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "approve_candidate",
        ) as approve_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        approve_mock.assert_not_called()
        answer_mock.assert_called_once_with(
            "callback-2",
            "Недостаточно прав",
        )


if __name__ == "__main__":
    unittest.main()
