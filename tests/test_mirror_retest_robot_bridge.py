"""MIRROR-INTEGRATION-1: no-execution contract tests."""
import unittest

from geometry.naked_retest import PHASE_CAMPAIGN_ACTIVE, PHASE_RETEST_PROVEN
from retest_campaign import open_campaign_budget
from mirror_retest_robot_bridge import observe_for_robot


class MirrorRobotBridgeTests(unittest.TestCase):
    def state(self, phase=PHASE_CAMPAIGN_ACTIVE, **kwargs):
        return {
            "boundary_id": "b1",
            "phase": phase,
            "breakout": {"campaign_direction": "SHORT"},
            "data_blocked": False,
            **kwargs,
        }

    def test_policy_allow_never_becomes_robot_admission(self):
        row = observe_for_robot(
            boundary_id="b1", state=self.state(),
            budget=open_campaign_budget(10),
            data_reliable=True,
            realized_loss_costs_usdt=0,
            live_pending_worst_case_usdt=0,
            new_attempt_worst_case_usdt=1,
            remaining_net_reward_usdt=20,
        )
        self.assertEqual(row.risk_decision, "ALLOW")
        self.assertFalse(row.executable)
        self.assertFalse(row.admission_allowed)
        self.assertEqual(row.mode, "OBSERVE_ONLY")

    def test_unknown_risk_waits(self):
        row = observe_for_robot(boundary_id="b1", state=self.state(),
                                budget=open_campaign_budget(10))
        self.assertEqual(row.risk_decision, "WAIT")
        self.assertFalse(row.admission_allowed)

    def test_data_blocked_never_allows(self):
        row = observe_for_robot(
            boundary_id="b1", state=self.state(data_blocked=True),
            budget=open_campaign_budget(10), data_reliable=True,
            realized_loss_costs_usdt=0, live_pending_worst_case_usdt=0,
            new_attempt_worst_case_usdt=1, remaining_net_reward_usdt=20)
        self.assertEqual(row.risk_decision, "WAIT")

    def test_terminal_retest_is_not_an_exit_order(self):
        row = observe_for_robot(boundary_id="b1", state=self.state(PHASE_RETEST_PROVEN))
        self.assertEqual(row.exit_intent, "CLOSE_REMAINDER")
        self.assertEqual(row.risk_decision, "DENY")
        self.assertFalse(row.executable)

    def test_wrong_boundary_fails_closed(self):
        with self.assertRaises(ValueError):
            observe_for_robot(boundary_id="another", state=self.state())


if __name__ == "__main__":
    unittest.main()
