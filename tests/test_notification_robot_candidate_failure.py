import sys
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

# config.py is local and may contain secrets; stub it only for this import and
# restore the module registry immediately afterward.
_previous_config = sys.modules.get("config")
_config_stub = types.ModuleType("config")
_config_stub.TELEGRAM_TOKEN = "test-token"
_config_stub.TELEGRAM_CHAT_ID = "owner"
_config_stub.TELEGRAM_CHAT_IDS = ("owner",)
_config_stub.TELEGRAM_ENABLED = True
_config_stub.TELEGRAM_TEST_MODE = False
_config_stub.TIMEFRAME = "5"
sys.modules["config"] = _config_stub
try:
    import notification
finally:
    if _previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous_config

WARNING = "⚠️ Робот: кандидат BTC 1м не создан. Сигнал доставлен без Robot-кнопки."


def _signal():
    return {
        "symbol": "BTCUSDT",
        "pattern": "Falling Wedge",
        "final_score": 80,
        "timeframe": "1",
        "robot_handoff_ready": True,
        "confirmation": {"direction": "LONG", "confirmed": True},
    }


def _buttons(photo_call):
    keyboard = photo_call.kwargs["reply_markup"]["inline_keyboard"]
    return [button["text"] for row in keyboard for button in row]


class RobotCandidateFailureWarningTests(unittest.TestCase):
    def _send(self, *, recipients=("owner",), candidate=None, candidate_error=None,
              message_side_effect=None):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            (Path(directory) / "BTCUSDT_1_analysis.png").write_bytes(b"1m chart")
            stack.enter_context(patch.object(notification.config, "TELEGRAM_CHAT_IDS", recipients))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_CHAT_ID", "owner"))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_TOKEN", "test-token"))
            stack.enter_context(patch.object(notification.config, "TELEGRAM_ENABLED", True))
            stack.enter_context(patch.object(notification, "CHARTS_DIR", directory))
            messages = stack.enter_context(patch.object(
                notification, "send_message",
                side_effect=message_side_effect or (lambda *a, **k: {"ok": True}),
            ))
            photos = stack.enter_context(patch.object(
                notification, "send_photo", return_value={"ok": True}))
            create = stack.enter_context(patch.object(
                notification, "create_signal_snapshot",
                return_value=candidate, side_effect=candidate_error,
            ))
            delivered = notification.send_signal(_signal())
        return delivered, messages, photos, create

    @staticmethod
    def _warnings(messages):
        return [call for call in messages.call_args_list if call.args[2] == WARNING]

    def test_persistence_success_sends_no_warning_and_keeps_robot_button(self):
        delivered, messages, photos, create = self._send(
            candidate={"candidate_id": "candidate-1"})
        self.assertTrue(delivered)
        create.assert_called_once()
        self.assertEqual(self._warnings(messages), [])
        self.assertIn("🤖 Робот", _buttons(photos.call_args))

    def test_persistence_failure_warns_owner_once_without_robot_button(self):
        delivered, messages, photos, _create = self._send(
            candidate_error=RuntimeError("database is locked at C:/secret/paper.sqlite3"))
        self.assertTrue(delivered)  # the warning never changes delivery status
        photos.assert_called_once()
        self.assertNotIn("🤖 Робот", _buttons(photos.call_args))
        warnings = self._warnings(messages)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].args[:3], ("test-token", "owner", WARNING))
        self.assertEqual(warnings[0].kwargs, {})
        # The warning follows the ordinary card and photo; no exception text leaks.
        self.assertEqual(messages.call_args_list[-1].args[2], WARNING)
        for call in messages.call_args_list:
            self.assertNotIn("secret", call.args[2])
            self.assertNotIn("locked", call.args[2])

    def test_warning_goes_only_to_owner_with_multiple_recipients(self):
        _delivered, messages, photos, _create = self._send(
            recipients=("owner", "friend-one", "friend-two"),
            candidate_error=RuntimeError("persistence failed"))
        self.assertEqual([call.args[1] for call in self._warnings(messages)], ["owner"])
        # Ordinary delivery still reaches everyone: card to all, photo to all.
        cards = [call.args[1] for call in messages.call_args_list if call.args[2] != WARNING]
        self.assertEqual(cards, ["owner", "friend-one", "friend-two"])
        self.assertEqual([call.args[1] for call in photos.call_args_list],
                         ["owner", "friend-one", "friend-two"])
        for photo_call in photos.call_args_list:
            self.assertNotIn("🤖 Робот", _buttons(photo_call))

    def test_warning_send_failure_is_logged_once_and_not_retried(self):
        def fail_warning(token, chat_id, text, **kwargs):
            if text == WARNING:
                raise RuntimeError("telegram down")
            return {"ok": True}

        delivered, messages, photos, _create = self._send(
            candidate_error=RuntimeError("persistence failed"),
            message_side_effect=fail_warning)
        self.assertTrue(delivered)
        photos.assert_called_once()
        self.assertEqual(len(self._warnings(messages)), 1)  # attempted once, no retry


if __name__ == "__main__":
    unittest.main()
