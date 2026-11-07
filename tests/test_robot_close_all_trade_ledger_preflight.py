"""Robot Close-All requires durable OPEN candidate <-> open trade agreement.

No real database, HTTP backend, exchange, order or runtime process.
"""

from __future__ import annotations

from types import SimpleNamespace
import unittest

from terminal.api.models import CommandResultStatus
from terminal.domain.models import Symbol
from tests.test_robot_close_all_residual_proof import fake_runtime, perform_close


def trade(candidate_id, symbol="BOTUSDT", trade_id=None):
    return SimpleNamespace(
        trade_id=trade_id or f"trade-{candidate_id}",
        candidate_id=candidate_id,
        symbol=Symbol(symbol),
    )


class RobotCloseAllTradeLedgerPreflightTests(unittest.TestCase):
    def assert_blocked(self, runtime, store, close):
        result = perform_close(runtime)
        self.assertTrue(result.results)
        self.assertTrue(all(
            item.status is CommandResultStatus.UNAVAILABLE
            and item.reason_code == "robot_trade_ownership_unproven"
            and item.reconciliation_required
            for item in result.results
        ))
        close.assert_not_called()
        runtime._robot_close_box_candidate.assert_not_called()
        store.update_robot_runtime_state.assert_called_once()
        self.assertEqual(
            store.update_robot_runtime_state.call_args.kwargs["recovery_status"],
            "RECONCILIATION_REQUIRED",
        )
        return result

    def test_matching_durable_trade_keeps_original_close_path(self):
        runtime, store, close, inventory = fake_runtime()
        result = perform_close(runtime)
        self.assertEqual(result.results[0].status, CommandResultStatus.COMPLETED)
        close.assert_called_once()
        inventory.assert_called_once()
        store.update_robot_runtime_state.assert_not_called()

    def test_open_candidate_without_robot_trade_is_fenced(self):
        runtime, store, close, _ = fake_runtime()
        store.load_open_robot_trades.return_value = ()
        self.assert_blocked(runtime, store, close)

    def test_open_trade_without_open_candidate_is_reported_not_noop(self):
        runtime, store, close, _ = fake_runtime(robot_symbols=())
        store.load_open_robot_trades.return_value = (
            trade("orphan", trade_id="orphan-trade-id"),
        )
        result = self.assert_blocked(runtime, store, close)
        self.assertEqual(len(result.results), 1)

    def test_orphan_trade_blocks_otherwise_valid_close_in_same_batch(self):
        runtime, store, close, _ = fake_runtime()
        own = store.load_open_robot_trades.return_value[0]
        store.load_open_robot_trades.return_value = (
            own, trade("orphan", "OTHERUSDT"),
        )
        result = self.assert_blocked(runtime, store, close)
        self.assertEqual(len(result.results), 2)

    def test_duplicate_open_trades_for_one_candidate_are_fenced(self):
        runtime, store, close, _ = fake_runtime()
        own = store.load_open_robot_trades.return_value[0]
        store.load_open_robot_trades.return_value = (
            own, trade(own.candidate_id, trade_id="duplicate-trade"),
        )
        self.assert_blocked(runtime, store, close)

    def test_wrong_symbol_for_correct_candidate_is_fenced(self):
        runtime, store, close, _ = fake_runtime()
        own = store.load_open_robot_trades.return_value[0]
        store.load_open_robot_trades.return_value = (
            trade(own.candidate_id, "OTHERUSDT"),
        )
        self.assert_blocked(runtime, store, close)

    def test_missing_ledger_read_is_fenced(self):
        runtime, store, close, _ = fake_runtime()
        store.load_open_robot_trades.side_effect = LookupError("ledger unavailable")
        self.assert_blocked(runtime, store, close)

    def test_missing_ledger_read_with_no_candidates_is_not_reported_as_success(self):
        runtime, store, close, _ = fake_runtime(robot_symbols=())
        store.load_open_robot_trades.side_effect = LookupError("ledger unavailable")
        result = self.assert_blocked(runtime, store, close)
        self.assertEqual(len(result.results), 1)

    def test_box_close_does_not_dispatch_without_matching_trade(self):
        runtime, store, close, _ = fake_runtime()
        store.load_robot_candidates_by_status.return_value[0].signal_snapshot["pattern"] = "IKIGAI_BOX"
        store.load_open_robot_trades.return_value = ()
        self.assert_blocked(runtime, store, close)

    def test_clean_empty_ledger_preserves_existing_noop(self):
        runtime, store, close, inventory = fake_runtime(robot_symbols=())
        result = perform_close(runtime)
        self.assertEqual(result.results, ())
        close.assert_not_called()
        store.update_robot_runtime_state.assert_not_called()
        inventory.assert_called_once()


if __name__ == "__main__":
    unittest.main()
