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

import telegram_review
from terminal.application.robot_control import RobotControlRejected
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import RobotRuntimeStateRecord


def _owner_callback(callback_id, command):
    return {
        "id": callback_id,
        "data": f"robot:cmd:{command}",
        "from": {"id": 42, "username": "owner"},
        "message": {"message_id": 100, "chat": {"id": 42}},
    }


def _state(mode, recovery_status):
    return RobotRuntimeStateRecord(
        trading_account_id=TradingAccountId("paper"),
        mode=mode,
        recovery_status=recovery_status,
        reason=None,
        version=2,
        updated_at_ms=1000,
    )


class TelegramRobotControlDispatchTests(unittest.TestCase):
    def test_control_callback_parser_is_separate_from_other_parsers(self):
        self.assertIsNone(telegram_review._parse_callback("robot:cmd:pause"))
        self.assertIsNone(telegram_review._parse_robot_callback("robot:cmd:pause"))

    def test_owner_pause_callback_invokes_pause_robot_and_answers_success(self):
        callback_query = _owner_callback("cb-1", "pause")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "pause_robot", return_value=_state("ROBOT_RUNNING", "PAUSED"),
        ) as pause_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "PAUSED"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        pause_mock.assert_called_once_with()
        answer_mock.assert_called_once_with("cb-1", "Робот: на паузе ⏸")
        send_mock.assert_called_once()
        self.assertIn("Робот: на паузе ⏸", send_mock.call_args.args[2])
        self.assertIn("Статус робота: Запущен / Пауза", send_mock.call_args.args[2])

    def test_owner_resume_callback_invokes_resume_robot(self):
        callback_query = _owner_callback("cb-2", "resume")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "resume_robot", return_value=_state("ROBOT_RUNNING", "READY"),
        ) as resume_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        resume_mock.assert_called_once_with()
        answer_mock.assert_called_once_with("cb-2", "Робот: возобновлён ▶")
        send_mock.assert_called_once()
        self.assertIn("Статус робота: Запущен / Готов", send_mock.call_args.args[2])

    def test_owner_start_callback_invokes_start_robot(self):
        callback_query = _owner_callback("cb-3", "start")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "start_robot", return_value=_state("ROBOT_RUNNING", "READY"),
        ) as start_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        start_mock.assert_called_once_with()
        answer_mock.assert_called_once_with("cb-3", "Робот: запущен ▶")
        send_mock.assert_called_once()

    def test_owner_stop_callback_invokes_stop_robot(self):
        callback_query = _owner_callback("cb-4", "stop")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "stop_robot", return_value=_state("ROBOT_STOPPED", "ROBOT_STOPPED"),
        ) as stop_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_STOPPED", "ROBOT_STOPPED"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        stop_mock.assert_called_once_with()
        answer_mock.assert_called_once_with("cb-4", "Робот: остановлен ⏹")
        send_mock.assert_called_once()
        self.assertIn("Статус робота: Остановлен", send_mock.call_args.args[2])

    def test_rejected_command_answers_with_reason_and_does_not_raise(self):
        callback_query = _owner_callback("cb-5", "pause")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review,
            "pause_robot",
            side_effect=RobotControlRejected("pause_robot is legal only from (ROBOT_RUNNING, READY)"),
        ), patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with(
            "cb-5",
            "Робот: отклонено — pause_robot is legal only from (ROBOT_RUNNING, READY)",
        )

    def test_close_all_callback_requests_confirmation_without_executing(self):
        callback_query = _owner_callback("cb-7", "close_all")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "close_all_now",
        ) as close_all_mock, patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        close_all_mock.assert_not_called()
        answer_mock.assert_called_once_with("cb-7", "Подтвердите закрытие всех позиций робота")
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertEqual(args[1], 42)
        self.assertIn("reply_markup", kwargs)
        confirm_button = kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(confirm_button["callback_data"], "robot:cmd:close_all_confirm")

    def test_close_all_confirm_callback_invokes_close_all_now(self):
        callback_query = _owner_callback("cb-8", "close_all_confirm")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "close_all_now", return_value={"ok": True, "results": []},
        ) as close_all_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        close_all_mock.assert_called_once()
        self.assertIs(close_all_mock.call_args.kwargs["http_post"], telegram_review._post_robot_close_all_now)
        answer_mock.assert_called_once_with("cb-8", "Робот: закрытие отправлено ❌")
        send_mock.assert_called_once()
        self.assertIn("Робот: закрытие отправлено ❌", send_mock.call_args.args[2])

    def test_close_all_confirm_rejected_answers_with_reason(self):
        callback_query = _owner_callback("cb-9", "close_all_confirm")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review,
            "close_all_now",
            side_effect=RobotControlRejected("close_all_now is legal only from (ROBOT_RUNNING, READY) or (ROBOT_RUNNING, PAUSED)"),
        ), patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        answer_mock.assert_called_once_with(
            "cb-9",
            "Робот: отклонено — close_all_now is legal only from (ROBOT_RUNNING, READY) or (ROBOT_RUNNING, PAUSED)",
        )

    def test_close_all_cancel_callback_does_not_execute(self):
        callback_query = _owner_callback("cb-10", "close_all_cancel")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "close_all_now",
        ) as close_all_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        close_all_mock.assert_not_called()
        answer_mock.assert_called_once_with("cb-10", "Отменено")
        send_mock.assert_called_once()
        self.assertIn("Отменено", send_mock.call_args.args[2])

    def test_non_owner_control_callback_is_rejected(self):
        callback_query = {
            "id": "cb-6",
            "data": "robot:cmd:stop",
            "from": {"id": 99},
            "message": {"message_id": 101, "chat": {"id": 99}},
        }
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "stop_robot",
        ) as stop_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        stop_mock.assert_not_called()
        answer_mock.assert_called_once_with("cb-6", "Недостаточно прав")


if __name__ == "__main__":
    unittest.main()
