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


def _intent_result(outcome, blocked_by=()):
    from tools.runtime_intent import BootstrapResult

    return BootstrapResult("ROBOT", outcome, outcome, blocked_by=blocked_by)


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

    def test_owner_status_callback_opens_panel_without_mutation(self):
        callback_query = _owner_callback("cb-status", "status")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review.telegram_runtime_intent, "execute",
        ) as intent_mock, patch.object(
            telegram_review, "pause_robot",
        ) as pause_mock, patch.object(
            telegram_review.stop_robot_runtime, "launch_detached",
        ) as stop_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        intent_mock.assert_not_called()
        pause_mock.assert_not_called()
        stop_mock.assert_not_called()
        answer_mock.assert_called_once_with("cb-status", "🤖 Робот")
        send_mock.assert_called_once()
        self.assertIn("Статус робота: Запущен / Готов", send_mock.call_args.args[2])

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

        pause_mock.assert_called_once_with(
            http_post=telegram_review._post_robot_synchronize_pending_entries,
        )
        answer_mock.assert_called_once_with("cb-1", "🤖 Робот: на паузе ⏸")
        send_mock.assert_called_once()
        self.assertIn("🤖 Робот: на паузе ⏸", send_mock.call_args.args[2])
        self.assertIn("Статус робота: Запущен / Пауза", send_mock.call_args.args[2])

    def _run_intent_callback(self, command, result):
        callback_query = _owner_callback(f"cb-{command}", command)
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review.telegram_runtime_intent, "execute", return_value=result,
        ) as intent_mock, patch.object(
            telegram_review, "pause_robot",
        ) as pause_mock, patch.object(
            telegram_review.stop_robot_runtime, "launch_detached",
        ) as stop_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock, patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)
        pause_mock.assert_not_called()
        stop_mock.assert_not_called()
        intent_mock.assert_called_once_with("ROBOT")
        answer_mock.assert_called_once()
        return send_mock

    def test_owner_start_and_resume_callbacks_run_the_robot_runtime_intent(self):
        self.assertFalse(hasattr(telegram_review, "start_robot"))
        self.assertFalse(hasattr(telegram_review, "resume_robot"))
        for command, prefix in (("start", "🤖 Робот: запущен ▶"), ("resume", "🤖 Робот: возобновлён ▶")):
            with self.subTest(command=command):
                send_mock = self._run_intent_callback(command, _intent_result("READY"))
                send_mock.assert_called_once()
                self.assertIn(prefix, send_mock.call_args.args[2])
                self.assertIn("Статус робота: Запущен / Готов", send_mock.call_args.args[2])

    def test_blocked_or_unconfirmed_robot_intent_sends_one_message_without_retry(self):
        for result, text in (
            (_intent_result("BLOCKED", blocked_by=("ROBOT_PROTECTION_UNHEALTHY",)),
             "⛔ Запуск заблокирован: ROBOT_PROTECTION_UNHEALTHY"),
            (_intent_result("ERROR"), "⚠ Запуск не подтверждён."),
            (_intent_result("FAILED"), "⚠ Запуск не подтверждён."),
        ):
            with self.subTest(outcome=result.outcome):
                send_mock = self._run_intent_callback("start", result)
                send_mock.assert_called_once()
                self.assertEqual(send_mock.call_args.args[2], text)

    def test_candidate_approval_stays_on_admission_not_runtime_intent(self):
        callback_query = {
            "id": "cb-approve",
            "data": "robot:approve:cand-1",
            "from": {"id": 42, "username": "owner"},
            "message": {"message_id": 100, "chat": {"id": 42}},
        }
        record = types.SimpleNamespace(candidate_id="cand-1", symbol=types.SimpleNamespace(value="BTCUSDT"))
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review, "admit_robot_candidate", return_value=(record, True),
        ) as admit_mock, patch.object(
            telegram_review.telegram_runtime_intent, "execute",
        ) as intent_mock, patch.object(
            telegram_review, "_answer_callback",
        ), patch.object(
            telegram_review, "get_robot_runtime_status",
            return_value=_state("ROBOT_RUNNING", "READY"),
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ):
            telegram_review._process_callback(callback_query)

        admit_mock.assert_called_once()
        self.assertEqual(admit_mock.call_args.args[0], "cand-1")
        intent_mock.assert_not_called()

    def test_owner_stop_callback_hands_off_to_shared_full_runtime_shutdown(self):
        self.assertFalse(hasattr(telegram_review, "stop_robot"))
        callback_query = _owner_callback("cb-4", "stop")
        order = []
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review.stop_robot_runtime, "launch_detached",
            side_effect=lambda *a, **k: order.append("launch"),
        ) as launch_mock, patch.object(
            telegram_review, "pause_robot",
        ) as pause_mock, patch.object(
            telegram_review.telegram_runtime_intent, "execute",
        ) as intent_mock, patch.object(
            telegram_review, "_answer_callback",
            side_effect=lambda *a, **k: order.append("ack"),
        ) as answer_mock, patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)

        launch_mock.assert_called_once_with("all", notify_chat=42)
        self.assertEqual(order, ["ack", "launch"])
        answer_mock.assert_called_once_with("cb-4", "🤖 Робот: остановка…")
        send_mock.assert_called_once()
        self.assertEqual(
            send_mock.call_args.args[2], "⏹ Останавливаю сканер, робота, Telegram и backend…",
        )
        pause_mock.assert_not_called()
        intent_mock.assert_not_called()

    def test_stop_handoff_failure_is_one_message_without_retry(self):
        callback_query = _owner_callback("cb-4b", "stop")
        with patch.object(
            telegram_review.config, "TELEGRAM_CHAT_ID", "42",
        ), patch.object(
            telegram_review.stop_robot_runtime, "launch_detached", side_effect=OSError("no python"),
        ) as launch_mock, patch.object(
            telegram_review, "_answer_callback",
        ), patch.object(
            telegram_review.telegram_bot, "send_message",
        ) as send_mock:
            telegram_review._process_callback(callback_query)
        launch_mock.assert_called_once()
        send_mock.assert_called_once()
        self.assertEqual(send_mock.call_args.args[2], "⚠ Остановка не запущена.")

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
            "🤖 Робот: отклонено — pause_robot is legal only from (ROBOT_RUNNING, READY)",
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
        answer_mock.assert_called_once_with("cb-8", "🤖 Робот: закрытие отправлено ❌")
        send_mock.assert_called_once()
        self.assertIn("🤖 Робот: закрытие отправлено ❌", send_mock.call_args.args[2])

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
            "🤖 Робот: отклонено — close_all_now is legal only from (ROBOT_RUNNING, READY) or (ROBOT_RUNNING, PAUSED)",
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
            telegram_review.stop_robot_runtime, "launch_detached",
        ) as stop_mock, patch.object(
            telegram_review, "_answer_callback",
        ) as answer_mock:
            telegram_review._process_callback(callback_query)

        stop_mock.assert_not_called()
        answer_mock.assert_called_once_with("cb-6", "Недостаточно прав")


if __name__ == "__main__":
    unittest.main()
