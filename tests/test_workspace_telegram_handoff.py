"""Telegram editor button on Linux: protected URL only, no fake PC launch."""
import unittest
from unittest.mock import patch

import telegram_review
import workspace_telegram_handoff as handoff


class WorkspaceTelegramHandoffTests(unittest.TestCase):
    def test_editor_link_has_exact_context_without_secret_or_trading_control(self):
        with patch.dict("os.environ", {
            "BYBITSCANNER_TERMINAL_HTTPS_URL": "https://terminal.example.com/",
            "BYBITSCANNER_ACCESS_CLIENT_ID": "access-id",
            "BYBITSCANNER_ACCESS_CLIENT_SECRET": "access-secret",
            "TELEGRAM_CHAT_ID": "42",
        }), patch.object(handoff, "verify_workspace_gateway", return_value=True) as probe, \
                patch.object(handoff.telegram_gateway_client, "configured", return_value=True), \
                patch.object(handoff.telegram_gateway_client, "send_text", return_value={"ok": True}) as send:
            self.assertTrue(handoff.deliver_workspace_link(
                "42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")["ok"])
        probe.assert_called_once()
        args, kw = send.call_args
        self.assertEqual(args[0], "42")
        button = kw["reply_markup"]["inline_keyboard"][0][0]
        self.assertEqual(button["url"], "https://terminal.example.com/?mode=EDITOR&symbol=BTCUSDT&timeframe=5m")
        self.assertNotIn("access-secret", repr(send.call_args))
        self.assertNotIn("robot:", repr(send.call_args))

    def test_unconfigured_or_unverified_ingress_never_sends(self):
        env = {"BYBITSCANNER_TERMINAL_HTTPS_URL": "https://terminal.example.com/",
               "BYBITSCANNER_ACCESS_CLIENT_ID": "id",
               "BYBITSCANNER_ACCESS_CLIENT_SECRET": "secret",
               "TELEGRAM_CHAT_ID": "42"}
        with patch.dict("os.environ", env), \
                patch.object(handoff, "verify_workspace_gateway", return_value=False), \
                patch.object(handoff.telegram_gateway_client, "send_text") as send:
            with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "unverified"):
                handoff.deliver_workspace_link("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
            send.assert_not_called()
        with patch.dict("os.environ", {"TELEGRAM_CHAT_ID": "42"}, clear=True), \
                patch.object(handoff.telegram_gateway_client, "send_text") as send:
            with self.assertRaisesRegex(handoff.WorkspaceHandoffUnavailable, "unconfigured"):
                handoff.deliver_workspace_link("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
            send.assert_not_called()

    def test_wrong_owner_or_unsafe_url_never_delivers(self):
        env = {"BYBITSCANNER_TERMINAL_HTTPS_URL": "http://127.0.0.1:4173/",
               "BYBITSCANNER_ACCESS_CLIENT_ID": "id",
               "BYBITSCANNER_ACCESS_CLIENT_SECRET": "secret",
               "TELEGRAM_CHAT_ID": "42"}
        with patch.dict("os.environ", env), \
                patch.object(handoff, "verify_workspace_gateway") as probe, \
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
        with patch("telegram_review.os.name", "posix", create=True), \
                patch.object(handoff, "deliver_workspace_link", return_value={"ok": True}) as deliver, \
                patch("workspace_owner_launcher.request_owner_workspace_open") as pc, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        deliver.assert_called_once_with("42", mode="EDITOR", symbol="BTCUSDT", timeframe="5m")
        pc.assert_not_called()
        answer.assert_called_once_with("callback-1", "Ссылка на редактор/терминал отправлена в чат")

    def test_linux_callback_denies_unverified_connection(self):
        callback = {"id": "callback-1", "message": {"chat": {"id": 42}}}
        parsed = {"mode": "EDITOR", "symbol": "BTCUSDT", "timeframe": "5m"}
        with patch("telegram_review.os.name", "posix", create=True), \
                patch.object(handoff, "deliver_workspace_link", side_effect=handoff.WorkspaceHandoffUnavailable("missing")), \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._run_workspace_callback(callback, parsed)
        answer.assert_called_once_with("callback-1", "Редактор: защищённое HTTPS-соединение недоступно")


if __name__ == "__main__":
    unittest.main()
