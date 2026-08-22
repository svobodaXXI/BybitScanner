import ast
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.domain.models import (
    Category,
    CommandId,
    Controller,
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
)
from terminal.domain.states import CommandState
from terminal.exchange.events import (
    ExecutionEvent,
    NormalizedOrderStatus,
    NormalizedOrderType,
    NormalizedPositionStatus,
    OrderEvent,
    PositionEvent,
)
from terminal.persistence.sqlite_store import (
    CommandRecord,
    ExecutionApplyResult,
    SQLiteStore,
)


ACCOUNT = TradingAccountId("account-1")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0)


def order_event(
    *,
    order_id="order-1",
    link="link-1",
    status=NormalizedOrderStatus.OPEN,
    order_type=NormalizedOrderType.LIMIT,
    side=OrderSide.BUY,
    qty="0.002",
    filled="0",
    leaves="0.002",
    updated=2000,
    stop_type=None,
):
    return OrderEvent(
        trading_account_id=ACCOUNT,
        category=Category.LINEAR,
        symbol="BTCUSDT",
        order_id=OrderId(order_id),
        order_link_id=link,
        position_idx=0,
        side=side,
        order_type=order_type,
        raw_order_type=order_type.value,
        price=Decimal("100"),
        quantity=Decimal(qty),
        cumulative_filled_quantity=Decimal(filled),
        leaves_quantity=Decimal(leaves),
        average_price=Decimal("100") if Decimal(filled) else None,
        status=status,
        raw_status=status.value,
        reduce_only=False,
        close_on_trigger=False,
        stop_order_type=stop_type,
        trigger_price=None,
        take_profit=None,
        stop_loss=None,
        tpsl_mode=None,
        created_at_ms=1000,
        updated_at_ms=updated,
    )


def execution_event(
    *, exec_id="exec-1", order_id="order-1", link="link-1", side=OrderSide.BUY,
    qty="0.001", price="100", timestamp=2100,
):
    return ExecutionEvent(
        trading_account_id=ACCOUNT,
        category=Category.LINEAR,
        symbol="BTCUSDT",
        exec_id=ExecutionId(exec_id),
        order_id=OrderId(order_id),
        order_link_id=link,
        side=side,
        execution_price=Decimal(price),
        execution_quantity=Decimal(qty),
        execution_fee=Decimal("-0.01"),
        execution_value=Decimal(price) * Decimal(qty),
        is_maker=False,
        executed_at_ms=timestamp,
        sequence=10,
    )


def position_event(*, side=PositionSide.LONG, size="0.002", updated=3000):
    value = Decimal(size)
    return PositionEvent(
        position_key=KEY,
        side=side,
        size=value,
        average_entry=Decimal("101.123456789012345678") if value else None,
        mark_price=Decimal("102") if value else None,
        position_value=value * Decimal("101.123456789012345678") if value else Decimal("0"),
        unrealized_pnl=Decimal("0.1") if value else Decimal("0"),
        current_realized_pnl=Decimal("0.2"),
        cumulative_realized_pnl=Decimal("0.3"),
        status=NormalizedPositionStatus.NORMAL,
        raw_status="Normal",
        take_profit=None,
        stop_loss=None,
        trailing_stop=None,
        sequence=20,
        updated_at_ms=updated,
    )


class ExecutionEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "terminal.sqlite3"
        self.store = SQLiteStore.open(self.path)
        self.engine = ExecutionEngine(self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def command(self, state=CommandState.SUBMITTING):
        record = CommandRecord(
            command_id=CommandId("command-1"),
            order_link_id="link-1",
            trading_account_id=ACCOUNT,
            category=Category.LINEAR,
            symbol=Symbol("BTCUSDT"),
            position_idx=0,
            command_kind="create_limit",
            side=OrderSide.BUY,
            requested_notional=Notional(Decimal("0.2")),
            normalized_price=Price(Decimal("100")),
            normalized_quantity=Quantity(Decimal("0.002")),
            origin=Origin.TERMINAL_MANUAL,
            controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED,
            version=1,
            exchange_order_id=None,
            created_at_ms=1000,
            updated_at_ms=1000,
        )
        self.store.persist_command_before_submit(record)
        if state is CommandState.ADMITTED:
            return record
        current = self.store.transition_command_state(
            record.command_id,
            CommandState.ADMITTED,
            CommandState.SUBMITTING,
            expected_version=1,
            reason="submit began",
            occurred_at_ms=1100,
        )
        if state is CommandState.UNKNOWN:
            current = self.store.transition_command_state(
                current.command_id,
                current.current_state,
                CommandState.UNKNOWN,
                expected_version=current.version,
                reason="timeout",
                occurred_at_ms=1200,
            )
        return current

    def test_order_acknowledgement_is_not_fill(self):
        command = self.command()
        resolved = self.engine.resolve_command(
            command,
            order_evidence=(order_event(),),
            execution_evidence=(),
            occurred_at_ms=2200,
        )
        self.assertIs(resolved.current_state, CommandState.OPEN)
        self.assertEqual(self.store.load_executions(), ())
        self.assertIsNone(self.store.get_position_projection(KEY))

    def test_execution_is_exactly_once_for_ws_rest_overlap_and_restart(self):
        event = execution_event()
        self.assertIs(self.engine.apply_execution(event), ExecutionApplyResult.APPLIED)
        self.assertIs(self.engine.apply_execution(event), ExecutionApplyResult.DUPLICATE)
        first = self.store.get_position_projection(KEY)
        self.assertEqual(first.quantity.value, Decimal("0.001"))
        self.store.close()
        self.store = SQLiteStore.open(self.path)
        self.engine = ExecutionEngine(self.store)
        self.assertIs(self.engine.apply_execution(event), ExecutionApplyResult.DUPLICATE)
        self.assertEqual(self.store.get_position_projection(KEY), first)

    def test_execution_before_order_event_correlates_command(self):
        self.command()
        self.engine.apply_execution(execution_event())
        command = self.store.get_command(CommandId("command-1"))
        self.assertEqual(command.exchange_order_id, OrderId("order-1"))
        resolved = self.engine.resolve_command(
            command,
            order_evidence=(),
            execution_evidence=(execution_event(),),
            occurred_at_ms=2300,
        )
        self.assertIs(resolved.current_state, CommandState.PARTIALLY_FILLED)

    def test_multiple_partial_fills_apply_independently_out_of_order(self):
        later = execution_event(exec_id="exec-2", qty="0.001", timestamp=2200)
        earlier = execution_event(exec_id="exec-1", qty="0.0005", timestamp=2100)
        self.engine.apply_execution(later)
        self.engine.apply_execution(earlier)
        projection = self.store.get_position_projection(KEY)
        self.assertEqual(projection.quantity.value, Decimal("0.0015"))
        self.assertEqual(len(self.store.load_executions()), 2)

    def test_execution_after_cancel_intent_remains_economic_fact(self):
        command = self.command()
        acknowledged = self.store.transition_command_state(
            command.command_id,
            CommandState.SUBMITTING,
            CommandState.ACKNOWLEDGED,
            expected_version=command.version,
            reason="ack",
            occurred_at_ms=1300,
        )
        cancel_pending = self.store.transition_command_state(
            command.command_id,
            acknowledged.current_state,
            CommandState.CANCEL_PENDING,
            expected_version=acknowledged.version,
            reason="cancel intent",
            occurred_at_ms=1400,
        )
        self.engine.apply_execution(execution_event(qty="0.002"))
        resolved = self.engine.resolve_command(
            self.store.get_command(cancel_pending.command_id),
            order_evidence=(),
            execution_evidence=(execution_event(qty="0.002"),),
            occurred_at_ms=2400,
        )
        self.assertIs(resolved.current_state, CommandState.FILLED)
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0.002"))

    def test_external_order_inventory_is_not_hidden_or_claimed(self):
        external = order_event(order_id="external", link=None)
        self.engine.replace_order_inventory((external,))
        self.assertEqual(self.engine.active_orders, (external,))
        self.engine.ingest_order(
            order_event(order_id="external", link=None, status=NormalizedOrderStatus.CANCELLED, leaves="0")
        )
        self.assertEqual(self.engine.active_orders, ())

    def test_authoritative_position_translation_creates_no_execution(self):
        update = self.engine.projection_from_authoritative_position(
            position_event(), sync_state="synchronized"
        )
        self.assertEqual(update.quantity.value, Decimal("0.002"))
        self.assertEqual(update.average_entry.value, Decimal("101.123456789012345678"))
        self.assertEqual(self.store.load_executions(), ())

    def test_no_mutation_or_network_api_is_exposed(self):
        forbidden = {"create_order", "amend_order", "cancel_order", "submit", "resubmit"}
        self.assertTrue(all(not hasattr(self.engine, name) for name in forbidden))
        root = Path(__file__).parents[1] / "terminal" / "application"
        imported = set()
        for path in root.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
        self.assertTrue({"pybit", "requests", "websocket", "config", "scanner", "main"}.isdisjoint(imported))


if __name__ == "__main__":
    unittest.main()
