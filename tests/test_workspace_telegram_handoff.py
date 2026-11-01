"""Telegram Editor handoff through existing authenticated Mini App ingress."""
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import patch

config_stub = types.ModuleType("config")
config_stub.TELEGRAM_TOKEN = "test-token"
config_stub.TELEGRAM_CHAT_ID = "42"
config_stub.TELEGRAM_CHAT_IDS = ("42",)
config_stub.TELEGRAM_ENABLED = True
config_stub.TELEGRAM_TEST_MODE = False
config_stub.TIMEFRAME = "1"
sys.modules.setdefault("config", config_stub)

import telegram_review
import workspace_telegram_handoff as handoff
from deploy.terminal_ingress.auth_server import LOGIN_HTML


class WorkspaceTelegramHandoffTests(unittest.TestCase):
    def test_editor_context_via_web_app_not_unprotected_url(self):
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181",
            "TELEGRAM_CHAT_ID": "42",
        }), patch.object(handoff.requests, "get", side_effect=[
            SimpleNamespace(status_code=200), SimpleNamespace(status_code=401),
        ]) as probe, patch.object(handoff.telegram_gateway_client, "configured", return_value=True), \
                patch.object(handoff.telegram_gateway_client, "send_text", return_value={"ok": True}) as send:
            self.assertTrue(handoff.deliver_workspace_link(
                "42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")["ok"])
        self.assertEqual(probe.call_count, 2)
        button = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertNotIn("url", button)
        self.assertEqual(button["web_app"]["url"],
                         "https://83.217.213.181/login?mode=EDITOR&symbol=BTCUSDT&timeframe=5m")
        self.assertIn('target.searchParams.set("mode",mode)', LOGIN_HTML)
        self.assertIn('target.searchParams.set("symbol",symbol)', LOGIN_HTML)
        self.assertIn('target.searchParams.set("timeframe",timeframe)', LOGIN_HTML)
        self.assertNotIn("CF-Access", repr(send.call_args))

    def test_missing_or_open_ingress_fails_closed(self):
        env = {"BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181",
               "TELEGRAM_CHAT_ID": "42"}
        for status in (200, 302, 503):
            with self.subTest(private_status=status), patch.dict("os.environ", env), \
                    patch.object(handoff.requests, "get", side_effect=[
                        SimpleNamespace(status_code=200), SimpleNamespace(status_code=status)
                    ]), patch.object(handoff.telegram_gateway_client, "send_text") as send:
                with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "unverified"):
                    handoff.deliver_workspace_link("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
                send.assert_not_called()
        with patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "42"}, clear=True):
            with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "unconfigured"):
                handoff.deliver_workspace_link("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")

    def test_wrong_owner_or_unsafe_origin_never_delivers(self):
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "http://127.0.0.1:4173/",
            "TELEGRAM_CHAT_ID": "42",
        }), patch.object(handoff.requests, "get") as probe, \
                patch.object(handoff.telegram_gateway_client, "send_text") as send:
            with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "owner_mismatch"):
                handoff.deliver_workspace_link("43", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
            with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "invalid_workspace_link"):
                handoff.deliver_workspace_link("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
            probe.assert_not_called()
            send.assert_not_called()

    def test_linux_callback_returns_truthful_result_and_no_pc_launch(self):
        callback = {"id": "callback-1", "message": {"chat": {"id": 42}}}
        parsed = {"mode": "EDITOR", "symbol": "BTCUSDT", "timeframe": "5m"}
        with patch.object(handoff, "deliver_workspace_link", return_value={"ok": True}) as deliver, \
                patch("workspace_owner_launcher.request_owner_workspace_open") as pc, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        deliver.assert_called_once_with("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
        pc.assert_not_called()
        answer.assert_called_once_with("callback-1", "Ссылка на редактор/терминал отправлена в чат")

    def test_linux_callback_denies_unverified_connection(self):
        callback = {"id": "callback-1", "message": {"chat": {"id": 42}}}
        parsed = {"mode": "EDITOR", "symbol": "BTCUSDT", "timeframe": "5m"}
        with patch.object(handoff, "deliver_workspace_link", side_effect=handoff.WorkspaceHandoffUnavailable("missing")), \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        answer.assert_called_once_with("callback-1", "Редактор: защищённое HTTPS-соединение недоступно")


    def test_signal_cards_use_direct_mini_app_for_supported_timeframes(self):
        from notification import build_tradingview_keyboard
        with patch.dict("os.environ", {
            "BYBITSCANNER_WORKSPACE_URL": "https://83.217.213.181/login",
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "",
        }):
            for raw, chart in (("1", "1m"), ("5", "5m"), ("15", "15m"),
                               ("60", "1h"), ("D", "1d"), ("15s", "15s")):
                with self.subTest(raw=raw):
                    rows = build_tradingview_keyboard("BTCUSDT", raw)["inline_keyboard"]
                    editor, terminal = rows[-1]
                    self.assertEqual(
                        editor["web_app"]["url"],
                        f"https://83.217.213.181/login?mode=EDITOR&symbol=BTCUSDT&timeframe={chart}",
                    )
                    self.assertEqual(
                        terminal["web_app"]["url"],
                        f"https://83.217.213.181/login?mode=TERMINAL&symbol=BTCUSDT&timeframe={chart}",
                    )

    def test_signal_cards_retain_callback_when_https_unconfigured_or_unsafe(self):
        from notification import build_tradingview_keyboard
        for env in (
            {"BYBITSCANNER_WORKSPACE_URL": "", "BYBITSCANNER_TERMINAL_HTTPS_URL": ""},
            {"BYBITSCANNER_WORKSPACE_URL": "http://127.0.0.1:4173/login",
             "BYBITSCANNER_TERMINAL_HTTPS_URL": ""},
            {"BYBITSCANNER_WORKSPACE_URL": "https://83.217.213.181/unprotected",
             "BYBITSCANNER_TERMINAL_HTTPS_URL": ""},
        ):
            with self.subTest(env=env), patch.dict("os.environ", env):
                rows = build_tradingview_keyboard("ETHUSDT", "60")["inline_keyboard"]
                editor, terminal = rows[-1]
                self.assertEqual(editor["callback_data"], "workspace:EDITOR:ETHUSDT:1h")
                self.assertEqual(terminal["callback_data"], "workspace:TERMINAL:ETHUSDT:1h")
                self.assertNotIn("web_app", editor)

    def test_signal_cards_without_owner_never_advertise_mini_app(self):
        from notification import build_tradingview_keyboard
        with patch.dict("os.environ", {
            "BYBITSCANNER_WORKSPACE_URL": "https://83.217.213.181/login",
        }):
            rows = build_tradingview_keyboard(
                "ETHUSDT", "5", include_review_actions=False)["inline_keyboard"]
        self.assertFalse(any(button.get("web_app") for row in rows for button in row))


if __name__ == "__main__":
    unittest.main()
