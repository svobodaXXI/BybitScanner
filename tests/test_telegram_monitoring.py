import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import call, patch

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord
import telegram_monitoring as monitoring


class TelegramMonitoringTests(unittest.TestCase):
    def setUp(self):
        monitoring._published_commands = None
        for key, value in (("TELEGRAM_CHAT_ID", "123"), ("TELEGRAM_TOKEN", "test")):
            fixture = patch.object(monitoring.config, key, value, create=True)
            fixture.start()
            self.addCleanup(fixture.stop)

    def _record(self, *, phase="WAITING_RETEST", execution=None):
        state = {
            "phase": phase,
            "pattern": "Falling Wedge",
            "direction": "LONG",
        }
        if execution is not None:
            state["execution"] = execution
        return RobotCandidateRecord(
            candidate_id="cand-1",
            trading_account_id=TradingAccountId("paper"),
            symbol=Symbol("1000NEIROCTOUSDT"),
            status="APPROVED",
            signal_snapshot={
                "symbol": "1000NEIROCTOUSDT",
                "pattern": "Falling Wedge",
                "quality": "B Setup",
                "potential": {"signed_percent": 0.76},
            },
            snapshot_sha256="abc",
            robot_state=state,
            state_revision=1,
            approved_at_ms=1,
            updated_at_ms=2,
        )

    def test_phase_labels_are_human_readable(self):
        self.assertEqual(monitoring._phase_label(self._record(phase="WAITING_BREAKOUT")), "Ожидание пробоя")
        self.assertEqual(monitoring._phase_label(self._record(phase="WAITING_RETEST")), "Ожидание ретеста")
        self.assertEqual(monitoring._phase_label(self._record(phase="RETEST_DETECTED")), "Ретест обнаружен")

    def test_limit_order_takes_priority_over_retest_label(self):
        record = self._record(
            phase="RETEST_DETECTED",
            execution={"limit_order_id": "paper-limit-1"},
        )
        self.assertEqual(monitoring._phase_label(record), "Лимитный ордер выставлен")

    def test_candidate_keyboard_uses_candidate_id(self):
        keyboard = monitoring.build_candidate_keyboard((self._record(),))
        button = keyboard["inline_keyboard"][0][0]
        self.assertEqual(button["callback_data"], "monitor:candidate:cand-1")
        self.assertIn("1000NEIROCTOUSDT", button["text"])

    def test_parse_monitor_callbacks(self):
        self.assertEqual(monitoring.parse_monitor_callback("monitor:list"), {"action": "list"})
        self.assertEqual(
            monitoring.parse_monitor_callback("monitor:candidate:cand-1"),
            {"action": "candidate", "candidate_id": "cand-1"},
        )
        self.assertIsNone(monitoring.parse_monitor_callback("robot:approve:cand-1"))

    def test_robot_runtime_statuses_are_short_and_localized(self):
        cases = (
            ("ROBOT_RUNNING", "READY", "Запущен / Готов"),
            ("ROBOT_RUNNING", "PAUSED", "Запущен / Пауза"),
            ("ROBOT_RUNNING", "RECONCILING", "Запущен / Сверка"),
            ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED", "Запущен / Нужна сверка"),
            ("ROBOT_STOPPED", "ROBOT_STOPPED", "Остановлен"),
        )
        for mode, recovery_status, expected in cases:
            with self.subTest(mode=mode, recovery_status=recovery_status):
                runtime = SimpleNamespace(mode=mode, recovery_status=recovery_status)
                self.assertEqual(monitoring._robot_status_text(runtime), expected)
        self.assertEqual(monitoring._robot_status_text(None), "Остановлен")

    @patch("telegram_monitoring.get_robot_runtime_status")
    def test_candidate_card_contains_required_monitoring_fields(self, status):
        status.return_value = SimpleNamespace(mode="ROBOT_RUNNING", recovery_status="READY")
        card = monitoring.format_candidate_card(self._record(phase="RETEST_DETECTED"))
        self.assertIn("Тикер: 1000NEIROCTOUSDT", card)
        self.assertIn("Паттерн: Falling Wedge", card)
        self.assertIn("Направление: LONG", card)
        self.assertIn("Состояние: Ретест обнаружен", card)
        self.assertIn("Качество: B Setup", card)
        self.assertIn("Потенциал: +0.76%", card)
        self.assertIn("Робот: Запущен / Готов", card)
        self.assertIn("Сделка: не открыта", card)

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request")
    def test_fresh_authority_selects_action_and_result_is_reread(self, request, send, refresh):
        for mode, action in (
            ("SCANNER_RUNNING", "pause"),
            ("SCANNER_PAUSED", "resume"),
            ("SCANNER_STOPPED", "start"),
        ):
            request.reset_mock()
            request.side_effect = [
                {"mode": mode},
                {"mode": "SCANNER_PAUSED"},
                {"mode": "SCANNER_STOPPED"},
            ]
            monitoring._send_scanner_control(123)
            self.assertEqual(request.call_args_list, [call(), call(action), call()])
            self.assertEqual(send.call_args.args[1], "Сканер: остановлен")

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request")
    def test_ambiguous_dispatch_is_not_retried(self, request, send, refresh):
        request.side_effect = [
            {"mode": "SCANNER_STOPPED"},
            TimeoutError(),
            {"mode": "SCANNER_RUNNING"},
        ]
        monitoring._send_scanner_control(123)
        self.assertEqual(request.call_args_list, [call(), call("start"), call()])
        self.assertEqual(send.call_args.args[1], "Сканер: запущен")

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request", side_effect=TimeoutError)
    def test_unknown_state_never_dispatches(self, request, send, refresh):
        monitoring._send_scanner_control(123)
        self.assertTrue(all(not item.args for item in request.call_args_list))

    @patch("telegram_monitoring._telegram_request", return_value={"ok": True})
    @patch("telegram_monitoring._scanner_request")
    def test_menu_tracks_external_state_preserving_monitoring(self, request, telegram):
        for mode, label in (
            ("SCANNER_RUNNING", "Остановить сканер"),
            ("SCANNER_PAUSED", "Запустить сканер"),
        ):
            request.return_value = {"mode": mode}
            monitoring.refresh_command_menu()
            commands = json.loads(telegram.call_args.kwargs["commands"])
            self.assertEqual(
                [item["command"] for item in commands],
                ["terminal", "scanner", "robot", "positions", "monitoring"],
            )
            self.assertEqual(commands[1]["description"], label)
            self.assertEqual(commands[-1]["description"], "Мониторинг кандидатов")
        self.assertEqual(telegram.call_count, 2)

    @patch("telegram_monitoring._send_scanner_control")
    @patch("telegram_monitoring._send_candidate_list")
    def test_authorization_and_existing_monitoring(self, monitor, scanner):
        def message(user, chat, text):
            return {"from": {"id": user}, "chat": {"id": chat}, "text": text}

        monitoring._process_message(message(123, 123, "/monitoring@BybitCleanScannerBot"))
        monitor.assert_called_once_with(123)
        monitoring._process_message(message(456, 123, "/scanner"))
        monitoring._process_message(message(123, -100, "/scanner"))
        scanner.assert_not_called()
        monitoring._process_message(message(123, 123, "/scanner"))
        scanner.assert_called_once_with(123)

    @patch("telegram_monitoring._send_text")
    def test_positions_preserves_workspace_context(self, send):
        from urllib.parse import parse_qs, urlsplit

        with patch.dict(
            os.environ,
            {
                "BYBITSCANNER_WORKSPACE_URL":
                "https://example.test/workspace?symbol=BTCUSDT&view=old#chart"
            },
        ):
            monitoring._send_workspace(123, positions=True)
        url = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"]
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {"symbol": ["BTCUSDT"], "view": ["positions"]},
        )
        self.assertEqual(urlsplit(url).fragment, "chart")

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_robot_uses_authoritative_runtime_and_candidates(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_robot_runtime_state.return_value = SimpleNamespace(
            mode="ROBOT_RUNNING", recovery_status="READY"
        )
        value.load_robot_candidates.return_value = [
            SimpleNamespace(status=value) for value in ("OPEN", "APPROVED", "CLOSED")
        ]
        monitoring._send_robot_status(123)
        self.assertIn("Запущен / Готов", send.call_args.args[1])
        self.assertIn("Открытых позиций: 1", send.call_args.args[1])
        keyboard = send.call_args.kwargs["reply_markup"]
        self.assertEqual(
            keyboard["inline_keyboard"][0][0]["callback_data"],
            "robot:cmd:pause",
        )
        self.assertEqual(
            keyboard["inline_keyboard"][1][0]["callback_data"],
            "robot:cmd:close_all",
        )
        self.assertEqual(
            keyboard["inline_keyboard"][1][1]["callback_data"],
            "robot:cmd:stop",
        )

    @patch("telegram_monitoring.requests.get")
    def test_invalid_api_state_fails_closed(self, get):
        get.return_value.raise_for_status.return_value = None
        get.return_value.json.return_value = {"ok": True, "mode": "UNKNOWN"}
        with self.assertRaises(ValueError):
            monitoring._scanner_request()


if __name__ == "__main__":
    unittest.main()
