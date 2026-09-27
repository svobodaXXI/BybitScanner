import contextlib
import io
import unittest
from unittest.mock import patch

import pattern_robot_integration as integration


class PatternRobotIntegrationTests(unittest.TestCase):
    def test_wedge_capability_preserves_existing_timeframe_rules(self):
        base = {"pattern": "Falling Wedge", "symbol": "TESTUSDT"}

        self.assertTrue(
            integration.is_robot_executable_signal(base, timeframe="1")
        )
        self.assertFalse(
            integration.is_robot_executable_signal(base, timeframe="5")
        )
        self.assertTrue(
            integration.is_robot_executable_signal(
                {**base, "robot_handoff_ready": True},
                timeframe="5",
            )
        )
        self.assertFalse(
            integration.is_robot_executable_signal(
                {**base, "scanner_observational_only": True},
                timeframe="1",
            )
        )

    def test_l_shape_capability_uses_shared_boundary_without_wedge_support(self):
        snapshot = {
            "pattern": "L-shape",
            "symbol": "TESTUSDT",
            "robot_handoff_ready": True,
        }

        self.assertTrue(
            integration.is_robot_executable_signal(snapshot, timeframe="1")
        )
        self.assertTrue(
            integration.is_robot_executable_signal(snapshot, timeframe="5")
        )
        self.assertFalse(
            integration.is_robot_executable_signal(snapshot, timeframe="15")
        )

    def test_unsupported_pattern_never_persists_candidate(self):
        snapshot = {
            "pattern": "Ikigai Box",
            "symbol": "TESTUSDT",
            "robot_handoff_ready": True,
        }
        with patch.object(integration, "create_signal_snapshot") as persist:
            result = integration.prepare_robot_handoff(
                snapshot,
                timeframe="5",
                enabled=True,
            )

        self.assertFalse(result.executable)
        self.assertIsNone(result.candidate_id)
        self.assertFalse(result.persistence_failed)
        persist.assert_not_called()

    def test_disabled_handoff_never_persists_executable_signal(self):
        snapshot = {"pattern": "Rising Wedge", "symbol": "TESTUSDT"}
        with patch.object(integration, "create_signal_snapshot") as persist:
            result = integration.prepare_robot_handoff(
                snapshot,
                timeframe="1",
                enabled=False,
            )

        self.assertTrue(result.executable)
        self.assertIsNone(result.candidate_id)
        persist.assert_not_called()

    def test_persistence_success_returns_only_candidate_identity(self):
        snapshot = {"pattern": "Falling Wedge", "symbol": "TESTUSDT"}
        with patch.object(
            integration,
            "create_signal_snapshot",
            return_value={"candidate_id": "candidate-1"},
        ) as persist:
            result = integration.prepare_robot_handoff(
                snapshot,
                timeframe="1",
                enabled=True,
            )

        self.assertEqual(result.candidate_id, "candidate-1")
        self.assertTrue(result.executable)
        self.assertFalse(result.persistence_failed)
        persist.assert_called_once_with(snapshot, timeframe="1")

    def test_persistence_failure_is_fail_closed(self):
        snapshot = {"pattern": "L-shape", "symbol": "TESTUSDT", "robot_handoff_ready": True}
        with patch.object(
            integration,
            "create_signal_snapshot",
            side_effect=OSError("disk full"),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            result = integration.prepare_robot_handoff(
                snapshot,
                timeframe="5",
                enabled=True,
            )

        self.assertTrue(result.executable)
        self.assertIsNone(result.candidate_id)
        self.assertTrue(result.persistence_failed)
        self.assertIn("[ROBOT CANDIDATE ERROR]", output.getvalue())


if __name__ == "__main__":
    unittest.main()
