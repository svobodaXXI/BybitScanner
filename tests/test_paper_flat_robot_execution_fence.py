"""PAPER owner regression: net Flat must never conceal an OPEN Robot trade.

Pure mocked owner/store, no production DB, network, runtime or trading orders.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from terminal.domain.models import Category, PositionSide, Symbol, TradingAccountId
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("JASMYUSDT")


def _runtime(*, position_side=PositionSide.FLAT, quantity=0, status="READY", trade=True):
    store = SimpleNamespace(
        get_open_robot_trade_for_symbol=Mock(return_value=(
            SimpleNamespace(trade_id="robot-trade-JASMY") if trade else None
        )),
        get_position_projection=Mock(return_value=SimpleNamespace(
            side=position_side, quantity=SimpleNamespace(value=quantity),
        )),
        get_robot_runtime_state=Mock(return_value=SimpleNamespace(
            mode="ROBOT_RUNNING", recovery_status=status, version=81,
            updated_at_ms=1000,
        )),
        update_robot_runtime_state=Mock(),
    )
    owner = SimpleNamespace(_paper_account_id=ACCOUNT, store=store)
    return owner, store


class FlatRobotLedgerFenceTests(unittest.TestCase):
    def test_flat_with_open_trade_fences_ready_without_orders_or_closure(self):
        owner, store = _runtime()
        PaperRuntime._fence_flat_robot_ledger_after_paper_execution(owner, SYMBOL)
        store.update_robot_runtime_state.assert_called_once()
        args = store.update_robot_runtime_state.call_args
        self.assertEqual(args.kwargs["recovery_status"], "RECONCILIATION_REQUIRED")
        self.assertIn("robot-trade-JASMY", args.kwargs["reason"])
        self.assertEqual(args.kwargs["expected_version"], 81)
        self.assertEqual(store.get_open_robot_trade_for_symbol.call_args.args, (ACCOUNT, SYMBOL))
        position_key = store.get_position_projection.call_args.args[0]
        self.assertEqual(position_key.symbol, SYMBOL)
        self.assertEqual(position_key.category, Category.LINEAR)

    def test_symbol_string_normalizes_before_owner_lookup(self):
        owner, store = _runtime()
        PaperRuntime._fence_flat_robot_ledger_after_paper_execution(owner, "JASMYUSDT")
        store.get_open_robot_trade_for_symbol.assert_called_once_with(ACCOUNT, SYMBOL)
        store.update_robot_runtime_state.assert_called_once()

    def test_nonflat_and_no_open_trade_do_not_fence(self):
        for overrides in (
            {"position_side": PositionSide.SHORT, "quantity": 399},
            {"trade": False},
            {"status": "RECONCILIATION_REQUIRED"},
            {"status": "RECONCILING"},
        ):
            with self.subTest(overrides=overrides):
                owner, store = _runtime(**overrides)
                PaperRuntime._fence_flat_robot_ledger_after_paper_execution(owner, SYMBOL)
                store.update_robot_runtime_state.assert_not_called()

    def test_both_generic_paper_execution_paths_apply_same_fence(self):
        for method in ("market", "full_close"):
            with self.subTest(method=method):
                calls = []
                request = SimpleNamespace(symbol=SYMBOL)
                owner = SimpleNamespace(
                    require_paper_mutations=lambda: calls.append("paper_only"),
                    _robot_execution_book=lambda symbol, evidence: "book",
                    api=SimpleNamespace(**{method: Mock(return_value="done")}),
                    _fence_flat_robot_ledger_after_paper_execution=lambda symbol: calls.append(("fence", symbol)),
                )
                result = getattr(PaperRuntime, method)(owner, request)
                self.assertEqual(result, "done")
                self.assertEqual(calls, ["paper_only", ("fence", SYMBOL)])
                getattr(owner.api, method).assert_called_once()

    def test_mutation_failure_does_not_trigger_false_flat_fence(self):
        request = SimpleNamespace(symbol=SYMBOL)
        owner = SimpleNamespace(
            require_paper_mutations=lambda: None,
            _robot_execution_book=lambda symbol, evidence: "book",
            api=SimpleNamespace(market=Mock(side_effect=ValueError("rejected"))),
            _fence_flat_robot_ledger_after_paper_execution=Mock(),
        )
        with self.assertRaisesRegex(ValueError, "rejected"):
            PaperRuntime.market(owner, request)
        owner._fence_flat_robot_ledger_after_paper_execution.assert_not_called()


if __name__ == "__main__":
    unittest.main()
