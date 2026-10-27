"""Close-All must not dispatch PAPER Market orders on ambiguous Robot ownership.

All tests are synthetic in-memory owner/store projections: no service, DB,
network, market execution or protected runtime transitions.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import CommandResultStatus
from tests.test_robot_close_all_residual_proof import fake_runtime, perform_close


class RobotCloseAllOwnerPreflightTests(unittest.TestCase):
    def test_two_open_candidates_same_net_symbol_block_all_market_closes(self):
        runtime, store, close, _ = fake_runtime(
            robot_symbols=("BOTUSDT", "BOTUSDT"),
        )
        response = perform_close(runtime)
        self.assertEqual(len(response.results), 2)
        self.assertTrue(all(
            result.status is CommandResultStatus.UNAVAILABLE
            and result.reason_code == "robot_owner_unproven"
            and result.reconciliation_required
            for result in response.results
        ))
        close.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()
        self.assertEqual(
            store.update_robot_runtime_state.call_args.kwargs["recovery_status"],
            "RECONCILIATION_REQUIRED",
        )

    def test_other_symbols_do_not_partially_close_if_one_is_ambiguous(self):
        runtime, store, close, _ = fake_runtime(
            robot_symbols=("BOTUSDT", "BOTUSDT", "SAFEUSDT"),
        )
        response = perform_close(runtime)
        self.assertEqual(len(response.results), 3)
        close.assert_not_called()
        self.assertTrue(all(
            result.reason_code == "robot_owner_unproven"
            for result in response.results
        ))
        store.update_robot_runtime_state.assert_called_once()

    def test_filled_pending_candidate_is_second_owner(self):
        runtime, store, close, _ = fake_runtime()
        owner = store.load_active_robot_candidate_states.return_value[0]
        filled_pending = SimpleNamespace(
            candidate_id="pending-filled",
            symbol=owner.symbol,
            status="APPROVED",
            robot_state={"execution": {"limit_order_id": "limit-123"}},
        )
        store.load_active_robot_candidate_states.return_value = (owner, filled_pending)
        store.get_paper_limit = Mock(return_value=SimpleNamespace(
            filled_quantity=Decimal("0.3"),
        ))
        response = perform_close(runtime)
        self.assertEqual(response.results[0].reason_code, "robot_owner_unproven")
        close.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()

    def test_unfilled_pending_candidate_is_not_an_exposure_owner(self):
        runtime, store, close, _ = fake_runtime()
        owner = store.load_active_robot_candidate_states.return_value[0]
        pending = SimpleNamespace(
            candidate_id="pending-unfilled",
            symbol=owner.symbol,
            status="APPROVED",
            robot_state={"execution": {"limit_order_id": "limit-123"}},
        )
        store.load_active_robot_candidate_states.return_value = (owner, pending)
        store.get_paper_limit = Mock(return_value=SimpleNamespace(
            filled_quantity=Decimal("0"),
        ))
        response = perform_close(runtime)
        self.assertEqual(response.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_ownership_lookup_failure_fails_closed_without_dispatch(self):
        runtime, store, close, _ = fake_runtime()
        store.load_active_robot_candidate_states.side_effect = LookupError(
            "ownership unavailable",
        )
        response = perform_close(runtime)
        self.assertEqual(response.results[0].reason_code, "robot_owner_unproven")
        close.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()

    def test_box_close_is_not_dispatched_on_duplicate_owner(self):
        runtime, store, close, _ = fake_runtime(
            robot_symbols=("BOTUSDT", "BOTUSDT"),
        )
        for candidate in store.load_robot_candidates_by_status.return_value:
            candidate.signal_snapshot["pattern"] = "IKIGAI_BOX"
        response = perform_close(runtime)
        self.assertTrue(all(
            result.status is CommandResultStatus.UNAVAILABLE
            for result in response.results
        ))
        runtime._robot_close_box_candidate.assert_not_called()
        close.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()


if __name__ == "__main__":
    unittest.main()
