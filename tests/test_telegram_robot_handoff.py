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
from robot_candidate_store import RobotCandidateNotFound
from terminal.application.robot_admission import RobotAdmissionRejected
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, RobotRuntimeStateRecord


def _status(mode, recovery_status):
    return RobotRuntimeStateRecord(
        trading_account_id=TradingAccountId("paper"),
        mode=mode,
        recovery_status=recovery_status,
        reason=None,
        version=1,
        updated_at_ms=1000,
    )


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
        ) as answer_mock, patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=_status("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
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
            "🤖 Сигнал принят: ONGUSDT ✅",
        )

        # The status panel becomes the sole entry point into the control
        # keyboard (CR-ROBOT-CONTROL-001): every press re-sends it with live
        # state, regardless of admission outcome.
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertEqual(args[1], 42)
        self.assertIn("🤖 Сигнал принят: ONGUSDT ✅", args[2])
        self.assertIn("Статус робота: Запущен / Готов", args[2])
        confirm_button = kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(confirm_button["callback_data"], "robot:cmd:pause")

    def test_owner_callback_already_admitted_candidate_shows_late_notice(self):
        callback_query = {
            "id": "callback-already",
            "data": "robot:approve:abc123",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 106, "chat": {"id": 42}},
        }

        already_admitted_record = RobotCandidateRecord(
            candidate_id="abc123",
            trading_account_id=TradingAccountId("paper"),
            symbol=Symbol("1000NEIROCTOUSDT"),
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
            return_value=(already_admitted_record, False),
        ), patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=_status("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with(
            "callback-already",
            "🤖 Этот сигнал уже был принят ранее: 1000NEIROCTOUSDT ❗",
        )
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertIn(
            "🤖 Этот сигнал уже был принят ранее: 1000NEIROCTOUSDT ❗", args[2],
        )

    def test_rejected_admission_still_sends_status_panel_with_reason(self):
        callback_query = {
            "id": "callback-3",
            "data": "robot:approve:abc123",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 102, "chat": {"id": 42}},
        }

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "admit_robot_candidate",
            side_effect=RobotAdmissionRejected("Robot admission is not ready"),
        ), patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=_status("ROBOT_STOPPED", "ROBOT_STOPPED"),
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with(
            "callback-3",
            "Робот: отклонено — Robot admission is not ready",
        )
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertIn("Робот: отклонено — Robot admission is not ready", args[2])
        self.assertIn("Статус робота: Остановлен", args[2])
        start_button = kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(start_button["callback_data"], "robot:cmd:start")

    def test_stale_candidate_not_found_answers_with_specific_reason(self):
        callback_query = {
            "id": "callback-stale",
            "data": "robot:approve:abc123",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 105, "chat": {"id": 42}},
        }

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "admit_robot_candidate",
            side_effect=RobotCandidateNotFound("abc123"),
        ), patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=_status("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with(
            "callback-stale",
            "Робот: сигнал устарел или больше не найден",
        )
        send_mock.assert_called_once()

    def test_unexpected_admission_error_still_sends_status_panel(self):
        callback_query = {
            "id": "callback-4",
            "data": "robot:approve:abc123",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 103, "chat": {"id": 42}},
        }

        with patch.object(
            telegram_review.config,
            "TELEGRAM_CHAT_ID",
            "42",
        ), patch.object(
            telegram_review,
            "admit_robot_candidate",
            side_effect=RuntimeError("disk full"),
        ), patch.object(
            telegram_review,
            "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=_status("ROBOT_RUNNING", "PAUSED"),
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with("callback-4", "Робот: ошибка сохранения")
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertIn("Робот: ошибка сохранения", args[2])
        resume_button = kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(resume_button["callback_data"], "robot:cmd:resume")

    def test_status_panel_defaults_when_runtime_state_unavailable(self):
        callback_query = {
            "id": "callback-5",
            "data": "robot:approve:abc123",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 104, "chat": {"id": 42}},
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
        ), patch.object(
            telegram_review,
            "_answer_callback",
        ), patch.object(
            telegram_review,
            "get_robot_runtime_status",
            return_value=None,
        ), patch.object(
            telegram_review.telegram_bot,
            "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        args, kwargs = send_mock.call_args
        self.assertIn("Статус робота: Остановлен", args[2])
        start_button = kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(start_button["callback_data"], "robot:cmd:start")

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
