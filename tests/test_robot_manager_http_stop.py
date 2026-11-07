"""Focused contract for Terminal's Robot-only canonical STOP bridge.

Tests never run an actual order, HTTP server, or PAPER database mutation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from terminal.application.robot_control import RobotControlRejected
from terminal.runtime.paper_http_server import PaperHttpHandler


def make_handler(mode="ROBOT_STOPPED", recovery="ROBOT_STOPPED"):
    owner = SimpleNamespace(
        store=SimpleNamespace(normalized_path="/tmp/canonical-paper-test.sqlite3"),
        robot_runtime_state=lambda: SimpleNamespace(mode=mode, recovery_status=recovery),
    )
    runtime = SimpleNamespace(call=lambda callback: callback(owner))
    handler = PaperHttpHandler.__new__(PaperHttpHandler)
    handler.path = "/api/robot/stop"
    handler.server = SimpleNamespace(runtime=runtime, server_address=("127.0.0.1", 8765))
    handler._payload = lambda fields: {}
    replies = []
    handler._json_response = lambda status, body: replies.append((status, body))
    return handler, replies


class RobotManagerHttpStopTests(TestCase):
    def test_reuses_canonical_command_and_one_nested_pending_entry_sync(self):
        handler, replies = make_handler()
        observed = []

        def canonical_command(**kwargs):
            observed.append((kwargs["database_path"], kwargs["backend_url"]))
            actual_url = kwargs["backend_url"] + "/api/robot/synchronize-pending-entries"
            body = kwargs["http_post"](actual_url, {})
            self.assertTrue(body["ok"])

        with patch("terminal.runtime.paper_http_server.stop_robot", side_effect=canonical_command), patch(
            "terminal.runtime.paper_http_server.requests.post"
        ) as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"ok": True, "unresolved_candidate_ids": []}
            handler.do_POST()

        self.assertEqual(observed, [("/tmp/canonical-paper-test.sqlite3", "http://127.0.0.1:8765")])
        post.assert_called_once_with(
            "http://127.0.0.1:8765/api/robot/synchronize-pending-entries",
            json={}, timeout=15,
        )
        self.assertEqual(replies, [(200, {"ok": True, "robot": "ROBOT_STOPPED"})])

    def test_refuses_stop_with_open_robot_trades_without_fallback(self):
        handler, replies = make_handler(mode="ROBOT_RUNNING", recovery="READY")
        with patch(
            "terminal.runtime.paper_http_server.stop_robot",
            side_effect=RobotControlRejected("stop_robot is rejected while OPEN Robot trades remain"),
        ), patch("terminal.runtime.paper_http_server.requests.post") as post:
            handler.do_POST()
        self.assertEqual(replies, [
            (409, {"ok": False, "error": "stop_robot is rejected while OPEN Robot trades remain"})
        ])
        post.assert_not_called()

    def test_reports_unknown_postcondition_instead_of_success(self):
        handler, replies = make_handler(mode="ROBOT_RUNNING", recovery="RECONCILIATION_REQUIRED")
        with patch("terminal.runtime.paper_http_server.stop_robot"):
            handler.do_POST()
        self.assertEqual(replies, [(409, {"ok": False, "error": "robot_stop_not_converged"})])

    def test_rejected_sync_is_not_reported_as_stopped(self):
        handler, replies = make_handler()
        def canonical_command(**kwargs):
            kwargs["http_post"](kwargs["backend_url"] + "/api/robot/synchronize-pending-entries", {})
        with patch("terminal.runtime.paper_http_server.stop_robot", side_effect=canonical_command), patch(
            "terminal.runtime.paper_http_server.requests.post"
        ) as post:
            post.return_value.status_code = 409
            post.return_value.json.return_value = {"ok": False, "error": "pending_exposure"}
            handler.do_POST()
        self.assertEqual(replies, [(409, {"ok": False, "error": "synchronize_pending_entries_rejected"})])
