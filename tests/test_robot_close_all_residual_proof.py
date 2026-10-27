"""Robot close-all must not leave admission READY over unconfirmed owned exposure.

Pure synthetic owner/store tests: no HTTP, orders, running processes or PAPER DB.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import (
    ClientActionId, CloseAllCommandRequest, CommandResult, CommandResultStatus,
)
from terminal.domain.models import TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT = TradingAccountId("paper")


def fake_runtime(*, robot_symbols=("BOTUSDT",), remaining=(),
                 status=CommandResultStatus.COMPLETED, inventory_error=None):
    candidates = [
        SimpleNamespace(
            symbol=SimpleNamespace(value=symbol),
            signal_snapshot={"pattern": "Falling Wedge"},
        )
        for symbol in robot_symbols
    ]
    store = SimpleNamespace(
        load_robot_candidates_by_status=Mock(return_value=candidates),
        get_robot_runtime_state=Mock(return_value=SimpleNamespace(
            mode="ROBOT_RUNNING", recovery_status="READY", version=7,
        )),
        update_robot_runtime_state=Mock(),
    )
    close = Mock(side_effect=lambda request: CommandResult(
        request.client_action_id.value, status, "test", "test",
    ))
    if inventory_error:
        inventory = Mock(side_effect=inventory_error)
    else:
        inventory = Mock(return_value=SimpleNamespace(positions=tuple(
            SimpleNamespace(symbol=symbol, position_quantity=Decimal(str(quantity)))
            for symbol, quantity in remaining
        )))
    runtime = SimpleNamespace(
        _account_id=ACCOUNT,
        store=store,
        _robot_full_close=close,
        _robot_close_box_candidate=Mock(),
        open_positions=inventory,
    )
    return runtime, store, close, inventory


def perform_close(runtime):
    return PaperRuntime.robot_close_all(
        runtime, CloseAllCommandRequest(ClientActionId("close-request")),
    )


class RobotCloseAllResidualProofTests(unittest.TestCase):
    def test_completed_command_with_remaining_owned_position_requires_reconcile(self):
        runtime, store, close, inventory = fake_runtime(
            remaining=(("BOTUSDT", "2.50"),),
        )
        response = perform_close(runtime)
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].status, CommandResultStatus.COMPLETED)
        self.assertEqual(response.positions[0].symbol, "BOTUSDT")
        close.assert_called_once()
        inventory.assert_called_once()
        store.update_robot_runtime_state.assert_called_once()
        self.assertEqual(
            store.update_robot_runtime_state.call_args.kwargs["recovery_status"],
            "RECONCILIATION_REQUIRED",
        )

    def test_confirmed_flat_does_not_change_runtime_state(self):
        runtime, store, close, inventory = fake_runtime(remaining=())
        response = perform_close(runtime)
        self.assertEqual(response.positions, ())
        close.assert_called_once()
        inventory.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_other_account_paper_position_stays_out_of_robot_scope(self):
        runtime, store, close, inventory = fake_runtime(
            remaining=(("MANUALUSDT", "1"),),
        )
        response = perform_close(runtime)
        self.assertEqual(response.positions[0].symbol, "MANUALUSDT")
        close.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_unconfirmed_command_status_keeps_existing_fence(self):
        runtime, store, close, inventory = fake_runtime(
            status=CommandResultStatus.UNKNOWN,
        )
        response = perform_close(runtime)
        self.assertEqual(response.results[0].status, CommandResultStatus.UNKNOWN)
        store.update_robot_runtime_state.assert_called_once()

    def test_inventory_failure_fences_before_reporting_failure(self):
        runtime, store, close, inventory = fake_runtime(
            inventory_error=LookupError("inventory unavailable"),
        )
        with self.assertRaises(RuntimeError):
            perform_close(runtime)
        close.assert_called_once()
        inventory.assert_called_once()
        store.update_robot_runtime_state.assert_called_once()

    def test_no_robot_candidate_does_not_close_manual_positions(self):
        runtime, store, close, inventory = fake_runtime(
            robot_symbols=(), remaining=(("MANUALUSDT", "1"),),
        )
        response = perform_close(runtime)
        self.assertEqual(len(response.results), 0)
        close.assert_not_called()
        inventory.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
