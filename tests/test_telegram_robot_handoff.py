import sys
import types
import unittest
from unittest.mock import patch


# config.py is intentionally local/ignored because it contains machine-specific
# credentials.  The repository verifier runs in a tracked-only worktree, so this
# focused unit test must provide only the import-time configuration surface it
# owns instead of depending on a developer machine's secret-bearing config.py.
config_stub = types.ModuleType("config")
config_stub.TELEGRAM_TOKEN = "test-token"
config_stub.TELEGRAM_CHAT_ID = "42"
config_stub.TELEGRAM_CHAT_IDS = ("42",)
config_stub.TELEGRAM_ENABLED = True
config_stub.TELEGRAM_TEST_MODE = False
config_stub.TIMEFRAME = "1"
sys.modules["config"] = config_stub

import notification
import telegram_review
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord


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

        approved_record = RobotCandidateRecord(
            candidate_id="abc123",
            trading_account_id=TradingAccountId("paper"),
            symbol=Symbol("ONGUSDT"),
            status="APPROVED",
            signal_snapshot={},
            snapshot_sha256="0" * 64,
            robot_state=None,
            state_revision=1,
            approved_at_ms=0,
            updated_at_ms=0,
        )

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "admit_robot_candidate",
            return_value=(approved_record, True),
        ) as admit_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        admit_mock.assert_called_once()
        args, kwargs = admit_mock.call_args
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
            "admit_robot_candidate",
        ) as admit_mock, patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        admit_mock.assert_not_called()
        answer_mock.assert_called_once_with(
            "callback-2",
            "Недостаточно прав",
        )


if __name__ == "__main__":
    unittest.main()
