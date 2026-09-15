from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import Mock, patch

from tools.e2e import run_robot_paper_acceptance


class RobotPaperAcceptanceDriverTests(unittest.TestCase):
    def test_load_suite_uses_only_curated_deterministic_scenarios(self):
        loader = Mock()
        loader.loadTestsFromName.side_effect = lambda name: unittest.TestSuite()

        run_robot_paper_acceptance._load_suite(loader)

        self.assertEqual(
            [call.args[0] for call in loader.loadTestsFromName.call_args_list],
            list(run_robot_paper_acceptance.SCENARIOS),
        )

    def test_run_propagates_success_and_failure(self):
        for successful, expected in ((True, 0), (False, 1)):
            with self.subTest(successful=successful):
                result = Mock()
                result.wasSuccessful.return_value = successful
                runner = Mock()
                runner.run.return_value = result
                with patch.object(run_robot_paper_acceptance, "_ensure_test_config"), patch.object(
                    run_robot_paper_acceptance, "_load_suite", return_value=unittest.TestSuite()
                ), patch("tools.e2e.run_robot_paper_acceptance.unittest.TextTestRunner", return_value=runner):
                    self.assertEqual(run_robot_paper_acceptance.run(), expected)

    def test_missing_machine_config_gets_non_secret_process_local_stub(self):
        prior = sys.modules.pop("config", None)
        self.addCleanup(lambda: sys.modules.__setitem__("config", prior) if prior is not None else sys.modules.pop("config", None))
        with patch("tools.e2e.run_robot_paper_acceptance.importlib.util.find_spec", return_value=None):
            run_robot_paper_acceptance._ensure_test_config()
        config = sys.modules["config"]
        self.assertIsInstance(config, types.ModuleType)
        self.assertEqual(config.MODE, "hunter")
        self.assertEqual(config.MIN_SCORE, 60)
        self.assertIsNone(config.MAX_SYMBOLS)
        self.assertIsNone(config.UNUSED_ACCEPTANCE_SETTING)

    def test_existing_machine_config_is_never_replaced(self):
        existing = types.ModuleType("config")
        prior = sys.modules.get("config")
        sys.modules["config"] = existing
        self.addCleanup(lambda: sys.modules.__setitem__("config", prior) if prior is not None else sys.modules.pop("config", None))
        run_robot_paper_acceptance._ensure_test_config()
        self.assertIs(sys.modules["config"], existing)

    def test_contract_covers_progression_real_topology_and_restart_idempotency(self):
        joined = "\n".join(run_robot_paper_acceptance.SCENARIOS)
        self.assertIn("test_full_limit_fill_creates_protected_trade", joined)
        self.assertIn("real_topology_limit_fill_and_protection", joined)
        self.assertIn("restart_with_stale_retest_detected_creates_exactly_one_order", joined)


if __name__ == "__main__":
    unittest.main()
