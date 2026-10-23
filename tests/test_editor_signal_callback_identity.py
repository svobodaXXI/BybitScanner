"""Exact identity in owner-only Telegram EDITOR callback."""
import unittest

from notification import build_tradingview_keyboard
from telegram_review import _parse_workspace_callback


class EditorSignalCallbackIdentityTests(unittest.TestCase):
    def test_exact_signal_survives_sender_to_listener(self):
        keyboard = build_tradingview_keyboard(
            "UMAUSDT", "5", robot_candidate_id="candidate-123",
            signal_id="candidate-123")
        callback = keyboard["inline_keyboard"][-1][0]["callback_data"]
        parsed = _parse_workspace_callback(callback)
        self.assertEqual(parsed["signal_id"], "candidate-123")
        self.assertEqual((parsed["symbol"], parsed["timeframe"]), ("UMAUSDT", "5m"))

    def test_legacy_callback_stays_supported(self):
        parsed = _parse_workspace_callback("workspace:EDITOR:ZHIPUUSDT:1m")
        self.assertIsNone(parsed["signal_id"])

    def test_malicious_and_overlong_callbacks_are_rejected(self):
        self.assertIsNone(_parse_workspace_callback("workspace:EDITOR:UMAUSDT:5m:../../secret"))
        self.assertIsNone(_parse_workspace_callback("workspace:TERMINAL:UMAUSDT:5m:candidate"))
        self.assertIsNone(_parse_workspace_callback("workspace:EDITOR:UMAUSDT:5m:" + "a" * 70))

    def test_long_identity_does_not_breach_telegram_callback_limit(self):
        keyboard = build_tradingview_keyboard(
            "UMAUSDT", "5", signal_id="a" * 100)
        callback = keyboard["inline_keyboard"][-1][0]["callback_data"]
        self.assertLessEqual(len(callback.encode("utf-8")), 64)

    def test_compact_callback_preserves_uuid_identity(self):
        candidate = "12345678-1234-1234-1234-123456789abc"
        keyboard = build_tradingview_keyboard("ZHIPUUSDT", "1", signal_id=candidate)
        callback = keyboard["inline_keyboard"][-1][0]["callback_data"]
        self.assertLessEqual(len(callback.encode("utf-8")), 64)
        self.assertEqual(_parse_workspace_callback(callback)["signal_id"], candidate)


if __name__ == "__main__":
    unittest.main()
