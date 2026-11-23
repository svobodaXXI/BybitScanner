"""PAPER owner regression: net Flat must never conceal an OPEN Robot trade.

Pure mocked owner/store, no production DB, network, runtime or trading orders.
"""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from terminal.domain.models import Category, PositionSide, Symbol, TradingAccountId
from terminal.persistence.sqlite_store import ExecutionApplyResult
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
                    _paper_account_id=ACCOUNT,
                    store=SimpleNamespace(
                        robot_symbol_quarantine_candidate_ids=Mock(return_value=()),
                    ),
                    require_paper_mutations=lambda: calls.append("paper_only"),
                    _robot_execution_book=lambda symbol, evidence: "book",
                    api=SimpleNamespace(**{method: Mock(return_value="done")}),
                    _fence_flat_robot_ledger_after_paper_execution=lambda symbol: calls.append(("fence", symbol)),
                )
                result = getattr(PaperRuntime, method)(owner, request)
                self.assertEqual(result, "done")
                self.assertEqual(calls, ["paper_only", ("fence", SYMBOL)])
                getattr(owner.api, method).assert_called_once()

    def test_quarantined_manual_market_does_not_dispatch_or_claim_flat(self):
        request = SimpleNamespace(
            symbol=SYMBOL,
            client_action_id=SimpleNamespace(value="manual-quarantined-test"),
        )
        store = SimpleNamespace(
            robot_symbol_quarantine_candidate_ids=Mock(return_value=("blocked-a",)),
        )
        owner = SimpleNamespace(
            _paper_account_id=ACCOUNT, store=store,
            require_paper_mutations=lambda: None,
            api=SimpleNamespace(market=Mock()),
            _robot_execution_book=Mock(),
            _fence_flat_robot_ledger_after_paper_execution=Mock(),
        )
        result = PaperRuntime.market(owner, request)
        self.assertEqual(result.status.value, "blocked")
        self.assertEqual(result.reason_code, "robot_symbol_quarantined")
        owner.api.market.assert_not_called()
        owner._robot_execution_book.assert_not_called()
        owner._fence_flat_robot_ledger_after_paper_execution.assert_not_called()
        store.robot_symbol_quarantine_candidate_ids.assert_called_once_with(ACCOUNT, SYMBOL)

    def test_limit_matching_keeps_only_owned_box_exit_when_a_is_quarantined(self):
        """The already-working manual A LIMIT cannot fill; proven EXIT keeps working."""
        manual = SimpleNamespace(order_id=SimpleNamespace(value="manual-a"))
        robot_entry = SimpleNamespace(order_id=SimpleNamespace(value="robot-entry-a"))
        box_exit = SimpleNamespace(order_id=SimpleNamespace(value="box-exit-a"))
        store = SimpleNamespace(
            load_active_paper_limits=Mock(return_value=(manual, robot_entry, box_exit)),
            robot_symbol_quarantine_candidate_ids=Mock(return_value=("box-a",)),
            load_active_box_exit_limit_ids=Mock(return_value=frozenset({"box-exit-a"})),
        )
        execution = Mock(return_value=SimpleNamespace(
            apply_result=ExecutionApplyResult.APPLIED,
        ))
        owner = SimpleNamespace(
            _account_id=ACCOUNT, _paper_account_id=ACCOUNT, store=store,
            _robot_entry_limit_ids_fenced_by_admission=Mock(return_value=frozenset()),
            _limit_executor=SimpleNamespace(execute=execution),
        )
        applied = PaperRuntime._match_limits_only(
            owner, SYMBOL, object(), "quarantined-a-event",
        )
        self.assertEqual(applied, 1)
        self.assertEqual(execution.call_count, 1)
        self.assertIs(execution.call_args.kwargs["order"], box_exit)
        store.load_active_box_exit_limit_ids.assert_called_once_with(ACCOUNT, SYMBOL)

        # Missing exact ownership may never become a generic permission.
        store.load_active_box_exit_limit_ids.return_value = frozenset()
        execution.reset_mock()
        self.assertEqual(PaperRuntime._match_limits_only(
            owner, SYMBOL, object(), "unproven-a-event",
        ), 0)
        execution.assert_not_called()

    def test_mutation_failure_does_not_trigger_false_flat_fence(self):
        request = SimpleNamespace(symbol=SYMBOL)
        owner = SimpleNamespace(
            _paper_account_id=ACCOUNT,
            store=SimpleNamespace(
                robot_symbol_quarantine_candidate_ids=Mock(return_value=()),
            ),
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
