import ast
import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path

from terminal.domain.events import (
    ExchangeAcknowledgement,
    ExecutionEvidence,
    PositionSnapshotEvidence,
)
from terminal.domain.models import (
    Category,
    CommandId,
    Controller,
    Execution,
    ExecutionDedupKey,
    ExecutionId,
    Notional,
    OrderId,
    OrderSide,
    Origin,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
    TradingCommand,
)
from terminal.domain.policies import (
    TradingAction,
    cap_market_quantity_at_flat,
    permission_for,
    retry_requires_reconciliation,
)
from terminal.domain.states import (
    CommandState,
    ConnectivityState,
    InvalidStateTransition,
    OrderState,
    transition_command,
    transition_order,
)


class TerminalValueObjectTests(unittest.TestCase):
    def test_identity_objects_are_deterministic(self):
        self.assertEqual(CommandId("command-1"), CommandId("command-1"))
        self.assertNotEqual(CommandId("command-1"), CommandId("command-2"))
        self.assertEqual(Symbol("btcusdt"), Symbol("BTCUSDT"))

    def test_decimal_values_are_preserved_exactly(self):
        value = Decimal("0.100000000000000001")
        self.assertEqual(Price(value).value, value)
        self.assertEqual(Quantity(value).value, value)
        self.assertEqual(Notional(value).value, value)
        with self.assertRaises(TypeError):
            Price(0.1)  # type: ignore[arg-type]

    def test_position_key_requires_linear_one_way_mode(self):
        account = TradingAccountId("manual")
        key = PositionKey(account, Category.LINEAR, Symbol("BTCUSDT"), 0)
        self.assertEqual(
            key,
            PositionKey(account, Category.LINEAR, Symbol("BTCUSDT"), 0),
        )
        with self.assertRaisesRegex(ValueError, "position_idx=0"):
            PositionKey(account, Category.LINEAR, Symbol("BTCUSDT"), 1)

    def test_execution_dedup_identity_uses_account_category_and_exec_id(self):
        account = TradingAccountId("manual")
        first = ExecutionDedupKey(account, Category.LINEAR, ExecutionId("exec-1"))
        duplicate = ExecutionDedupKey(account, Category.LINEAR, ExecutionId("exec-1"))
        other_account = ExecutionDedupKey(
            TradingAccountId("other"), Category.LINEAR, ExecutionId("exec-1")
        )
        self.assertEqual(first, duplicate)
        self.assertNotEqual(first, other_account)

    def test_origin_and_controller_are_independent(self):
        command = TradingCommand(
            CommandId("takeover-command"),
            TradingAccountId("manual"),
            Symbol("BTCUSDT"),
            OrderSide.SELL,
            Origin.EXTERNAL,
            Controller.MANUAL,
        )
        self.assertIs(command.origin, Origin.EXTERNAL)
        self.assertIs(command.controller, Controller.MANUAL)


class TerminalStateTransitionTests(unittest.TestCase):
    def test_valid_command_progression(self):
        state = transition_command(CommandState.LOCAL_INTENT, CommandState.ADMITTED)
        state = transition_command(state, CommandState.SUBMITTING)
        state = transition_command(state, CommandState.ACKNOWLEDGED)
        state = transition_command(state, CommandState.OPEN)
        state = transition_command(state, CommandState.PARTIALLY_FILLED)
        self.assertIs(transition_command(state, CommandState.FILLED), CommandState.FILLED)

    def test_valid_cancel_fill_race(self):
        self.assertIs(
            transition_order(OrderState.CANCEL_PENDING, OrderState.FILLED),
            OrderState.FILLED,
        )
        self.assertIs(
            transition_order(OrderState.CANCEL_PENDING, OrderState.CANCELLED),
            OrderState.CANCELLED,
        )

    def test_confirmed_amend_has_distinct_terminal_completion(self):
        state = transition_command(CommandState.LOCAL_INTENT, CommandState.ADMITTED)
        state = transition_command(state, CommandState.SUBMITTING)
        acknowledgement = transition_command(state, CommandState.ACKNOWLEDGED)
        self.assertIs(acknowledgement, CommandState.ACKNOWLEDGED)
        self.assertIsNot(acknowledgement, CommandState.AMENDED)
        completed = transition_command(acknowledgement, CommandState.AMENDED)
        self.assertIs(completed, CommandState.AMENDED)
        self.assertIsNot(completed, CommandState.FILLED)
        with self.assertRaises(InvalidStateTransition):
            transition_command(completed, CommandState.OPEN)

    def test_ambiguous_amend_can_reconcile_to_completion(self):
        self.assertIs(
            transition_command(CommandState.SUBMITTING, CommandState.UNKNOWN),
            CommandState.UNKNOWN,
        )
        self.assertIs(
            transition_command(CommandState.UNKNOWN, CommandState.RECONCILING),
            CommandState.RECONCILING,
        )
        self.assertIs(
            transition_command(CommandState.RECONCILING, CommandState.AMENDED),
            CommandState.AMENDED,
        )

    def test_amend_completion_does_not_change_exchange_order_state(self):
        self.assertIs(
            transition_order(OrderState.OPEN, OrderState.AMEND_PENDING),
            OrderState.AMEND_PENDING,
        )
        self.assertIs(
            transition_order(OrderState.AMEND_PENDING, OrderState.OPEN),
            OrderState.OPEN,
        )

    def test_terminal_and_regressive_transitions_are_rejected(self):
        with self.assertRaises(InvalidStateTransition):
            transition_command(CommandState.FILLED, CommandState.OPEN)
        with self.assertRaises(InvalidStateTransition):
            transition_order(OrderState.FILLED, OrderState.PARTIALLY_FILLED_OPEN)
        with self.assertRaises(InvalidStateTransition):
            transition_order(OrderState.PARTIALLY_FILLED_OPEN, OrderState.OPEN)
        with self.assertRaises(InvalidStateTransition):
            transition_order(OrderState.CANCEL_PENDING, OrderState.PARTIALLY_FILLED_OPEN)


class TerminalEvidenceTests(unittest.TestCase):
    def _execution(self) -> Execution:
        return Execution(
            ExecutionDedupKey(
                TradingAccountId("manual"),
                Category.LINEAR,
                ExecutionId("exec-1"),
            ),
            OrderId("order-1"),
            Symbol("BTCUSDT"),
            OrderSide.BUY,
            Price(Decimal("65000.25")),
            Quantity(Decimal("0.001")),
            Decimal("0.01"),
            123456789,
        )

    def test_acknowledgement_is_not_execution_evidence(self):
        ack = ExchangeAcknowledgement(CommandId("command-1"), True, OrderId("order-1"))
        self.assertNotIsInstance(ack, ExecutionEvidence)
        self.assertFalse(hasattr(ack, "execution"))

    def test_position_snapshot_is_not_execution_evidence(self):
        snapshot = PositionSnapshotEvidence(
            PositionKey(
                TradingAccountId("manual"), Category.LINEAR, Symbol("BTCUSDT"), 0
            ),
            PositionSide.LONG,
            Quantity(Decimal("0.001")),
        )
        self.assertNotIsInstance(snapshot, ExecutionEvidence)

    def test_execution_is_immutable_and_duplicate_identity_is_stable(self):
        execution = self._execution()
        duplicate = self._execution()
        self.assertEqual(execution.dedup_key, duplicate.dedup_key)
        with self.assertRaises(FrozenInstanceError):
            execution.fee = Decimal("9")  # type: ignore[misc]

    def test_execution_fee_preserves_negative_rebate(self):
        execution = self._execution()
        rebate = Execution(
            execution.dedup_key,
            execution.order_id,
            execution.symbol,
            execution.side,
            execution.price,
            execution.quantity,
            Decimal("-0.005"),
            execution.exchange_timestamp_ms,
        )
        self.assertEqual(rebate.fee, Decimal("-0.005"))


class TerminalPolicyTests(unittest.TestCase):
    def test_online_allows_normal_actions(self):
        for action in TradingAction:
            self.assertTrue(permission_for(ConnectivityState.ONLINE, action).allowed)

    def test_non_online_states_block_new_exposure(self):
        for state in (
            ConnectivityState.DEGRADED,
            ConnectivityState.UNKNOWN_EXECUTION,
            ConnectivityState.RECONCILING,
            ConnectivityState.OFFLINE,
        ):
            self.assertFalse(permission_for(state, TradingAction.NEW_ENTRY).allowed)
            self.assertFalse(permission_for(state, TradingAction.SCALE_IN).allowed)
            self.assertFalse(permission_for(state, TradingAction.NEW_LIMIT).allowed)

    def test_bounded_reduction_and_cancel_are_allowed_except_offline(self):
        for state in (
            ConnectivityState.DEGRADED,
            ConnectivityState.UNKNOWN_EXECUTION,
            ConnectivityState.RECONCILING,
        ):
            self.assertTrue(
                permission_for(state, TradingAction.EMERGENCY_CLOSE, safely_bounded=True).allowed
            )
            self.assertTrue(
                permission_for(state, TradingAction.CANCEL, safely_bounded=True).allowed
            )
        self.assertFalse(
            permission_for(
                ConnectivityState.OFFLINE,
                TradingAction.EMERGENCY_CLOSE,
                safely_bounded=True,
            ).allowed
        )

    def test_unknown_and_submitted_commands_require_reconciliation_not_retry(self):
        self.assertTrue(retry_requires_reconciliation(CommandState.UNKNOWN))
        self.assertTrue(retry_requires_reconciliation(CommandState.SUBMITTING))
        self.assertFalse(retry_requires_reconciliation(CommandState.FAILED))

    def test_opposite_market_quantity_is_capped_at_flat(self):
        decision = cap_market_quantity_at_flat(
            Quantity(Decimal("5")),
            OrderSide.SELL,
            PositionSide.LONG,
            Quantity(Decimal("2")),
        )
        self.assertEqual(decision.submitted_quantity.value, Decimal("2"))
        self.assertTrue(decision.capped_at_flat)

    def test_same_direction_and_flat_market_quantity_are_not_capped(self):
        same_side = cap_market_quantity_at_flat(
            Quantity(Decimal("5")),
            OrderSide.BUY,
            PositionSide.LONG,
            Quantity(Decimal("2")),
        )
        from_flat = cap_market_quantity_at_flat(
            Quantity(Decimal("5")),
            OrderSide.SELL,
            PositionSide.FLAT,
            Quantity(Decimal("0")),
        )
        self.assertEqual(same_side.submitted_quantity.value, Decimal("5"))
        self.assertEqual(from_flat.submitted_quantity.value, Decimal("5"))


class TerminalDependencyBoundaryTests(unittest.TestCase):
    def test_domain_has_no_transport_database_ui_or_scanner_imports(self):
        root = Path(__file__).parents[1] / "terminal" / "domain"
        forbidden = {
            "pybit",
            "requests",
            "websocket",
            "sqlite3",
            "fastapi",
            "flask",
            "main",
            "scanner",
            "analyzer",
            "bybit_api",
            "notification",
            "telegram_bot",
        }
        imported = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)


if __name__ == "__main__":
    unittest.main()
