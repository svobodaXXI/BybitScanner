"""Telegram Editor handoff through existing authenticated Mini App ingress."""
import sys
from pathlib import Path
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


class ProbeSession:
    """Preserve the existing transport mocks while inspecting session policy."""
    instances = []

    def __init__(self):
        self.trust_env = True
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, *args, **kwargs):
        return handoff.requests.get(*args, **kwargs)


class WorkspaceTelegramHandoffTests(unittest.TestCase):
    def setUp(self):
        ProbeSession.instances.clear()
        session_patch = patch.object(handoff.requests, "Session", side_effect=ProbeSession)
        session_patch.start()
        self.addCleanup(session_patch.stop)

    def test_dead_inherited_proxy_is_ignored_without_disabling_tls(self):
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181",
            "TELEGRAM_CHAT_ID": "42",
            "HTTP_PROXY": "socks5h://127.0.0.1:10809",
            "HTTPS_PROXY": "socks5h://127.0.0.1:10809",
        }, clear=True), patch.object(handoff.requests, "get", side_effect=[
            SimpleNamespace(status_code=200), SimpleNamespace(status_code=401),
        ]) as probe, patch.object(handoff.telegram_gateway_client, "configured", return_value=True), \
                patch.object(handoff.telegram_gateway_client, "send_text", return_value={"ok": True}):
            handoff.deliver_workspace_link("42", mode="EDITOR", symbol="ETHUSDT", timeframe="5m")
        self.assertEqual(len(ProbeSession.instances), 1)
        self.assertIs(ProbeSession.instances[0].trust_env, False)
        self.assertEqual([call.args[0] for call in probe.call_args_list],
                         ["https://83.217.213.181/login", "https://83.217.213.181/"])
        self.assertTrue(all("verify" not in call.kwargs for call in probe.call_args_list))

    def test_linux_import_uses_installed_review_queue_not_windows_path(self):
        self.assertEqual(telegram_review.PROJECT_ROOT, Path(telegram_review.__file__).resolve().parent)
        self.assertEqual(telegram_review.REVIEW_QUEUE, telegram_review.PROJECT_ROOT / "review_queue")
        self.assertEqual(telegram_review.OFFSET_FILE, telegram_review.REVIEW_QUEUE / ".telegram_offset")

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

    def test_editor_login_keeps_exact_signal_id_after_owner_auth(self):
        # The Telegram login page must forward the immutable Scanner identity
        # to App; otherwise App silently loads only current symbol candles.
        from notification import build_tradingview_keyboard
        from workspace_ready_link import workspace_link
        from urllib.parse import parse_qs, urlsplit

        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181/login",
        }, clear=True):
            editor, terminal = build_tradingview_keyboard(
                "BTCUSDT", "5", signal_id="mirror-origin:abc",
            )["inline_keyboard"][-1]
        editor_query = parse_qs(urlsplit(editor["web_app"]["url"]).query)
        self.assertEqual(editor_query["signal_id"], ["mirror-origin:abc"])
        self.assertNotIn("signal_id", urlsplit(terminal["web_app"]["url"]).query)
        self.assertIn('const signalId=params.get("signal_id")', LOGIN_HTML)
        self.assertIn('mode==="EDITOR" && signalId!==null', LOGIN_HTML)
        self.assertIn('target.searchParams.set("signal_id",signalId)', LOGIN_HTML)
        self.assertIn("^[A-Za-z0-9_.:-]{1,128}$", LOGIN_HTML)
        # Reuse the canonical URL builder, never add a credential token.
        self.assertEqual(
            workspace_link("https://83.217.213.181/", "EDITOR",
                           "BTCUSDT", "5m", signal_id="mirror-origin:abc"),
            "https://83.217.213.181/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m&signal_id=mirror-origin%3Aabc",
        )

    def test_signal_callback_reuses_configured_telegram_mini_app_url(self):
        # Production /terminal uses BYBITSCANNER_WORKSPACE_URL; signal cards
        # must not silently require a second environment variable.
        with patch.dict("os.environ", {
            "BYBITSCANNER_WORKSPACE_URL": "https://83.217.213.181/login",
            "TELEGRAM_CHAT_ID": "42",
        }, clear=True), patch.object(handoff.requests, "get", side_effect=[
            SimpleNamespace(status_code=200), SimpleNamespace(status_code=401),
        ]), patch.object(handoff.telegram_gateway_client, "configured", return_value=True), \
                patch.object(handoff.telegram_gateway_client, "send_text", return_value={"ok": True}) as send:
            handoff.deliver_workspace_link("42", mode="EDITOR", symbol="ETHUSDT", timeframe="15m")
        button = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(button["web_app"]["url"],
                         "https://83.217.213.181/login?mode=EDITOR&symbol=ETHUSDT&timeframe=15m")

    def test_malformed_mini_app_base_fails_before_delivery(self):
        for bad in ("http://83.217.213.181/login",
                    "https://83.217.213.181/login?token=secret",
                    "https://83.217.213.181/other",
                    "https://83.217.213.181/login#fragment"):
            with self.subTest(base=bad), patch.dict("os.environ", {
                "BYBITSCANNER_WORKSPACE_URL": bad, "TELEGRAM_CHAT_ID": "42",
            }, clear=True), patch.object(handoff.requests, "get") as probe, \
                    patch.object(handoff.telegram_gateway_client, "send_text") as send:
                with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "invalid_workspace_link"):
                    handoff.deliver_workspace_link("42", mode="EDITOR", symbol="ETHUSDT", timeframe="15m")
                probe.assert_not_called()
                send.assert_not_called()

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


    def test_owner_signal_keyboard_maps_native_intervals_and_preserves_exact_signal(self):
        from notification import build_tradingview_keyboard
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181/login",
            "BYBITSCANNER_WORKSPACE_URL": "",
        }, clear=True):
            for native, expected in (("1", "1m"), ("5", "5m"), ("15", "15m"),
                                     ("60", "1h"), ("D", "1d"), ("15s", "15s")):
                with self.subTest(native=native):
                    editor, terminal = build_tradingview_keyboard(
                        "BTCUSDT", native, signal_id="signal-123",
                    )["inline_keyboard"][-1]
                    self.assertEqual(
                        editor["web_app"]["url"],
                        f"https://83.217.213.181/login?mode=EDITOR&symbol=BTCUSDT&timeframe={expected}&signal_id=signal-123",
                    )
                    self.assertEqual(
                        terminal["web_app"]["url"],
                        f"https://83.217.213.181/login?mode=TERMINAL&symbol=BTCUSDT&timeframe={expected}",
                    )

    def test_owner_keyboard_fallback_and_non_owner_do_not_leak_editor_link(self):
        from notification import build_tradingview_keyboard
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "",
            "BYBITSCANNER_WORKSPACE_URL": "",
        }, clear=True):
            editor, _ = build_tradingview_keyboard(
                "BTCUSDT", "D", signal_id="signal-123",
            )["inline_keyboard"][-1]
            self.assertEqual(editor["callback_data"], "workspace:EDITOR:BTCUSDT:1d")
            self.assertNotIn("web_app", editor)
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181/login",
        }):
            rows = build_tradingview_keyboard(
                "BTCUSDT", "5", include_review_actions=False,
                signal_id="signal-123",
            )["inline_keyboard"]
        self.assertFalse(any("web_app" in button for row in rows for button in row))

    def test_fallback_owner_editor_callback_preserves_original_source_identity(self):
        from notification import build_tradingview_keyboard
        token = "a" * 24
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "", "BYBITSCANNER_WORKSPACE_URL": "",
        }, clear=True):
            editor, terminal = build_tradingview_keyboard(
                "BTCUSDT", "5", signal_id=f"source-original:{token}",
            )["inline_keyboard"][-1]
        self.assertEqual(editor["callback_data"], f"workspace:EDITOR:S:{token}")
        self.assertLessEqual(len(editor["callback_data"].encode("utf-8")), 64)
        self.assertEqual(terminal["callback_data"], "workspace:TERMINAL:BTCUSDT:5m")
        parsed = telegram_review._parse_workspace_callback(editor["callback_data"])
        self.assertEqual(parsed["source_token"], token)
        self.assertIsNone(telegram_review._parse_workspace_callback(
            "workspace:EDITOR:S:" + "!" * 24))
        callback = {"id": "callback-1", "message": {"chat": {"id": 42}}}
        frozen = {"signal_id": f"source-original:{token}", "symbol": "BTCUSDT",
                  "timeframe": "5", "bars": [], "boundaries": []}
        with patch("signal_archive.load_frozen_signal_geometry", return_value=frozen) as load, \
                patch.object(handoff, "deliver_workspace_link", return_value={"ok": True}) as deliver, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        load.assert_called_once_with(f"source-original:{token}")
        deliver.assert_called_once_with(
            "42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m",
            signal_id=f"source-original:{token}",
        )
        answer.assert_called_once_with("callback-1", "Ссылка на редактор/терминал отправлена в чат")

    def test_unavailable_frozen_geometry_blocks_callback_before_handoff(self):
        token = "b" * 24
        parsed = telegram_review._parse_workspace_callback(f"workspace:EDITOR:S:{token}")
        callback = {"id": "callback-2", "message": {"chat": {"id": 42}}}
        with patch("signal_archive.load_frozen_signal_geometry", return_value=None), \
                patch.object(handoff, "deliver_workspace_link") as deliver, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        deliver.assert_not_called()
        answer.assert_called_once_with("callback-2", "Исходная геометрия сигнала недоступна")

    def test_verified_telegram_handoff_url_contains_archived_signal_id(self):
        token = "c" * 24
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://83.217.213.181",
            "TELEGRAM_CHAT_ID": "42",
        }, clear=True), patch.object(handoff.requests, "get", side_effect=[
            SimpleNamespace(status_code=200), SimpleNamespace(status_code=401),
        ]), patch.object(handoff.telegram_gateway_client, "configured", return_value=True), \
                patch.object(handoff.telegram_gateway_client, "send_text", return_value={"ok": True}) as send:
            handoff.deliver_workspace_link(
                "42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m",
                signal_id=f"source-original:{token}",
            )
        from urllib.parse import parse_qs, urlsplit
        url = send.call_args.kwargs["reply_markup"]["inline_keyboard"][0][0]["web_app"]["url"]
        self.assertEqual(parse_qs(urlsplit(url).query)["signal_id"], [f"source-original:{token}"])


if __name__ == "__main__":
    unittest.main()
