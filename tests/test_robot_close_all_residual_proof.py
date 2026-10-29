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
from terminal.domain.models import Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT = TradingAccountId("paper")


def fake_runtime(*, robot_symbols=("BOTUSDT",), remaining=(),
                 status=CommandResultStatus.COMPLETED, inventory_error=None):
    candidates = [
        SimpleNamespace(
            candidate_id=f"candidate-{i}-{symbol}",
            symbol=Symbol(symbol),
            status="OPEN",
            robot_state={},
            signal_snapshot={"pattern": "Falling Wedge"},
        )
        for i, symbol in enumerate(robot_symbols)
    ]
    store = SimpleNamespace(
        load_robot_candidates_by_status=Mock(return_value=candidates),
        load_open_robot_trades=Mock(return_value=tuple(
            SimpleNamespace(
                trade_id=f"trade-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                symbol=candidate.symbol,
            )
            for candidate in candidates
        )),
        load_active_robot_candidate_states=Mock(return_value=candidates),
        load_active_robot_entry_orders=Mock(return_value={}),
        load_unresolved_paper_protection_obligations=Mock(return_value=()),
        load_active_paper_limits=Mock(return_value=()),
        get_robot_runtime_state=Mock(return_value=SimpleNamespace(
            mode="ROBOT_RUNNING", recovery_status="READY", version=7,
        )),
        update_robot_runtime_state=Mock(),
        # CR-ROBOT-CLOSE-ALL-MAX-QTY-001: robot_close_all() re-reads the
        # position after a COMPLETED chunk to decide whether to submit
        # another one. Already flat here, so it stops after the one chunk
        # these tests expect.
        get_position_projection=Mock(return_value=SimpleNamespace(
            quantity=SimpleNamespace(value=Decimal(0)),
        )),
    )
    close = Mock(side_effect=lambda request, *, identity=None: CommandResult(
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
        _robot_prepare_manual_close=Mock(side_effect=lambda candidate, request, identity, chunk_index=0: (
            request, identity,
        )),
        _instrument_provider=Mock(return_value=SimpleNamespace(
            max_market_order_quantity=Decimal("999999"), quantity_step=Decimal("0.0001"),
        )),
        _robot_finalize_manual_close=Mock(side_effect=lambda candidate: (
            close.call_count > 0
            and status == CommandResultStatus.COMPLETED
        )),
        _robot_linked_entry_limits=Mock(return_value={}),
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
        with self.assertRaisesRegex(LookupError, "inventory unavailable"):
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
