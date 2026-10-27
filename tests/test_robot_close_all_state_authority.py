"""Existing Robot close-all state policy must agree across Telegram and backend.

No network calls, startup, PAPER DB writes or order execution.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from terminal.application.robot_control import (
    ROBOT_CLOSE_ALL_ALLOWED_STATES,
    robot_close_all_is_legal,
)
from terminal.runtime.paper_http_server import (
    RobotRouteLegalityError,
    _require_robot_route_legality,
)


class RobotCloseAllStateAuthorityTests(unittest.TestCase):
    def test_telegram_and_backend_share_exact_close_all_states(self):
        self.assertEqual(
            ROBOT_CLOSE_ALL_ALLOWED_STATES,
            frozenset({
                ("ROBOT_RUNNING", "READY"),
                ("ROBOT_RUNNING", "PAUSED"),
            }),
        )
        for mode in ("ROBOT_RUNNING", "ROBOT_STOPPED"):
            for recovery in ("READY", "PAUSED", "RECONCILIATION_REQUIRED", "ROBOT_STOPPED"):
                with self.subTest(mode=mode, recovery=recovery):
                    expected = (mode, recovery) in ROBOT_CLOSE_ALL_ALLOWED_STATES
                    self.assertEqual(robot_close_all_is_legal(mode, recovery), expected)
                    state = SimpleNamespace(mode=mode, recovery_status=recovery)
                    store = SimpleNamespace(get_robot_runtime_state=lambda account: state)
                    runtime = SimpleNamespace(store=store)
                    if expected:
                        self.assertIsNone(
                            _require_robot_route_legality(runtime, "close_all_now")
                        )
                    else:
                        with self.assertRaises(RobotRouteLegalityError):
                            _require_robot_route_legality(runtime, "close_all_now")

    def test_backend_requires_existing_runtime_state(self):
        runtime = SimpleNamespace(store=SimpleNamespace(
            get_robot_runtime_state=lambda account: None,
        ))
        with self.assertRaisesRegex(RobotRouteLegalityError, "state is unavailable"):
            _require_robot_route_legality(runtime, "close_all_now")

    def test_non_close_commands_keep_their_distinct_permissions(self):
        state = SimpleNamespace(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        runtime = SimpleNamespace(store=SimpleNamespace(
            get_robot_runtime_state=lambda account: state,
        ))
        self.assertIsNone(
            _require_robot_route_legality(runtime, "synchronize_pending_entries")
        )
        with self.assertRaises(RobotRouteLegalityError):
            _require_robot_route_legality(runtime, "reconcile_robot")


if __name__ == "__main__":
    unittest.main()
