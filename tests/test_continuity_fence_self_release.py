"""A coverage-loss barrier is released only after the proven recovery of its own event.

ALABUSDT-like sequence on a temporary PAPER DB: websocket loss with a Box that has
four resting entry LIMITs -> durable RECONCILIATION_REQUIRED barrier -> recovery
cancels the LIMITs and proves no exposure -> the barrier from that same event is
released (back to READY, or PAUSED if the owner had paused). Everything else stays
fenced. No runtime, network or real DB is used.
"""

import tempfile
import time
import unittest

from tests.test_continuity_recovery_candidate_snapshot import (
    ACCOUNT,
    _footprint,
    _recover,
    _runtime,
    _seed_box_with_four_entry_limits,
    _status,
)
from tests.test_terminal_paper_runtime import _set_admission

SYMBOL = "BTCUSDT"
LOSS = "websocket_disconnect:SSLError"
HEALTHY = lambda: True  # noqa: E731
UNHEALTHY = lambda: False  # noqa: E731


def _state(runtime):
    state = runtime.store.get_robot_runtime_state(ACCOUNT)
    return state.mode, state.recovery_status


class ContinuityFenceSelfReleaseTests(unittest.TestCase):
    def _fenced_and_recovered(self, temp, prior):
        runtime = _runtime(temp)
        _set_admission(runtime, mode="ROBOT_RUNNING", recovery_status=prior)
        _candidate, order_ids = _seed_box_with_four_entry_limits(runtime)
        self.assertTrue(runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS))
        self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
        self.assertTrue(_recover(runtime))
        # Recovery alone never lifts the barrier.
        self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
        return runtime, order_ids

    def test_ready_before_loss_is_ready_again_without_new_orders_or_fills(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, order_ids = self._fenced_and_recovered(temp, "READY")
            try:
                before = _footprint(runtime)
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "READY"))
                self.assertEqual([_status(runtime, o) for o in order_ids], ["cancelled"] * 4)
                self.assertEqual(_footprint(runtime), before)
                self.assertIsNone(runtime.store.get_robot_runtime_state(ACCOUNT).reason)
            finally:
                runtime.close()

    def test_owner_pause_before_loss_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self._fenced_and_recovered(temp, "PAUSED")
            try:
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "PAUSED"))
            finally:
                runtime.close()

    def test_release_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self._fenced_and_recovered(temp, "READY")
            try:
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                footprint = _footprint(runtime)
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "READY"))
                self.assertEqual(_footprint(runtime), footprint)
            finally:
                runtime.close()

    def test_unhealthy_ingress_keeps_the_fence_until_every_symbol_recovers(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self._fenced_and_recovered(temp, "READY")
            try:
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=UNHEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
                # A later recovery of ANOTHER symbol, once ingress is healthy, releases
                # the fence of the event whose own recovery was already proven.
                self.assertTrue(runtime.release_robot_protection_continuity_fence(
                    "ETHUSDT", ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "READY"))
            finally:
                runtime.close()

    def test_unrecovered_event_is_never_released(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _seed_box_with_four_entry_limits(runtime)
                runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS)
                # A different symbol's proven recovery says nothing about this event.
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    "ETHUSDT", ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
            finally:
                runtime.close()

    def test_preexisting_independent_reconciliation_cause_is_not_released(self):
        with tempfile.TemporaryDirectory() as temp:
            runtime = _runtime(temp)
            try:
                _seed_box_with_four_entry_limits(runtime)
                state = runtime.store.get_robot_runtime_state(ACCOUNT)
                runtime.store.update_robot_runtime_state(
                    ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
                    reason="ROBOT_BOX_EMERGENCY_CLOSE_PENDING symbol=BTCUSDT",
                    expected_version=state.version, updated_at_ms=int(time.time() * 1000) + 60_000,
                )
                runtime.fence_robot_protection_continuity_loss(SYMBOL, LOSS)
                self.assertTrue(_recover(runtime))
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                state = runtime.store.get_robot_runtime_state(ACCOUNT)
                self.assertEqual(state.recovery_status, "RECONCILIATION_REQUIRED")
                self.assertTrue(state.reason.startswith("ROBOT_BOX_EMERGENCY_CLOSE_PENDING"))
            finally:
                runtime.close()

    def test_fence_without_in_process_origin_stays_operator_controlled(self):
        # E.g. a durable fence that survived a restart.
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self._fenced_and_recovered(temp, "READY")
            try:
                runtime._continuity_fence_origin.clear()
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
            finally:
                runtime.close()

    def test_residual_exposure_keeps_the_fence_closed(self):
        # A later change to the fence (new version) means it is no longer the
        # event we proved; nothing is released and nothing is traded.
        with tempfile.TemporaryDirectory() as temp:
            runtime, _ = self._fenced_and_recovered(temp, "READY")
            try:
                state = runtime.store.get_robot_runtime_state(ACCOUNT)
                runtime.store.update_robot_runtime_state(
                    ACCOUNT, mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED",
                    reason=state.reason, expected_version=state.version, updated_at_ms=int(time.time() * 1000) + 60_000,
                )
                footprint = _footprint(runtime)
                self.assertFalse(runtime.release_robot_protection_continuity_fence(
                    SYMBOL, ingress_healthy=HEALTHY,
                ))
                self.assertEqual(_state(runtime), ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"))
                self.assertEqual(_footprint(runtime), footprint)
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
