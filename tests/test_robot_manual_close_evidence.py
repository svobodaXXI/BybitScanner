"""Non-Box Robot Close-All durable-intent and exact PAPER fill tests.

Pure/synthetic owner + store: zero real database, HTTP, exchange or runtime.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from terminal.api.models import ClientActionId, FullCloseCommandRequest
from terminal.application.command_identity import CommandIdentityCandidate
from terminal.application.robot_manual_close_proof import prove_robot_manual_close
from terminal.domain.models import (
    Category, CommandId, Execution, ExecutionDedupKey, ExecutionId, OrderId,
    OrderSide, PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.runtime.paper_runtime import PaperRuntime


ACCOUNT = TradingAccountId("paper")
SYMBOL = Symbol("BOTUSDT")
LINK = "tw_" + "a" * 32 + "0"


def trade():
    return SimpleNamespace(
        trade_id="trade-one", candidate_id="candidate-one",
        trading_account_id=ACCOUNT, symbol=SYMBOL, direction="LONG",
        pattern="Falling Wedge", entry_time_ms=100,
        entry_quantity=Decimal("2"), entry_position_version=3,
        average_entry=Decimal("10"), exit_time_ms=None,
        created_at_ms=90,
    )


def candidate(intent=True):
    data = {
        "trade_id": "trade-one", "candidate_id": "candidate-one",
        "symbol": "BOTUSDT", "entry_quantity": "2",
        "entry_position_version": 3,
        "client_action_id": "robot-close-all-first",
        "command_id": "cmd_" + "a" * 32,
        "order_link_id": LINK,
    }
    return SimpleNamespace(
        candidate_id="candidate-one", symbol=SYMBOL, status="OPEN",
        state_revision=1, robot_state={"phase": "OPEN", "execution": (
            {"robot_close_all_manual_intent": data} if intent else {}
        )},
    )


def position(flat=True):
    return SimpleNamespace(
        position_key=SimpleNamespace(
            trading_account_id=ACCOUNT, symbol=SYMBOL,
            category=Category.LINEAR, position_idx=0,
        ),
        side=PositionSide.FLAT if flat else PositionSide.LONG,
        quantity=Quantity(Decimal("0" if flat else "2")),
        version=4 if flat else 3, updated_at_ms=150 if flat else 110,
    )


def fill():
    return Execution(
        dedup_key=ExecutionDedupKey(
            ACCOUNT, Category.LINEAR, ExecutionId("paper-exec-" + LINK),
        ),
        order_id=OrderId("paper-order-" + LINK),
        symbol=SYMBOL, side=OrderSide.SELL,
        price=Price(Decimal("12")), quantity=Quantity(Decimal("2")),
        fee=Decimal("0.03"), exchange_timestamp_ms=150,
    )


def proof(**overrides):
    values = dict(trade=trade(), candidate=candidate(), position=position(),
                  fill=fill(), entry_fees=Decimal("0.02"))
    values.update(overrides)
    return prove_robot_manual_close(**values)


class RobotManualCloseEvidenceTests(unittest.TestCase):
    def test_exact_flat_market_fill_proves_realized_economics(self):
        result = proof()
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_time_ms, 150)
        self.assertEqual(result.exit_price, Decimal("12"))
        self.assertEqual(result.realized_pnl_usdt, Decimal("4"))
        self.assertEqual(result.fees_costs_usdt, Decimal("0.05"))
        self.assertEqual(result.realized_pnl_pct, Decimal("19.75"))

    def test_unknown_entry_fees_are_never_invented(self):
        self.assertIsNone(proof(entry_fees=None))

    def test_nonflat_or_stale_projection_is_not_close_proof(self):
        self.assertIsNone(proof(position=position(flat=False)))
        stale = position()
        stale.updated_at_ms = 149
        self.assertIsNone(proof(position=stale))

    def test_extra_position_execution_does_not_prove_manual_flat(self):
        ambiguous = position()
        ambiguous.version += 1
        self.assertIsNone(proof(position=ambiguous))

    def test_exec_id_and_order_id_must_match_first_durable_intent(self):
        bad = candidate()
        bad.robot_state["execution"]["robot_close_all_manual_intent"]["order_link_id"] = (
            "tw_" + "b" * 32 + "0"
        )
        self.assertIsNone(proof(candidate=bad))
        wrong_order = replace(fill(), order_id=OrderId("wrong-order"))
        self.assertIsNone(proof(fill=wrong_order))

    def test_neither_partial_fill_nor_mismatched_side_can_finalize(self):
        bad_fill = replace(fill(), quantity=Quantity(Decimal("1")))
        self.assertIsNone(proof(fill=bad_fill))
        opposite = replace(fill(), side=OrderSide.BUY)
        self.assertIsNone(proof(fill=opposite))

    def test_trade_owner_and_frozen_entry_quantity_must_match(self):
        bad = trade()
        bad.candidate_id = "other-candidate"
        self.assertIsNone(proof(trade=bad))
        bad2 = candidate()
        bad2.robot_state["execution"]["robot_close_all_manual_intent"]["entry_quantity"] = "3"
        self.assertIsNone(proof(candidate=bad2))


class RobotManualCloseRecoveryTests(unittest.TestCase):
    def test_first_close_persists_intent_and_new_confirmation_reuses_it(self):
        t = trade()
        c = candidate(intent=False)
        store = SimpleNamespace(
            get_open_robot_trade_for_symbol=Mock(return_value=t),
            get_robot_candidate=Mock(return_value=c),
            get_position_projection=Mock(return_value=position(flat=False)),
            save_robot_candidate_state=Mock(),
        )
        def save(candidate_id, *, status, robot_state, expected_revision, updated_at_ms):
            c.robot_state = robot_state
            c.state_revision += 1
            return c
        store.save_robot_candidate_state.side_effect = save
        runtime = SimpleNamespace(_paper_account_id=ACCOUNT, store=store)
        first = FullCloseCommandRequest(ClientActionId("robot-close-all-first"), "BOTUSDT")
        one = CommandIdentityCandidate(CommandId("cmd_" + "a" * 32), LINK)
        prepared = PaperRuntime._robot_prepare_manual_close(runtime, c, first, one)
        self.assertEqual(prepared, (first, one))
        store.save_robot_candidate_state.assert_called_once()
        second = FullCloseCommandRequest(ClientActionId("robot-close-all-new-tap"), "BOTUSDT")
        two = CommandIdentityCandidate(CommandId("cmd_" + "b" * 32), "tw_" + "b" * 32 + "0")
        replay = PaperRuntime._robot_prepare_manual_close(runtime, c, second, two)
        self.assertEqual(replay, (first, one))
        store.save_robot_candidate_state.assert_called_once()

    def test_missing_attested_position_never_persists_or_dispatches(self):
        c = candidate(intent=False)
        store = SimpleNamespace(
            get_open_robot_trade_for_symbol=Mock(return_value=trade()),
            get_robot_candidate=Mock(return_value=c),
            get_position_projection=Mock(return_value=position(flat=True)),
            save_robot_candidate_state=Mock(),
        )
        runtime = SimpleNamespace(_paper_account_id=ACCOUNT, store=store)
        with self.assertRaisesRegex(RuntimeError, "position attestation"):
            PaperRuntime._robot_prepare_manual_close(
                runtime, c,
                FullCloseCommandRequest(ClientActionId("first"), "BOTUSDT"),
                CommandIdentityCandidate(CommandId("cmd_" + "a" * 32), LINK),
            )
        store.save_robot_candidate_state.assert_not_called()

    def test_restart_finalizes_exact_fill_without_new_market_dispatch(self):
        c = candidate()
        store = SimpleNamespace(
            get_robot_candidate=Mock(return_value=c),
            get_open_robot_trade_for_symbol=Mock(return_value=trade()),
            get_position_projection=Mock(return_value=position()),
            get_execution=Mock(return_value=fill()),
            close_robot_trade=Mock(),
            clear_paper_protection_for_flat=Mock(),
        )
        runtime = SimpleNamespace(
            _paper_account_id=ACCOUNT, store=store,
            _robot_entry_fees=Mock(return_value=Decimal("0.02")),
            _robot_full_close=Mock(),
        )
        self.assertTrue(PaperRuntime._robot_finalize_manual_close(runtime, c))
        store.close_robot_trade.assert_called_once()
        arguments = store.close_robot_trade.call_args
        self.assertEqual(arguments.kwargs["exit_reason"], "MANUAL")
        self.assertEqual(arguments.kwargs["realized_pnl_usdt"], Decimal("4"))
        self.assertEqual(arguments.kwargs["fees_costs_usdt"], Decimal("0.05"))
        self.assertEqual(arguments.kwargs["realized_pnl_pct"], Decimal("19.75"))
        store.clear_paper_protection_for_flat.assert_called_once()
        runtime._robot_full_close.assert_not_called()

    def test_missing_fill_does_not_finalize_or_clear_protection(self):
        c = candidate()
        store = SimpleNamespace(
            get_robot_candidate=Mock(return_value=c),
            get_open_robot_trade_for_symbol=Mock(return_value=trade()),
            get_position_projection=Mock(return_value=position()),
            get_execution=Mock(return_value=None),
            close_robot_trade=Mock(),
            clear_paper_protection_for_flat=Mock(),
        )
        runtime = SimpleNamespace(
            _paper_account_id=ACCOUNT, store=store,
            _robot_entry_fees=Mock(return_value=Decimal("0.02")),
        )
        self.assertFalse(PaperRuntime._robot_finalize_manual_close(runtime, c))
        store.close_robot_trade.assert_not_called()
        store.clear_paper_protection_for_flat.assert_not_called()


if __name__ == "__main__":
    unittest.main()
