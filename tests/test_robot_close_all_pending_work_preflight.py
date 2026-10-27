"""Close-All must not race outstanding Robot ENTRYs or STOP/TAKE dispatches.

Synthetic PAPER owner-only tests: no exchange, Telegram, DB, or live process.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import CommandResultStatus
from terminal.domain.models import OrderId, Symbol
from tests.test_robot_close_all_residual_proof import fake_runtime, perform_close


def assert_fenced(testcase, runtime, store, close, reason="robot_close_work_inflight"):
    result = perform_close(runtime)
    testcase.assertGreater(len(result.results), 0)
    testcase.assertTrue(all(
        item.status is CommandResultStatus.UNAVAILABLE
        and item.reason_code == reason
        and item.reconciliation_required
        for item in result.results
    ))
    close.assert_not_called()
    runtime._robot_close_box_candidate.assert_not_called()
    store.update_robot_runtime_state.assert_called_once()
    testcase.assertEqual(
        store.update_robot_runtime_state.call_args.kwargs["recovery_status"],
        "RECONCILIATION_REQUIRED",
    )


class CloseAllPendingWorkPreflightTests(unittest.TestCase):
    def test_active_robot_entry_on_target_symbol_prevents_market_close(self):
        runtime, store, close, _ = fake_runtime()
        store.load_active_robot_entry_orders.return_value = {
            "entry-1": (Symbol("BOTUSDT"), 7),
        }
        assert_fenced(self, runtime, store, close)

    def test_other_symbol_entry_does_not_block_owned_close(self):
        runtime, store, close, _ = fake_runtime()
        store.load_active_robot_entry_orders.return_value = {
            "entry-other": (Symbol("OTHERUSDT"), 7),
        }
        result = perform_close(runtime)
        self.assertEqual(result.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_unresolved_protection_on_target_prevents_second_close(self):
        runtime, store, close, _ = fake_runtime()
        store.load_unresolved_paper_protection_obligations.return_value = (
            SimpleNamespace(symbol=Symbol("BOTUSDT"), status="DISPATCHING"),
        )
        assert_fenced(self, runtime, store, close)

    def test_other_symbol_obligation_does_not_block_robot_close(self):
        runtime, store, close, _ = fake_runtime()
        store.load_unresolved_paper_protection_obligations.return_value = (
            SimpleNamespace(symbol=Symbol("OTHERUSDT"), status="TRIGGERED"),
        )
        result = perform_close(runtime)
        self.assertEqual(result.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_legacy_linked_active_entry_is_detected(self):
        runtime, store, close, _ = fake_runtime()
        runtime._robot_linked_entry_limits.return_value = {"legacy-entry": 7}
        store.load_active_paper_limits.return_value = (
            SimpleNamespace(order_id=OrderId("legacy-entry")),
        )
        assert_fenced(self, runtime, store, close)

    def test_inactive_linked_entry_does_not_block(self):
        runtime, store, close, _ = fake_runtime()
        runtime._robot_linked_entry_limits.return_value = {"old-cancelled": 7}
        store.load_active_paper_limits.return_value = ()
        result = perform_close(runtime)
        self.assertEqual(result.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()

    def test_manual_or_box_exit_limits_not_identified_as_entry_do_not_block(self):
        runtime, store, close, _ = fake_runtime()
        store.load_active_paper_limits.return_value = (
            SimpleNamespace(order_id=OrderId("manual-order")),
            SimpleNamespace(order_id=OrderId("box-take-slot-1")),
        )
        result = perform_close(runtime)
        self.assertEqual(result.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()

    def test_unavailable_entry_ownership_evidence_fails_closed(self):
        runtime, store, close, _ = fake_runtime()
        store.load_active_robot_entry_orders.side_effect = LookupError("cannot read")
        assert_fenced(self, runtime, store, close)

    def test_unavailable_protection_evidence_fails_closed(self):
        runtime, store, close, _ = fake_runtime()
        store.load_unresolved_paper_protection_obligations.side_effect = RuntimeError(
            "cannot read protection",
        )
        assert_fenced(self, runtime, store, close)

    def test_unavailable_legacy_links_fails_closed(self):
        runtime, store, close, _ = fake_runtime()
        runtime._robot_linked_entry_limits.side_effect = LookupError("cannot read")
        assert_fenced(self, runtime, store, close)

    def test_no_partial_dispatch_if_one_of_two_symbols_has_pending_work(self):
        runtime, store, close, _ = fake_runtime(robot_symbols=("BOTUSDT", "SAFEUSDT"))
        store.load_active_robot_entry_orders.return_value = {
            "entry-1": (Symbol("BOTUSDT"), 7),
        }
        result = perform_close(runtime)
        self.assertEqual(len(result.results), 2)
        self.assertTrue(all(
            item.reason_code == "robot_close_work_inflight"
            for item in result.results
        ))
        close.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()

    def test_no_open_robot_owner_preserves_noop_without_new_preflight(self):
        runtime, store, close, _ = fake_runtime(robot_symbols=())
        result = perform_close(runtime)
        self.assertEqual(result.results, ())
        close.assert_not_called()
        store.load_active_robot_entry_orders.assert_not_called()
        store.load_unresolved_paper_protection_obligations.assert_not_called()
        store.update_robot_runtime_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
