import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from terminal.application.robot_control import RobotControlRejected
from terminal.persistence.sqlite_store import SQLiteStore
import tools.stop_robot_runtime as shutdown


class SafeStopRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "paper.sqlite3"
        store = SQLiteStore.open(self.db)
        try:
            self.identity = store.database_identity
        finally:
            store.close()

    def _response(self, payload, *, status=200):
        response = Mock(status_code=status)
        response.json.return_value = payload
        return response

    def test_safe_stop_proves_identity_then_stops_scanner_then_robot(self):
        health = self._response({
            "ok": True,
            "component": "paper_backend",
            "mode": "paper",
            "database_identity": self.identity,
        })
        scanner = self._response({"ok": True, "mode": "SCANNER_STOPPED"})
        order = []

        def get(*args, **kwargs):
            order.append("health")
            return health

        def post(*args, **kwargs):
            order.append("scanner")
            return scanner

        def robot_stop(**kwargs):
            order.append("robot")

        with patch.dict(os.environ, {
            "BYBITSCANNER_PAPER_DB": str(self.db),
            "BYBITSCANNER_PAPER_BACKEND_URL": "http://127.0.0.1:8765",
        }), patch.object(shutdown.requests, "get", side_effect=get), patch.object(
            shutdown.requests, "post", side_effect=post
        ), patch.object(shutdown, "stop_robot", side_effect=robot_stop) as stop:
            shutdown.safe_stop()

        self.assertEqual(order, ["health", "scanner", "robot"])
        stop.assert_called_once()
        self.assertEqual(stop.call_args.kwargs["database_path"], self.db)
        self.assertEqual(stop.call_args.kwargs["backend_url"], "http://127.0.0.1:8765")

    def test_wrong_backend_identity_blocks_before_any_stop(self):
        health = self._response({
            "ok": True,
            "component": "paper_backend",
            "mode": "paper",
            "database_identity": "0" * 64,
        })
        with patch.dict(os.environ, {
            "BYBITSCANNER_PAPER_DB": str(self.db),
        }), patch.object(shutdown.requests, "get", return_value=health), patch.object(
            shutdown.requests, "post"
        ) as post, patch.object(shutdown, "stop_robot") as robot:
            with self.assertRaisesRegex(shutdown.SafeStopError, "identity"):
                shutdown.safe_stop()
        post.assert_not_called()
        robot.assert_not_called()

    def test_scanner_stop_failure_blocks_robot_stop(self):
        health = self._response({
            "ok": True,
            "component": "paper_backend",
            "mode": "paper",
            "database_identity": self.identity,
        })
        scanner = self._response({"ok": False, "error": "scanner_control_unavailable"}, status=503)
        with patch.dict(os.environ, {
            "BYBITSCANNER_PAPER_DB": str(self.db),
        }), patch.object(shutdown.requests, "get", return_value=health), patch.object(
            shutdown.requests, "post", return_value=scanner
        ), patch.object(shutdown, "stop_robot") as robot:
            with self.assertRaises(shutdown.SafeStopError):
                shutdown.safe_stop()
        robot.assert_not_called()

    def test_open_position_robot_rejection_is_fail_closed(self):
        health = self._response({
            "ok": True,
            "component": "paper_backend",
            "mode": "paper",
            "database_identity": self.identity,
        })
        scanner = self._response({"ok": True, "mode": "SCANNER_STOPPED"})
        with patch.dict(os.environ, {
            "BYBITSCANNER_PAPER_DB": str(self.db),
        }), patch.object(shutdown.requests, "get", return_value=health), patch.object(
            shutdown.requests, "post", return_value=scanner
        ), patch.object(
            shutdown,
            "stop_robot",
            side_effect=RobotControlRejected("open Robot position"),
        ):
            with self.assertRaisesRegex(RobotControlRejected, "open Robot position"):
                shutdown.safe_stop()

    def test_main_returns_nonzero_on_blocked_stop(self):
        with patch.object(
            shutdown,
            "safe_stop",
            side_effect=shutdown.SafeStopError("wrong backend"),
        ):
            self.assertEqual(shutdown.main(), 1)


if __name__ == "__main__":
    unittest.main()
