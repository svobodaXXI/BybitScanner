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

import notification
import telegram_review
from robot_candidate_store import RobotCandidateNotFound
from terminal.application.robot_admission import RobotAdmissionRejected
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import RobotCandidateRecord, RobotRuntimeStateRecord


def _status(mode, recovery_status):
    return RobotRuntimeStateRecord(
        trading_account_id=TradingAccountId("paper"),
        mode=mode,
        recovery_status=recovery_status,
        reason=None,
        version=1,
        updated_at_ms=1000,
    )


class TelegramRobotHandoffTests(unittest.TestCase):
    def test_owner_robot_button_ignores_existing_candidate(self):
        for kwargs in ({"robot_candidate_id": "abc123"}, {"robot_status_button": True}, {}):
            with self.subTest(kwargs=kwargs):
                rows = notification.build_tradingview_keyboard(
                    "ONGUSDT", "1", include_review_actions=True, **kwargs,
                )["inline_keyboard"]
                buttons = [button for row in rows for button in row]
                self.assertEqual(
                    [b for b in buttons if b["text"] == "🤖 Робот"],
                    [{"text": "🤖 Робот",
                      "callback_data": "workspace:AUTOPILOT:ONGUSDT:1m"}],
                )
                self.assertFalse(any(
                    b.get("callback_data", "").startswith("robot:approve:") for b in buttons
                ))

    def test_non_owner_signal_never_gets_autopilot_navigation(self):
        buttons = [b for row in notification.build_tradingview_keyboard(
            "ONGUSDT", "1", include_review_actions=False,
            robot_candidate_id="abc123",
        )["inline_keyboard"] for b in row]
        self.assertFalse(any(b.get("text") == "🤖 Робот" for b in buttons))

    def test_owner_autopilot_callback_uses_view_only_workspace_path(self):
        query = {
            "id": "callback-autopilot",
            "data": "workspace:AUTOPILOT:ONGUSDT:1m",
            "from": {"id": 42},
            "message": {"chat": {"id": 42, "type": "private"}},
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
                patch.object(telegram_review, "admit_robot_candidate") as admit, \
                patch.object(telegram_review, "_run_workspace_callback") as launch:
            telegram_review._process_callback(query)
        admit.assert_not_called()
        launch.assert_called_once_with(query, {
            "kind": "workspace", "mode": "AUTOPILOT",
            "symbol": "ONGUSDT", "timeframe": "1m",
        })

    def test_legacy_candidate_approval_callback_is_retired_without_mutation(self):
        query = {
            "id": "callback-old", "data": "robot:approve:abc123",
            "from": {"id": 42}, "message": {"chat": {"id": 42, "type": "private"}},
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
                patch.object(telegram_review, "admit_robot_candidate") as admit, \
                patch.object(telegram_review, "_send_robot_status_panel") as panel, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(query)
        admit.assert_not_called()
        panel.assert_not_called()
        answer.assert_called_once()
        self.assertIn("устарела", answer.call_args.args[1])

    def test_non_owner_legacy_button_is_rejected_without_mutation(self):
        query = {
            "id": "callback-other", "data": "robot:approve:abc123",
            "from": {"id": 99}, "message": {"chat": {"id": 99, "type": "private"}},
        }
        with patch.object(telegram_review.config, "TELEGRAM_CHAT_ID", "42"), \
                patch.object(telegram_review, "admit_robot_candidate") as admit, \
                patch.object(telegram_review, "_answer_callback") as answer:
            telegram_review._process_callback(query)
        admit.assert_not_called()
        answer.assert_called_once_with("callback-other", "Недостаточно прав")


if __name__ == "__main__":
    unittest.main()
