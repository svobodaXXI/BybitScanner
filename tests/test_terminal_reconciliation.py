import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.application.execution_engine import ExecutionEngine
from terminal.application.models import FlatCause, RecoveryBundle, TrustState
from terminal.application.reconciliation import ReconciliationCoordinator
from terminal.domain.models import (
    Category,
    CommandId,
    Controller,
    Notional,
    OrderSide,
    Origin,
    PositionSide,
    Price,
    Quantity,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.events import (
    NormalizedOrderStatus,
    NormalizedOrderType,
    StreamLifecycleEvent,
    StreamLifecycleKind,
)
from terminal.persistence.sqlite_store import CommandRecord, ConcurrentUpdate, SQLiteStore
from tests.test_terminal_execution_engine import (
    ACCOUNT,
    KEY,
    execution_event,
    order_event,
    position_event,
)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "terminal.sqlite3"
        self.store = SQLiteStore.open(self.path)
        self.engine = ExecutionEngine(self.store)
        self.coordinator = ReconciliationCoordinator(self.engine)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def persist_command(self, state=CommandState.SUBMITTING):
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

    def bundle(self, *, position=None, **kwargs):
        return RecoveryBundle(
            position_key=KEY,
            position_snapshot=position if position is not None else position_event(side=PositionSide.FLAT, size="0"),
            open_orders=kwargs.pop("open_orders", ()),
            order_history=kwargs.pop("order_history", ()),
            executions=kwargs.pop("executions", ()),
            **kwargs,
        )

    def reconcile(self, bundle, generation=1, started=1000, completed=4000):
        return self.coordinator.reconcile(
            bundle,
            generation=generation,
            started_at_ms=started,
            completed_at_ms=completed,
        )

    def test_clean_startup_converges_and_persists_checkpoint(self):
        result = self.reconcile(self.bundle())
        self.assertIs(result.trust_state, TrustState.CONVERGED)
        self.assertEqual(result.active_orders, ())
        self.assertEqual(result.checkpoint.outcome, TrustState.CONVERGED.value)
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0"))

    def test_startup_accepts_open_position_active_limits_and_external_orders(self):
        local = order_event(order_id="local", link="link-local")
        external = order_event(order_id="external", link=None)
        result = self.reconcile(
            self.bundle(
                position=position_event(),
                open_orders=(local, external),
            )
        )
        self.assertTrue(result.converged)
        self.assertEqual({item.order_id.value for item in result.active_orders}, {"local", "external"})
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0.002"))

    def test_unfinished_submitting_and_unknown_remain_unresolved_without_evidence(self):
        submitting = self.persist_command()
        result = self.reconcile(self.bundle(unfinished_commands=(submitting,)))
        self.assertIs(result.trust_state, TrustState.RECONCILING)
        self.assertEqual(result.unresolved_command_ids, ("command-1",))
        self.assertIs(self.store.get_command(CommandId("command-1")).current_state, CommandState.UNKNOWN)
        self.assertFalse(hasattr(self.coordinator, "resubmit"))

    def test_unknown_after_restart_requires_sufficient_evidence(self):
        unknown = self.persist_command(CommandState.UNKNOWN)
        result = self.reconcile(self.bundle(unfinished_commands=(unknown,)))
        self.assertFalse(result.converged)
        self.assertIs(self.store.get_command(unknown.command_id).current_state, CommandState.UNKNOWN)

    def test_command_absent_from_open_orders_resolves_from_execution(self):
        command = self.persist_command()
        fill = execution_event(qty="0.002")
        result = self.reconcile(
            self.bundle(
                position=position_event(size="0.002"),
                executions=(fill,),
                unfinished_commands=(command,),
            )
        )
        self.assertTrue(result.converged)
        self.assertIs(self.store.get_command(command.command_id).current_state, CommandState.FILLED)

    def test_command_absent_from_open_orders_resolves_from_history(self):
        command = self.persist_command()
        final = order_event(
            status=NormalizedOrderStatus.CANCELLED,
            leaves="0",
            updated=3000,
        )
        result = self.reconcile(
            self.bundle(order_history=(final,), unfinished_commands=(command,))
        )
        self.assertTrue(result.converged)
        self.assertIs(self.store.get_command(command.command_id).current_state, CommandState.CANCELLED)

    def test_ws_rest_overlap_and_restart_replay_are_deduplicated(self):
        fill = execution_event()
        first = self.reconcile(
            self.bundle(position=position_event(size="0.001"), executions=(fill,), buffered_executions=(fill,))
        )
        self.assertEqual(first.applied_execution_count, 1)
        self.assertEqual(first.duplicate_execution_count, 1)
        self.store.close()
        self.store = SQLiteStore.open(self.path)
        self.engine = ExecutionEngine(self.store)
        self.coordinator = ReconciliationCoordinator(self.engine)
        second = self.reconcile(
            self.bundle(position=position_event(size="0.001", updated=5000), executions=(fill,)),
            generation=2,
            started=4500,
            completed=5500,
        )
        self.assertEqual(second.applied_execution_count, 0)
        self.assertEqual(second.duplicate_execution_count, 1)
        self.assertEqual(len(self.store.load_executions()), 1)

    def test_out_of_order_multiple_fills_and_fill_during_outage_converge(self):
        later = execution_event(exec_id="exec-2", qty="0.001", timestamp=2500)
        earlier = execution_event(exec_id="exec-1", qty="0.0005", timestamp=2000)
        lifecycle = (
            StreamLifecycleEvent(ACCOUNT, StreamLifecycleKind.DISCONNECTED, "gap"),
            StreamLifecycleEvent(ACCOUNT, StreamLifecycleKind.CONNECTED_UNTRUSTED, "reconnected"),
        )
        result = self.reconcile(
            self.bundle(
                position=position_event(size="0.0015"),
                executions=(later, earlier),
                stream_lifecycle=lifecycle,
            )
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.applied_execution_count, 2)
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0.0015"))

    def test_disconnect_without_recovered_stream_remains_non_converged(self):
        disconnected = StreamLifecycleEvent(ACCOUNT, StreamLifecycleKind.DISCONNECTED, "gap")
        result = self.reconcile(self.bundle(stream_lifecycle=(disconnected,)))
        self.assertIs(result.trust_state, TrustState.RECONCILING)
        self.assertEqual(result.checkpoint.outcome, TrustState.RECONCILING.value)

    def test_incomplete_rest_inputs_keep_unfinished_checkpoint(self):
        result = self.reconcile(self.bundle(rest_history_complete=False))
        self.assertIs(result.trust_state, TrustState.RECONCILING)
        self.assertEqual(result.checkpoint.outcome, "in_progress")
        self.assertIsNone(result.checkpoint.completed_at_ms)

    def test_external_position_change_corrects_stale_projection_without_fake_execution(self):
        self.reconcile(self.bundle(position=position_event(size="0.001")))
        result = self.reconcile(
            self.bundle(position=position_event(size="0.009", updated=6000)),
            generation=2,
            started=5000,
            completed=6500,
        )
        self.assertTrue(result.converged)
        self.assertEqual(self.store.get_position_projection(KEY).quantity.value, Decimal("0.009"))
        self.assertEqual(self.store.load_executions(), ())

    def test_position_event_never_fabricates_fill(self):
        result = self.reconcile(self.bundle(position=position_event(size="0.004")))
        self.assertTrue(result.converged)
        self.assertEqual(self.store.load_executions(), ())

    def test_external_limit_add_and_remove_follow_buffered_exchange_truth(self):
        external = order_event(order_id="external", link=None)
        cancelled = order_event(
            order_id="external", link=None, status=NormalizedOrderStatus.CANCELLED, leaves="0", updated=3000
        )
        result = self.reconcile(
            self.bundle(open_orders=(external,), buffered_orders=(cancelled,))
        )
        self.assertTrue(result.converged)
        self.assertEqual(result.active_orders, ())

    def test_flat_transition_market_sl_tp_and_ambiguous_causes(self):
        cases = (
            (order_event(status=NormalizedOrderStatus.FILLED, order_type=NormalizedOrderType.MARKET, side=OrderSide.SELL, leaves="0"), FlatCause.MARKET),
            (order_event(status=NormalizedOrderStatus.FILLED, side=OrderSide.SELL, leaves="0", stop_type="StopLoss"), FlatCause.STOP_LOSS),
            (order_event(status=NormalizedOrderStatus.FILLED, side=OrderSide.SELL, leaves="0", stop_type="TakeProfit"), FlatCause.TAKE_PROFIT),
            (None, FlatCause.UNKNOWN),
        )
        for index, (closing_order, expected) in enumerate(cases):
            with self.subTest(cause=expected):
                path = Path(self.temp.name) / f"cause-{index}.sqlite3"
                with SQLiteStore.open(path) as store:
                    coordinator = ReconciliationCoordinator(ExecutionEngine(store))
                    coordinator.reconcile(
                        self.bundle(position=position_event(size="0.002")),
                        generation=1,
                        started_at_ms=1000,
                        completed_at_ms=3000,
                    )
                    history = (closing_order,) if closing_order is not None else ()
                    result = coordinator.reconcile(
                        self.bundle(
                            position=position_event(side=PositionSide.FLAT, size="0", updated=5000),
                            order_history=history,
                        ),
                        generation=2,
                        started_at_ms=4000,
                        completed_at_ms=5500,
                    )
                    self.assertIs(result.flat_transition.cause, expected)
                    self.assertEqual(store.load_executions(), ())

    def test_previous_converged_checkpoint_does_not_grant_new_session_online(self):
        self.reconcile(self.bundle())
        self.store.close()
        self.store = SQLiteStore.open(self.path)
        self.engine = ExecutionEngine(self.store)
        self.coordinator = ReconciliationCoordinator(self.engine)
        result = self.reconcile(
            self.bundle(rest_position_complete=False),
            generation=2,
            started=5000,
            completed=6000,
        )
        self.assertIs(result.trust_state, TrustState.RECONCILING)

    def test_stale_reconciliation_generation_is_rejected(self):
        self.reconcile(self.bundle(), generation=2)
        with self.assertRaises(ConcurrentUpdate):
            self.reconcile(self.bundle(), generation=2, started=5000, completed=6000)

    def test_mismatched_exchange_scope_fails_closed(self):
        foreign = replace(order_event(), trading_account_id=TradingAccountId("other-account"))
        result = self.reconcile(self.bundle(open_orders=(foreign,)))
        self.assertIs(result.trust_state, TrustState.FAILED_INCONSISTENT)
        self.assertFalse(result.converged)

    def test_conflicting_execution_identity_fails_closed_without_application(self):
        first = execution_event()
        conflicting = replace(first, execution_quantity=Decimal("0.009"))
        result = self.reconcile(
            self.bundle(executions=(first,), buffered_executions=(conflicting,))
        )
        self.assertIs(result.trust_state, TrustState.FAILED_INCONSISTENT)
        self.assertEqual(self.store.load_executions(), ())


if __name__ == "__main__":
    unittest.main()
