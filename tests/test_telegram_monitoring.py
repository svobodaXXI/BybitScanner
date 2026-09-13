import importlib.util
import json
import os
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch, call

# No private credentials are needed in an isolated checkout.
if "config" not in sys.modules and importlib.util.find_spec("config") is None:
    sys.modules["config"] = ModuleType("config")
import telegram_monitoring as menu


class UnifiedMenuTests(unittest.TestCase):
    def setUp(self):
        menu._published_commands = None
        for key, value in (("TELEGRAM_CHAT_ID", "123"), ("TELEGRAM_TOKEN", "test")):
            fixture = patch.object(menu.config, key, value, create=True)
            fixture.start()
            self.addCleanup(fixture.stop)

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request")
    def test_fresh_authority_selects_action_and_result_is_reread(self, request, send, refresh):
        for mode, action in (("SCANNER_RUNNING", "pause"), ("SCANNER_PAUSED", "resume"),
                             ("SCANNER_STOPPED", "start")):
            request.reset_mock()
            request.side_effect = [{"mode": mode}, {"mode": "SCANNER_PAUSED"},
                                   {"mode": "SCANNER_STOPPED"}]
            menu._send_scanner_control(123)
            self.assertEqual(request.call_args_list, [call(), call(action), call()])
            self.assertEqual(send.call_args.args[1], "Сканер: остановлен")

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request")
    def test_ambiguous_dispatch_is_not_retried(self, request, send, refresh):
        request.side_effect = [{"mode": "SCANNER_STOPPED"}, TimeoutError(),
                               {"mode": "SCANNER_RUNNING"}]
        menu._send_scanner_control(123)
        self.assertEqual(request.call_args_list, [call(), call("start"), call()])
        self.assertEqual(send.call_args.args[1], "Сканер: запущен")

    @patch("telegram_monitoring.refresh_command_menu")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._scanner_request", side_effect=TimeoutError)
    def test_unknown_state_never_dispatches(self, request, send, refresh):
        menu._send_scanner_control(123)
        self.assertTrue(all(not item.args for item in request.call_args_list))

    @patch("telegram_monitoring._telegram_request", return_value={"ok": True})
    @patch("telegram_monitoring._scanner_request")
    def test_menu_tracks_external_state_preserving_monitoring(self, request, telegram):
        for mode, label in (("SCANNER_RUNNING", "Остановить сканер"),
                            ("SCANNER_PAUSED", "Запустить сканер")):
            request.return_value = {"mode": mode}
            menu.refresh_command_menu()
            commands = json.loads(telegram.call_args.kwargs["commands"])
            self.assertEqual([x["command"] for x in commands],
                             ["terminal", "scanner", "robot", "positions", "monitoring"])
            self.assertEqual(commands[1]["description"], label)
            self.assertEqual(commands[-1]["description"], "Мониторинг кандидатов")
        self.assertEqual(telegram.call_count, 2)

    @patch("telegram_monitoring._send_scanner_control")
    @patch("telegram_monitoring._send_candidate_list")
    def test_authorization_and_existing_monitoring(self, monitor, scanner):
        def message(user, chat, text):
            return {"from": {"id": user}, "chat": {"id": chat}, "text": text}
        menu._process_message(message(123, 123, "/monitoring@BybitCleanScannerBot"))
        monitor.assert_called_once_with(123)
        menu._process_message(message(456, 123, "/scanner"))
        menu._process_message(message(123, -100, "/scanner"))
        scanner.assert_not_called()
        menu._process_message(message(123, 123, "/scanner"))
        scanner.assert_called_once_with(123)

    @patch("telegram_monitoring._send_text")
    def test_positions_preserves_workspace_context(self, send):
        from urllib.parse import urlsplit, parse_qs
        with patch.dict(os.environ, {"BYBITSCANNER_WORKSPACE_URL":
                        "https://example.test/workspace?symbol=BTCUSDT&view=old#chart"}):
            menu._send_workspace(123, positions=True)
        url = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"]
        self.assertEqual(parse_qs(urlsplit(url).query),
                         {"symbol": ["BTCUSDT"], "view": ["positions"]})
        self.assertEqual(urlsplit(url).fragment, "chart")

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_robot_uses_authoritative_runtime_and_candidates(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_robot_runtime_state.return_value = SimpleNamespace(
            mode="ROBOT_RUNNING", recovery_status="READY")
        value.load_robot_candidates.return_value = [
            SimpleNamespace(status=x) for x in ("OPEN", "APPROVED", "CLOSED")]
        menu._send_robot_status(123)
        self.assertIn("Запущен / Готов", send.call_args.args[1])
        self.assertIn("Открытых позиций: 1", send.call_args.args[1])

    @patch("telegram_monitoring.requests.get")
    def test_invalid_api_state_fails_closed(self, get):
        get.return_value.json.return_value = {"ok": True, "mode": "UNKNOWN"}
        with self.assertRaises(ValueError):
            menu._scanner_request()

    def test_existing_monitor_callbacks_and_status_labels(self):
        self.assertEqual(menu.parse_monitor_callback("monitor:list"), {"action": "list"})
        self.assertEqual(menu.parse_monitor_callback("monitor:candidate:c1"),
                         {"action": "candidate", "candidate_id": "c1"})
        self.assertIsNone(menu.parse_monitor_callback("robot:approve:c1"))
        self.assertEqual(menu._robot_status_text(None), "Остановлен")

    def test_read_only_status_does_not_create_missing_database(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory) / "missing.sqlite3"
            with patch.object(menu, "DB_PATH", path):
                with self.assertRaises(Exception):
                    menu.get_robot_runtime_status()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
