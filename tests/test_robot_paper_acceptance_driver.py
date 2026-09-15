from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from tools.e2e import run_robot_paper_acceptance


class RobotPaperAcceptanceDriverTests(unittest.TestCase):
    def test_runs_only_curated_deterministic_scenarios_and_propagates_success(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0)
        with patch("tools.e2e.run_robot_paper_acceptance.subprocess.run", return_value=completed) as run:
            self.assertEqual(run_robot_paper_acceptance.run(), 0)

        command = run.call_args.args[0]
        self.assertEqual(command[:4], [
            run_robot_paper_acceptance.sys.executable, "-m", "unittest", "-v",
        ])
        self.assertEqual(tuple(command[4:]), run_robot_paper_acceptance.SCENARIOS)
        self.assertTrue(all(name.startswith("tests.") for name in command[4:]))
        self.assertFalse(run.call_args.kwargs["check"])

    def test_propagates_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=7)
        with patch("tools.e2e.run_robot_paper_acceptance.subprocess.run", return_value=completed):
            self.assertEqual(run_robot_paper_acceptance.run(), 7)

    def test_contract_covers_progression_real_topology_and_restart_idempotency(self):
        joined = "\n".join(run_robot_paper_acceptance.SCENARIOS)
        self.assertIn("test_full_limit_fill_creates_protected_trade", joined)
        self.assertIn("real_topology_limit_fill_and_protection", joined)
        self.assertIn("restart_with_stale_retest_detected_creates_exactly_one_order", joined)


if __name__ == "__main__":
    unittest.main()
