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


class TelegramGatewayReviewCallbackTransportTests(unittest.TestCase):
    def test_configured_gateway_ack_uses_bot_method_not_direct_socks(self):
        with patch.object(
            telegram_review.telegram_gateway_client, "configured", return_value=True,
        ), patch.object(
            telegram_review.telegram_gateway_client, "bot_method",
            return_value={"ok": True, "result": True},
        ) as gateway, patch.object(
            telegram_review.requests, "get",
        ) as direct:
            accepted = telegram_review._answer_callback("cb-gateway", "PAPER FLAT")
        self.assertTrue(accepted)
        gateway.assert_called_once_with(
            "answerCallbackQuery", callback_query_id="cb-gateway",
            text="PAPER FLAT",
        )
        direct.assert_not_called()

    def test_configured_gateway_ack_never_falls_back_on_error(self):
        from telegram_gateway_client import TelegramGatewayError
        with patch.object(
            telegram_review.telegram_gateway_client, "configured", return_value=True,
        ), patch.object(
            telegram_review.telegram_gateway_client, "bot_method",
            side_effect=TelegramGatewayError("poll unavailable"),
        ), patch.object(
            telegram_review.requests, "get",
        ) as direct:
            accepted = telegram_review._answer_callback("cb-gateway", "PAPER FLAT")
        self.assertFalse(accepted)
        direct.assert_not_called()

    def test_gateway_malformed_ack_is_not_claimed_accepted(self):
        with patch.object(
            telegram_review.telegram_gateway_client, "configured", return_value=True,
        ), patch.object(
            telegram_review.telegram_gateway_client, "bot_method",
            return_value={"ok": False},
        ), patch.object(
            telegram_review.requests, "get",
        ) as direct:
            accepted = telegram_review._answer_callback("cb-gateway", "PAPER FLAT")
        self.assertFalse(accepted)
        direct.assert_not_called()

    def test_no_gateway_keeps_legacy_transport(self):
        with patch.object(
            telegram_review.telegram_gateway_client, "configured", return_value=False,
        ), patch.object(
            telegram_review.requests, "get",
        ) as direct, patch.object(
            telegram_review.telegram_gateway_client, "bot_method",
        ) as gateway:
            direct.return_value.json.return_value = {"ok": True, "result": True}
            accepted = telegram_review._answer_callback("cb-direct", "PAPER FLAT")
        self.assertTrue(accepted)
        direct.assert_called_once()
        gateway.assert_not_called()


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

    @staticmethod
    def _private_paper_callback(callback_id, command):
        callback = _owner_callback(callback_id, command)
        callback["message"]["chat"]["type"] = "private"
        return callback

    def test_owner_paper_close_is_one_tap_with_no_confirmation(self):
        callback = self._private_paper_callback("paper-offer", "paper_close_all")
        action_id = telegram_review._paper_close_all_callback_action_id(callback)
        response = {
            "ok": True, "client_action_id": action_id,
            "results": [{"status": "completed"}], "positions": [],
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all", return_value=response) as post, \
             patch.object(telegram_review.telegram_bot, "send_message") as send, \
             patch.object(telegram_review, "_send_robot_status_panel") as panel, \
             patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(callback)
        post.assert_called_once_with({"client_action_id": action_id})
        self.assertIn("PAPER FLAT", answer.call_args.args[1])
        panel.assert_called_once()

    def test_reconciliation_required_panel_still_offers_operator_close(self):
        from robot_telegram_feed import build_robot_control_keyboard
        panel = build_robot_control_keyboard("ROBOT_RUNNING", "RECONCILIATION_REQUIRED")
        self.assertEqual(panel["inline_keyboard"][0][0]["callback_data"],
                         "robot:cmd:paper_close_all")
        self.assertEqual(len(panel["inline_keyboard"]), 1)

    def test_paper_confirm_success_uses_single_route_scoped_action(self):
        callback = self._private_paper_callback("paper-confirm", "paper_close_all_confirm")
        action_id = telegram_review._paper_close_all_callback_action_id(callback)
        self.assertNotEqual(action_id, telegram_review._robot_close_all_callback_action_id(callback))
        result = {
            "ok": True, "client_action_id": action_id,
            "results": [{"status": "completed"}], "positions": [],
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all", return_value=result) as post, \
             patch.object(telegram_review, "close_all_now") as robot_only, \
             patch.object(telegram_review, "_send_robot_status_panel") as panel, \
             patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(callback)
        post.assert_called_once_with({"client_action_id": action_id})
        robot_only.assert_not_called()
        self.assertIn("PAPER FLAT", answer.call_args.args[1])
        panel.assert_called_once()

    def test_economics_report_contains_verified_gross_fees_and_net(self):
        callback = self._private_paper_callback("economic-cb", "paper_close_all_confirm")
        action_id = telegram_review._paper_close_all_callback_action_id(callback)
        result = {
            "ok": True, "client_action_id": action_id, "results": [], "positions": [],
            "symbol_reports": [
                {"symbol": "BTCUSDT", "owner": "ROBOT", "evidence_status": "VERIFIED",
                 "entry_price": "10", "exit_price": "12", "quantity": "2",
                 "gross_pnl_usdt": "4", "fees_costs_usdt": "0.05", "net_pnl_usdt": "3.95"},
                {"symbol": "ETHUSDT", "owner": "MANUAL", "evidence_status": "UNPROVEN",
                 "net_pnl_usdt": None, "reason": "entry_basis_unknown"},
            ],
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all", return_value=result), \
             patch.object(telegram_review, "_send_robot_status_panel"), \
             patch.object(telegram_review.telegram_bot, "send_message") as send, \
             patch.object(telegram_review, "_answer_callback"):
            telegram_review._process_callback(callback)
        send.assert_called_once()
        message = send.call_args.args[2]
        self.assertIn("BTCUSDT (ROBOT)", message)
        self.assertIn("вход 10; выход 12", message)
        self.assertIn("Net 3.95 USDT", message)
        self.assertIn("ETHUSDT (MANUAL): Net PnL не подтверждён", message)
        self.assertNotIn("Net None", message)

    def test_multiple_symbols_are_paginated_without_fabricating_net(self):
        result = {"symbol_reports": [
            {"symbol": f"PAIR{i}", "owner": "MANUAL", "evidence_status": "UNPROVEN",
             "reason": "missing_fees"} for i in range(21)
        ]}
        messages = telegram_review._paper_close_all_report_messages(result)
        self.assertEqual(len(messages), 3)
        self.assertIn("PAIR0", messages[0])
        self.assertIn("PAIR10", messages[1])
        self.assertIn("PAIR20", messages[2])
        self.assertIn("не подтверждён", messages[2])

    def test_paper_confirm_replay_is_stable_but_new_tap_gets_new_id(self):
        a = self._private_paper_callback("same-tap", "paper_close_all_confirm")
        b = self._private_paper_callback("different-tap", "paper_close_all_confirm")
        self.assertEqual(telegram_review._paper_close_all_callback_action_id(a),
                         telegram_review._paper_close_all_callback_action_id(dict(a)))
        self.assertNotEqual(telegram_review._paper_close_all_callback_action_id(a),
                            telegram_review._paper_close_all_callback_action_id(b))

    def test_paper_cancel_is_noop_without_robot_side_effects(self):
        callback = self._private_paper_callback("paper-cancel", "paper_close_all_cancel")
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all") as post, \
             patch.object(telegram_review, "close_all_now") as robot, \
             patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(callback)
        post.assert_not_called()
        robot.assert_not_called()
        answer.assert_called_once_with("paper-cancel", "Закрытие PAPER отменено")

    def test_group_or_forwarded_paper_confirmation_is_refused(self):
        for chat in ({"id": -1001234, "type": "supergroup"}, {"id": 42, "type": "group"},
                     {"id": -1001234, "type": "private"}, {"id": 42}):
            with self.subTest(chat=chat):
                callback = self._private_paper_callback("paper-group", "paper_close_all_confirm")
                callback["message"]["chat"] = chat
                with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
                     patch.object(telegram_review, "_post_paper_close_all") as post, \
                     patch.object(telegram_review, "_answer_callback") as answer:
                    telegram_review._process_callback(callback)
                post.assert_not_called()
                self.assertIn("личном чате", answer.call_args.args[1])

    def test_non_owner_paper_confirmation_never_posts(self):
        callback = self._private_paper_callback("paper-other", "paper_close_all_confirm")
        callback["from"]["id"] = 99
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all") as post, \
             patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(callback)
        post.assert_not_called()
        answer.assert_called_once_with("paper-other", "Недостаточно прав")

    def test_paper_success_requires_verified_flat_result(self):
        callback = self._private_paper_callback("paper-incomplete", "paper_close_all_confirm")
        action_id = telegram_review._paper_close_all_callback_action_id(callback)
        cases = (
            {"ok": True, "client_action_id": action_id, "results": [], "positions": [{"symbol": "BTCUSDT"}]},
            {"ok": True, "client_action_id": action_id, "results": [{"status": "unknown"}], "positions": []},
            {"ok": True, "client_action_id": "wrong", "results": [], "positions": []},
            {"ok": True, "client_action_id": action_id, "results": [], "positions": None},
            {"ok": True, "client_action_id": action_id, "results": [], "positions": [] , "something": 0},
            {"ok": True, "client_action_id": action_id, "results": ["bad"], "positions": []},
        )
        for i, body in enumerate(cases):
            if i == 4:
                continue  # Other optional backend fields are permitted.
            with self.subTest(i=i), \
                 patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
                 patch.object(telegram_review, "_post_paper_close_all", return_value=body) as post, \
                 patch.object(telegram_review, "_send_robot_status_panel") as panel, \
                 patch.object(telegram_review, "_answer_callback") as answer:
                telegram_review._process_callback(callback)
                post.assert_called_once()
                panel.assert_not_called()
                self.assertIn("не подтверждено", answer.call_args.args[1])

    def test_paper_confirm_missing_callback_id_fails_closed(self):
        callback = self._private_paper_callback("paper-no-id", "paper_close_all_confirm")
        callback.pop("id")
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
             patch.object(telegram_review, "_post_paper_close_all") as post, \
             patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(callback)
        post.assert_not_called()
        self.assertIn("не подтверждено", answer.call_args.args[1])

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
