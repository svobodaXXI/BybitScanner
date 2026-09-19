import json
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import call, patch

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord
# Runtime config.py is local and may contain secrets; unit tests own this
# import dependency and restore the module registry immediately afterward.
_previous_config = sys.modules.get("config")
sys.modules["config"] = ModuleType("config")
try:
    import telegram_monitoring as monitoring
finally:
    if _previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous_config


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
            self.assertEqual(send.call_args.args[1], "📡 Сканер: остановлен")

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
        self.assertEqual(send.call_args.args[1], "📡 Сканер: запущен")

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
    def test_paper_positions_empty_is_explicit(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_paper_account.return_value = SimpleNamespace()
        value.load_open_position_projections.return_value = ()
        value.load_unfinished_commands.return_value = ()
        value.load_reconciliation_checkpoints.return_value = ()

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BYBITSCANNER_WORKSPACE_URL", None)
            monitoring._send_paper_positions(123)

        self.assertEqual(send.call_count, 1)
        self.assertIn(
            "\u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0445 \u043f\u043e\u0437\u0438\u0446\u0438\u0439 \u043d\u0435\u0442",
            send.call_args.args[1],
        )
        self.assertIsNone(send.call_args.kwargs["reply_markup"])

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_paper_positions_empty_with_unfinished_work_is_uncertain(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_paper_account.return_value = SimpleNamespace()
        value.load_open_position_projections.return_value = ()
        value.load_unfinished_commands.return_value = (
            SimpleNamespace(trading_account_id=monitoring.PAPER_ACCOUNT_ID),
        )
        value.load_reconciliation_checkpoints.return_value = ()

        monitoring._send_paper_positions(123)

        self.assertEqual(send.call_count, 1)
        message = send.call_args.args[1]
        self.assertIn(
            "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e",
            message,
        )
        self.assertIn(
            "\u041e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u0438\u0435 \u044d\u043a\u0441\u043f\u043e\u0437\u0438\u0446\u0438\u0438 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e",
            message,
        )

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_paper_positions_reconciliation_in_progress_is_uncertain(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_paper_account.return_value = SimpleNamespace()
        value.load_open_position_projections.return_value = ()
        value.load_unfinished_commands.return_value = ()
        value.load_reconciliation_checkpoints.return_value = (
            SimpleNamespace(
                position_key=SimpleNamespace(
                    trading_account_id=monitoring.PAPER_ACCOUNT_ID,
                ),
                completed_at_ms=None,
            ),
        )

        monitoring._send_paper_positions(123)

        self.assertIn(
            "\u0421\u043e\u0441\u0442\u043e\u044f\u043d\u0438\u0435 \u043d\u0435 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043e",
            send.call_args.args[1],
        )

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_paper_positions_database_failure_never_claims_zero(self, store, send):
        store.side_effect = RuntimeError("database unavailable")

        monitoring._send_paper_positions(123)

        self.assertEqual(send.call_count, 1)
        self.assertEqual(
            send.call_args.args[1],
            "\u0414\u0430\u043d\u043d\u044b\u0435 \u043f\u043e\u0437\u0438\u0446\u0438\u0439 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b.",
        )

    @patch("telegram_monitoring.format_paper_positions_view")
    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_paper_positions_valid_workspace_url_adds_terminal_button(
        self, store, send, formatter
    ):
        value = store.return_value.__enter__.return_value
        value.get_paper_account.return_value = SimpleNamespace()
        value.load_open_position_projections.return_value = (self._position(),)
        value.load_unfinished_commands.return_value = ()
        value.load_reconciliation_checkpoints.return_value = ()
        formatter.return_value = ("positions",)

        with patch.dict(
            os.environ,
            {
                "BYBITSCANNER_WORKSPACE_URL":
                "https://example.test/workspace?symbol=BTCUSDT&view=old#chart"
            },
        ):
            monitoring._send_paper_positions(123)

        markup = send.call_args.kwargs["reply_markup"]
        url = markup["inline_keyboard"][-1][0]["web_app"]["url"]

        from urllib.parse import parse_qs, urlsplit
        self.assertEqual(
            parse_qs(urlsplit(url).query),
            {"symbol": ["BTCUSDT"], "view": ["positions"]},
        )
        self.assertEqual(urlsplit(url).fragment, "chart")

    @staticmethod
    def _position(symbol="CELOUSDT", side="Long"):
        return SimpleNamespace(
            position_key=SimpleNamespace(symbol=Symbol(symbol)),
            side=SimpleNamespace(value=side),
        )

    @patch("telegram_monitoring._send_text")
    @patch("telegram_monitoring._robot_store")
    def test_paper_positions_adds_one_card_button_per_position(self, store, send):
        value = store.return_value.__enter__.return_value
        value.get_paper_account.return_value = SimpleNamespace()
        value.load_open_position_projections.return_value = (
            self._position("CELOUSDT", "Long"), self._position("RIOTUSDT", "Short"),
        )
        value.load_unfinished_commands.return_value = (
            SimpleNamespace(trading_account_id=monitoring.PAPER_ACCOUNT_ID),
        )
        value.load_reconciliation_checkpoints.return_value = ()

        with patch("telegram_monitoring.format_paper_positions_view", return_value=("list",)), \
                patch.dict(os.environ, {"BYBITSCANNER_WORKSPACE_URL": ""}):
            monitoring._send_paper_positions(123)

        # List text and the warning stay unchanged; the keyboard sits under the last message.
        self.assertEqual([c.args[1] for c in send.call_args_list][0], "list")
        self.assertIsNone(send.call_args_list[0].kwargs["reply_markup"])
        self.assertIn("⚠", send.call_args.args[1])
        self.assertEqual(
            send.call_args.kwargs["reply_markup"],
            {"inline_keyboard": [
                [{"text": "1. CELOUSDT · Long", "callback_data": "pos:card:CELOUSDT"}],
                [{"text": "2. RIOTUSDT · Short", "callback_data": "pos:card:RIOTUSDT"}],
            ]},
        )

    @patch("telegram_monitoring._send_position_card")
    @patch("telegram_monitoring._answer_callback")
    def test_position_card_callback_routes_to_card(self, answer, card):
        callback = {
            "id": "callback-3",
            "from": {"id": 123},
            "message": {"chat": {"id": 123}},
            "data": "pos:card:CELOUSDT",
        }

        self.assertTrue(monitoring._process_positions_callback(callback))
        answer.assert_called_once_with("callback-3")
        card.assert_called_once_with(123, "CELOUSDT")

    @patch("telegram_monitoring._send_position_card")
    @patch("telegram_monitoring._answer_callback")
    def test_position_card_callback_rejects_non_owner(self, answer, card):
        callback = {
            "id": "callback-4",
            "from": {"id": 456},
            "message": {"chat": {"id": 123}},
            "data": "pos:card:CELOUSDT",
        }

        self.assertTrue(monitoring._process_positions_callback(callback))
        card.assert_not_called()

    def test_unrelated_callback_is_not_consumed(self):
        self.assertFalse(monitoring._process_positions_callback({"data": "monitor:list"}))
        self.assertFalse(monitoring._process_positions_callback({"data": "pos:card:"}))

    def _card_patches(self, view, *, candles=None):
        fake_api = ModuleType("bybit_api")
        self.candle_requests = []
        fake_api.get_candles = (
            lambda symbol, interval, limit: self.candle_requests.append((symbol, interval, limit))
            or candles
        )
        for fixture in (
            patch("telegram_monitoring._robot_store"),
            patch("telegram_monitoring.load_position_view", return_value=view),
            patch.dict(sys.modules, {"bybit_api": fake_api}),
        ):
            fixture.start()
            self.addCleanup(fixture.stop)

    def _robot_view(self):
        from decimal import Decimal
        from robot_position_view import PositionView

        return PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=True, quantity=Decimal("1"),
            average_entry=Decimal("1"), stop_price=None, take_price=None,
            pattern="Falling Wedge", trade=SimpleNamespace(entry_time_ms=1_000),
        )

    @patch("telegram_monitoring.render_position_chart")
    @patch("telegram_monitoring.telegram_bot.send_photo", return_value={"ok": True})
    @patch("telegram_monitoring._send_text")
    def test_manual_position_card_is_text_only(self, send, photo, render):
        from dataclasses import replace

        self._card_patches(replace(self._robot_view(), trade=None))

        monitoring._send_position_card(123, "CELOUSDT")

        render.assert_not_called()
        photo.assert_not_called()
        self.assertIn("Позиция не от робота — график недоступен", send.call_args.args[1])
        self.assertEqual(
            send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["callback_data"],
            "robot:view:positions",
        )

    @patch("telegram_monitoring.render_position_chart", return_value="chart.png")
    @patch("telegram_monitoring.telegram_bot.send_photo", return_value={"ok": True})
    @patch("telegram_monitoring._send_text")
    def test_robot_position_card_is_photo_with_back_button(self, send, photo, render):
        import pandas as pd

        self._card_patches(self._robot_view(), candles=pd.DataFrame({"close": [1.0, 1.1]}))

        monitoring._send_position_card(123, "SAGAUSDT")

        send.assert_not_called()
        caption = photo.call_args.kwargs["caption"]
        self.assertIn("PnL: ≈ +0.10 USDT (+10.00%)", caption)
        self.assertEqual(photo.call_args.kwargs["reply_markup"], monitoring.POSITIONS_BACK_MARKUP)

    def test_candle_window_follows_entry_age(self):
        import pandas as pd
        from dataclasses import replace

        candles = pd.DataFrame({"close": [1.0, 1.1]})
        now_ms = 1_789_760_700_000
        for timeframe, minutes, limit, note in (
            (5, 30, 120, False), (5, 12 * 60, 168, False), (5, 90 * 60, 1000, True),
            (1, 30, 300, False), (1, 6 * 60, 384, False), (1, 17 * 60, 1000, True),
        ):
            with self.subTest(timeframe=timeframe, minutes=minutes):
                view = replace(
                    self._robot_view(),
                    trade=SimpleNamespace(entry_time_ms=now_ms - minutes * 60_000),
                    chart_candle_minutes=timeframe,
                )
                self._card_patches(view, candles=candles)
                view, _ = monitoring._with_candles(view, now_ms=now_ms)
                self.assertEqual(self.candle_requests, [("SAGAUSDT", str(timeframe), limit)])
                self.assertEqual(
                    "Вход раньше окна графика" in monitoring.format_position_card(view), note,
                )

    @patch("telegram_monitoring.render_position_chart", side_effect=RuntimeError("no candles"))
    @patch("telegram_monitoring.telegram_bot.send_photo")
    @patch("telegram_monitoring._send_text")
    def test_chart_failure_falls_back_to_text(self, send, photo, render):
        self._card_patches(self._robot_view(), candles=None)

        monitoring._send_position_card(123, "SAGAUSDT")

        photo.assert_not_called()
        self.assertTrue(send.call_args.args[1].endswith("\nГрафик недоступен"))

    @patch("telegram_monitoring.render_position_chart", return_value="chart.png")
    @patch("telegram_monitoring.telegram_bot.send_photo", return_value={"ok": False})
    @patch("telegram_monitoring._send_text")
    def test_send_photo_failure_falls_back_to_text(self, send, photo, render):
        self._card_patches(self._robot_view())

        monitoring._send_position_card(123, "SAGAUSDT")

        self.assertIn("SAGAUSDT · LONG", send.call_args.args[1])
        self.assertNotIn("График недоступен", send.call_args.args[1])

    @patch("telegram_monitoring._send_text")
    def test_closed_position_card_reports_no_position(self, send):
        self._card_patches(None)

        monitoring._send_position_card(123, "CELOUSDT")

        self.assertIn("открытой позиции нет", send.call_args.args[1])

    @patch("telegram_monitoring._send_paper_positions")
    def test_positions_command_uses_paper_positions_handler(self, positions):
        message = {
            "from": {"id": 123},
            "chat": {"id": 123},
            "text": "/positions",
        }

        self.assertTrue(monitoring._process_message(message))
        positions.assert_called_once_with(123)

    @patch("telegram_monitoring._send_paper_positions")
    @patch("telegram_monitoring._answer_callback")
    def test_positions_callback_uses_same_handler(self, answer, positions):
        callback = {
            "id": "callback-1",
            "from": {"id": 123},
            "message": {"chat": {"id": 123}},
            "data": "robot:view:positions",
        }

        self.assertTrue(monitoring._process_positions_callback(callback))
        answer.assert_called_once_with("callback-1")
        positions.assert_called_once_with(123)

    @patch("telegram_monitoring._send_paper_positions")
    @patch("telegram_monitoring._answer_callback")
    def test_positions_callback_rejects_non_owner(self, answer, positions):
        callback = {
            "id": "callback-2",
            "from": {"id": 456},
            "message": {"chat": {"id": 123}},
            "data": "robot:view:positions",
        }

        self.assertTrue(monitoring._process_positions_callback(callback))
        positions.assert_not_called()
        answer.assert_called_once_with(
            "callback-2",
            "\u041d\u0435\u0434\u043e\u0441\u0442\u0430\u0442\u043e\u0447\u043d\u043e \u043f\u0440\u0430\u0432",
        )


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


class RobotLifecyclePollTests(unittest.TestCase):
    INIT_MS = 1_000_000

    def setUp(self):
        import tempfile
        from pathlib import Path

        for key, value in (("TELEGRAM_CHAT_ID", "123"), ("TELEGRAM_TOKEN", "test")):
            fixture = patch.object(monitoring.config, key, value, create=True)
            fixture.start()
            self.addCleanup(fixture.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state_file = Path(temp.name) / ".robot_lifecycle_notified"
        self.trades = []
        store = patch("telegram_monitoring._robot_store")
        self.store = store.start().return_value.__enter__.return_value
        self.addCleanup(store.stop)
        self.store.load_robot_trades_with_events_since.side_effect = lambda account, since: self.trades
        for fixture in (
            patch.object(monitoring, "LIFECYCLE_STATE_FILE", self.state_file),
            patch("telegram_monitoring.load_position_view",
                  side_effect=lambda store, symbol, trade_id: SimpleNamespace(trade_id=trade_id)),
        ):
            fixture.start()
            self.addCleanup(fixture.stop)

    def _trade(self, trade_id, entry_ms, exit_ms=None):
        return SimpleNamespace(
            trade_id=trade_id, symbol=Symbol("SAGAUSDT"), entry_time_ms=entry_ms,
            exit_time_ms=exit_ms, exit_reason="STOP" if exit_ms else None,
        )

    def _state(self):
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _poll(self, results=None, now_ms=None):
        sent = []

        def send(chat_id, event, view):
            sent.append((event.kind, event.trade_id))
            return True if results is None else results.pop(0)

        with patch("telegram_monitoring._send_lifecycle_post", side_effect=send):
            monitoring.poll_lifecycle_once(now_ms=now_ms or self.INIT_MS)
        return sent

    def test_first_run_does_not_backfill_history(self):
        self.trades = [self._trade("old", self.INIT_MS - 100, self.INIT_MS - 10)]
        self.assertEqual(self._poll(now_ms=self.INIT_MS), [])
        self.assertEqual(self._state(), {"initialized_at_ms": self.INIT_MS, "opened": [], "closed": []})

    def test_open_then_close_are_sent_once_across_restart(self):
        self._poll()  # initializes the dedup file
        self.trades = [self._trade("t1", self.INIT_MS + 1, self.INIT_MS + 2)]

        self.assertEqual(self._poll(), [("OPENED", "t1"), ("CLOSED", "t1")])
        self.assertEqual(self._state()["opened"], ["t1"])
        self.assertEqual(self._state()["closed"], ["t1"])
        # Restart: state is re-read from the file on every poll; nothing is re-sent.
        self.assertEqual(self._poll(now_ms=self.INIT_MS + 10**9), [])

    def test_failed_open_is_retried_and_close_waits_for_it(self):
        self._poll()
        self.trades = [self._trade("t1", self.INIT_MS + 1, self.INIT_MS + 2)]

        self.assertEqual(self._poll(results=[False]), [("OPENED", "t1")])
        self.assertEqual((self._state()["opened"], self._state()["closed"]), ([], []))
        self.assertEqual(self._poll(results=[True, True]), [("OPENED", "t1"), ("CLOSED", "t1")])

    def test_failed_close_is_retried_without_resending_open(self):
        self._poll()
        self.trades = [self._trade("t1", self.INIT_MS + 1, self.INIT_MS + 2)]

        self._poll(results=[True, False])
        self.assertEqual((self._state()["opened"], self._state()["closed"]), (["t1"], []))
        self.assertEqual(self._poll(), [("CLOSED", "t1")])

    def test_send_exception_is_logged_not_raised(self):
        self._poll()
        self.trades = [self._trade("t1", self.INIT_MS + 1)]
        with patch("telegram_monitoring._send_lifecycle_post", side_effect=RuntimeError("net")):
            monitoring.poll_lifecycle_once(now_ms=self.INIT_MS)
        self.assertEqual(self._state()["opened"], [])

    def test_loop_survives_poll_errors(self):
        class StopLoop(BaseException):
            pass

        with patch("telegram_monitoring.poll_lifecycle_once",
                   side_effect=[RuntimeError("db"), None]) as poll, \
                patch("telegram_monitoring.time.sleep", side_effect=[None, StopLoop()]):
            with self.assertRaises(StopLoop):
                monitoring._lifecycle_loop()
        self.assertEqual(poll.call_count, 2)


class RobotLifecyclePostDeliveryTests(unittest.TestCase):
    def setUp(self):
        for key, value in (("TELEGRAM_CHAT_ID", "123"), ("TELEGRAM_TOKEN", "test")):
            fixture = patch.object(monitoring.config, key, value, create=True)
            fixture.start()
            self.addCleanup(fixture.stop)
        fake_api = ModuleType("bybit_api")
        fake_api.get_candles = lambda symbol, interval, limit: None
        fixture = patch.dict(sys.modules, {"bybit_api": fake_api})
        fixture.start()
        self.addCleanup(fixture.stop)

    def _event_and_view(self):
        from decimal import Decimal
        from robot_lifecycle_posts import EVENT_CLOSED, LifecycleEvent
        from robot_position_view import PositionView

        trade = SimpleNamespace(
            exit_price=Decimal("0.0249"), exit_reason="TAKE", realized_pnl_usdt=Decimal("3"),
            realized_pnl_pct=Decimal("1.1"), fees_costs_usdt=Decimal("0.1"),
            entry_time_ms=1, exit_time_ms=2, entry_quantity=Decimal("1"), average_entry=Decimal("1"),
        )
        view = PositionView(
            symbol="SAGAUSDT", direction="LONG", is_open=False, quantity=Decimal("1"),
            average_entry=Decimal("1"), stop_price=None, take_price=None,
            pattern="Falling Wedge", trade=trade,
        )
        return LifecycleEvent(EVENT_CLOSED, "t1", "SAGAUSDT", 2, "TAKE"), view

    @patch("telegram_monitoring.render_position_chart", return_value="chart.png")
    @patch("telegram_monitoring.telegram_bot.send_photo", return_value={"ok": True})
    def test_closed_post_is_photo_with_all_positions_keyboard(self, photo, render):
        event, view = self._event_and_view()

        self.assertTrue(monitoring._send_lifecycle_post(123, event, view))

        caption = photo.call_args.kwargs["caption"]
        self.assertTrue(caption.startswith("🤖 Сделка закрыта · по тейку"))
        # Only the button with a working handler.
        self.assertEqual(
            photo.call_args.kwargs["reply_markup"],
            {"inline_keyboard": [[{"text": "Все позиции", "callback_data": "robot:view:positions"}]]},
        )

    @patch("telegram_monitoring.render_position_chart", return_value="chart.png")
    @patch("telegram_monitoring.telegram_bot.send_photo", return_value={"ok": False})
    @patch("telegram_monitoring._send_text", return_value={"ok": True})
    def test_photo_failure_falls_back_to_text(self, send, photo, render):
        event, view = self._event_and_view()

        self.assertTrue(monitoring._send_lifecycle_post(123, event, view))
        self.assertTrue(send.call_args.args[1].startswith("🤖 Сделка закрыта · по тейку"))

    @patch("telegram_monitoring.render_position_chart", side_effect=RuntimeError("render"))
    @patch("telegram_monitoring._send_text", return_value={"ok": False})
    def test_undelivered_text_reports_failure(self, send, render):
        event, view = self._event_and_view()

        self.assertFalse(monitoring._send_lifecycle_post(123, event, view))
        self.assertTrue(send.call_args.args[1].endswith("\nГрафик недоступен"))


if __name__ == "__main__":
    unittest.main()
