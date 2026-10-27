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


if __name__ == "__main__":
    unittest.main()
