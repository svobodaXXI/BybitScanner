"""JASMY-like post-hoc reconciliation from immutable PAPER command/fill facts.

All data synthetic; no runtime/DB/Market calls or production credentials.
"""
import unittest
from unittest.mock import Mock
from decimal import Decimal
from types import SimpleNamespace

from terminal.application.robot_nonrobot_close_proof import prove_nonrobot_robot_close
from terminal.domain.models import (
    Category, Controller, Execution, ExecutionDedupKey,
    ExecutionId, OrderId, OrderSide, PositionKey, PositionSide, Price,
    Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.runtime.paper_runtime import PaperRuntime

ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("JASMYUSDT")
LINK = "tw_ce6b00000000000000000000000000000"
ENTRY_ORDER = "paper-limit-tw_c318-jasmy-identity"


def fill(exec_id, order, side, qty, price, fee, timestamp):
    return Execution(
        dedup_key=ExecutionDedupKey(ACCOUNT, Category.LINEAR, ExecutionId(exec_id)),
        order_id=OrderId(order), symbol=SYMBOL, side=side,
        quantity=Quantity(Decimal(qty)), price=Price(Decimal(price)),
        fee=Decimal(fee), exchange_timestamp_ms=timestamp,
    )


class NonRobotCloseProofTests(unittest.TestCase):
    def setUp(self):
        self.trade = SimpleNamespace(
            trade_id="robot-trade-2a023e646fd8add8b5b30cd8",
            candidate_id="2a023e646fd8add8b5b30cd8",
            trading_account_id=ACCOUNT, symbol=SYMBOL, direction="SHORT",
            pattern="Double Top", entry_quantity=Decimal("399"),
            entry_position_version=1, exit_time_ms=None,
            average_entry=Decimal("0.003792"),
            entry_time_ms=1793556278449,
        )
        self.candidate = SimpleNamespace(
            candidate_id=self.trade.candidate_id, symbol=SYMBOL, status="OPEN",
        )
        self.position = SimpleNamespace(
            position_key=PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0),
            side=PositionSide.FLAT, quantity=Quantity(Decimal("0")),
            sync_state="synced", version=2, updated_at_ms=1793556284508,
        )
        self.entry = fill(
            "paper-limit-05cf4f1", ENTRY_ORDER, OrderSide.SELL,
            "399", "0.003792", "0.0009078048", 1793556278449,
        )
        self.close = fill(
            "paper-exec-" + LINK, "paper-order-" + LINK, OrderSide.BUY,
            "399", "0.003794", "0.0009082836", 1793556284508,
        )
        self.command = SimpleNamespace(
            trading_account_id=ACCOUNT, category=Category.LINEAR,
            symbol=SYMBOL, position_idx=0, controller=Controller.MANUAL,
            command_kind="create_market", current_state=CommandState.FILLED,
            exchange_order_id=self.close.order_id,
            normalized_quantity=Quantity(Decimal("399")),
            order_link_id=LINK, side=OrderSide.BUY,
        )

    def prove(self, **overrides):
        kwargs = dict(
            trade=self.trade, candidate=self.candidate, position=self.position,
            executions=(self.entry, self.close), command=self.command,
            entry_order_ids=(ENTRY_ORDER,), entry_fees=Decimal("0.0009078048"),
            unique_open_owner=True, has_competing_work=False,
        )
        kwargs.update(overrides)
        return prove_nonrobot_robot_close(**kwargs)

    def test_jasmy_exact_fill_reconstructs_truthful_manual_economics(self):
        result = self.prove()
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_time_ms, 1793556284508)
        self.assertEqual(result.exit_price, Decimal("0.003794"))
        self.assertEqual(result.realized_pnl_usdt, Decimal("-0.000798"))
        self.assertEqual(result.fees_costs_usdt, Decimal("0.0018160884"))
        expected_pct = (
            Decimal("-0.000798") - Decimal("0.0018160884")
        ) / (Decimal("399") * Decimal("0.003792")) * 100
        self.assertEqual(result.realized_pnl_pct, expected_pct)

    def test_owner_reconcile_finalizes_only_proven_existing_execution(self):
        trade = SimpleNamespace(**{
            **vars(self.trade), "entry_path": "LIMIT", "created_at_ms": 1793556278449,
        })
        candidate = SimpleNamespace(**{
            **vars(self.candidate), "updated_at_ms": 1793556278449,
            "robot_state": {"execution": {"limit_order_id": ENTRY_ORDER}},
        })
        store = SimpleNamespace(
            load_robot_candidates_for_symbol=Mock(return_value=(candidate,)),
            load_open_robot_trades=Mock(return_value=(trade,)),
            load_active_paper_limits=Mock(return_value=()),
            load_unresolved_paper_protection_obligations=Mock(return_value=()),
            load_unfinished_commands=Mock(return_value=()),
            load_executions_for_symbol=Mock(return_value=(self.entry, self.close)),
            get_paper_command_by_order_link=Mock(return_value=self.command),
            close_robot_trade=Mock(),
            clear_paper_protection_for_flat=Mock(),
        )
        owner = SimpleNamespace(
            _paper_account_id=ACCOUNT, store=store,
            _robot_entry_fees=lambda candidate_trade: Decimal("0.0009078048"),
        )
        self.assertTrue(PaperRuntime._robot_finalize_nonrobot_close(
            owner, candidate, trade, self.position,
        ))
        kwargs = store.close_robot_trade.call_args.kwargs
        self.assertEqual(kwargs["exit_reason"], "MANUAL")
        self.assertEqual(kwargs["realized_pnl_usdt"], Decimal("-0.000798"))
        self.assertEqual(kwargs["fees_costs_usdt"], Decimal("0.0018160884"))
        self.assertEqual(store.get_paper_command_by_order_link.call_args.args, (ACCOUNT, LINK))
        store.clear_paper_protection_for_flat.assert_called_once()

        store.close_robot_trade.reset_mock()
        store.clear_paper_protection_for_flat.reset_mock()
        store.get_paper_command_by_order_link.return_value = SimpleNamespace(
            **{**vars(self.command), "controller": Controller.ROBOT},
        )
        self.assertFalse(PaperRuntime._robot_finalize_nonrobot_close(
            owner, candidate, trade, self.position,
        ))
        store.close_robot_trade.assert_not_called()
        store.clear_paper_protection_for_flat.assert_not_called()

    def test_mismatch_is_never_a_proven_robot_close(self):
        cases = [
            {"command": SimpleNamespace(**{**vars(self.command), "order_link_id": "tw_" + "0"*33})},
            {"command": SimpleNamespace(**{**vars(self.command), "controller": Controller.ROBOT})},
            {"command": SimpleNamespace(**{**vars(self.command), "command_kind": "create_limit"})},
            {"command": SimpleNamespace(**{**vars(self.command), "current_state": CommandState.ACKNOWLEDGED})},
            {"command": SimpleNamespace(**{**vars(self.command), "side": OrderSide.SELL})},
            {"command": SimpleNamespace(**{**vars(self.command), "normalized_quantity": Quantity(Decimal("398"))})},
            {"position": SimpleNamespace(**{**vars(self.position), "version": 3})},
            {"position": SimpleNamespace(**{**vars(self.position), "updated_at_ms": 1793556284509})},
            {"position": SimpleNamespace(**{**vars(self.position), "sync_state": "reconciliation_required"})},
            {"executions": (self.entry, fill(self.close.dedup_key.exec_id.value, self.close.order_id.value,
                                             OrderSide.SELL, "399", "0.003794", "0.0009082836", 1793556284508))},
            {"executions": (self.entry, fill(self.close.dedup_key.exec_id.value, self.close.order_id.value,
                                             OrderSide.BUY, "398", "0.003794", "0.0009082836", 1793556284508))},
            {"executions": (self.entry, fill(self.close.dedup_key.exec_id.value, self.close.order_id.value,
                                             OrderSide.BUY, "399", "0.003794", "0.0009082836", 1793556278449))},
            {"entry_fees": Decimal("0")},
            {"unique_open_owner": False},
            {"has_competing_work": True},
            {"entry_order_ids": ("other-order",)},
            {"executions": (self.entry, fill("other-exec", "other", OrderSide.BUY,
                                             "1", "0.003795", "0.00001", 1793556280000), self.close)},
            {"trade": SimpleNamespace(**{**vars(self.trade), "pattern": "IKIGAI_BOX"})},
        ]
        for i, case in enumerate(cases):
            with self.subTest(case=i):
                self.assertIsNone(self.prove(**case))


if __name__ == "__main__":
    unittest.main()
