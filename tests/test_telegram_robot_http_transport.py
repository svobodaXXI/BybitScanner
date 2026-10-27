"""Regression contract for the existing Telegram -> Robot HTTP bridge.

The refactor must not change URLs, payloads, timeout, acceptance conditions,
error identity or exception propagation. No network, Robot runtime or PAPER DB.
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import requests

# telegram_review is normally loaded by telegram_monitoring at callback time.
# The local runtime config is intentionally absent on CI.
_previous_config = sys.modules.get("config")
sys.modules["config"] = ModuleType("config")
try:
    # Importing this legacy module creates a Windows-local review_queue.
    # Avoid any filesystem mutation in a transport-only regression.
    with patch("pathlib.Path.mkdir"):
        import telegram_review as review
finally:
    if _previous_config is None:
        sys.modules.pop("config", None)
    else:
        sys.modules["config"] = _previous_config


class RobotHttpTransportTests(unittest.TestCase):
    COMMANDS = (
        ("_post_robot_close_all_now", "close_all_now", "/api/robot/close-all-now"),
        ("_post_robot_synchronize_pending_entries", "synchronize_pending_entries",
         "/api/robot/synchronize-pending-entries"),
    )

    def test_success_keeps_url_payload_timeout_and_response(self):
        payload = {"client_action_id": "same-once"}
        body = {"ok": True, "status": "accepted", "correlation_id": "existing"}
        for function, name, path in self.COMMANDS:
            with self.subTest(command=name):
                endpoint = "http://127.0.0.1:8765" + path
                response = SimpleNamespace(status_code=200, json=lambda: body)
                with patch.object(review.requests, "post", return_value=response) as post:
                    result = getattr(review, function)(endpoint, payload)
                self.assertIs(result, body)
                post.assert_called_once_with(endpoint, json=payload, timeout=15)

    def test_rejected_response_preserves_per_command_error(self):
        payload = {"client_action_id": "same-once"}
        for function, name, path in self.COMMANDS:
            for status, body in (
                (409, {"ok": False, "error": "robot_paused"}),
                (200, {"ok": False, "error": "not_closed"}),
                (200, {"error": "missing_ok"}),
            ):
                with self.subTest(command=name, status=status, body=body):
                    response = SimpleNamespace(status_code=status, json=lambda: body)
                    with patch.object(review.requests, "post", return_value=response):
                        with self.assertRaisesRegex(
                            review.RobotControlRejected,
                            "PAPER backend rejected " + name + ":",
                        ):
                            getattr(review, function)("http://127.0.0.1:8765" + path, payload)

    def test_transport_errors_are_not_masked_or_retried(self):
        for function, name, path in self.COMMANDS:
            with self.subTest(command=name):
                with patch.object(review.requests, "post", side_effect=requests.Timeout("timeout")) as post:
                    with self.assertRaises(requests.Timeout):
                        getattr(review, function)("http://127.0.0.1:8765" + path, {})
                post.assert_called_once()


class TelegramCloseAllCallbackIdentityTests(unittest.TestCase):
    def test_same_confirmed_callback_preserves_action_id(self):
        callback = {"id": "telegram-opaque-123"}
        a = review._robot_close_all_callback_action_id(callback)
        b = review._robot_close_all_callback_action_id(dict(callback))
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("robot-close-all-cb-"))
        self.assertLessEqual(len(a), 128)
        self.assertNotIn(callback["id"], a)

    def test_distinct_confirmations_are_distinct_commands(self):
        first = review._robot_close_all_callback_action_id({"id": "confirmation-1"})
        second = review._robot_close_all_callback_action_id({"id": "confirmation-2"})
        self.assertNotEqual(first, second)

    def test_callback_confirm_passes_one_stable_id_without_ui_change(self):
        callback = {"id": "same-callback"}
        result = {"ok": True, "results": []}
        with patch.object(review, "close_all_now", return_value=result) as dispatch, \\
                patch.object(review, "_answer_callback") as ack, \\
                patch.object(review, "_send_robot_status_panel") as status:
            self.assertIs(review._confirm_close_all_now(callback), result)
            self.assertIs(review._confirm_close_all_now(callback), result)
        self.assertEqual(dispatch.call_count, 2)
        calls = [call.kwargs for call in dispatch.call_args_list]
        self.assertEqual(calls[0], calls[1])
        self.assertEqual(
            calls[0]["client_action_id"],
            review._robot_close_all_callback_action_id(callback),
        )
        self.assertIs(calls[0]["http_post"], review._post_robot_close_all_now)
        self.assertEqual(ack.call_count, 2)
        self.assertEqual(status.call_count, 2)

    def test_missing_callback_id_keeps_original_call_contract(self):
        self.assertIsNone(review._robot_close_all_callback_action_id({}))
        with patch.object(review, "close_all_now", return_value={"ok": True}) as dispatch, \\
                patch.object(review, "_answer_callback"), \\
                patch.object(review, "_send_robot_status_panel"):
            review._confirm_close_all_now({})
        dispatch.assert_called_once_with(
            http_post=review._post_robot_close_all_now,
        )


if __name__ == "__main__":
    unittest.main()
