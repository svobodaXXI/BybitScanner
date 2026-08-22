import tempfile
import unittest
import uuid
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.application.cleanup import CleanupStatus, ConfirmedFlatCleanupService, is_ordinary_active_limit
from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.models import FlatCause, FlatTransitionEvidence, ReconciliationResult, TrustState
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import Category, PositionKey, PositionSide, Quantity, Symbol, TradingAccountId
from terminal.domain.states import ConnectivityState
from terminal.exchange.events import NormalizedOrderStatus
from terminal.persistence.sqlite_store import ReconciliationCheckpointRecord, SQLiteStore
from tests.test_terminal_reconciliation import order_event, position_event
from tests.test_terminal_trading_application import Adapter, Guard, admitted


ACCOUNT = TradingAccountId("account-1")
KEY = PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp.name) / "db.sqlite3")
        self.adapter = Adapter()
        self.app = TradingApplication(
            Guard(admitted()), self.store, self.adapter, ExecutionEngine(self.store),
            mutations_enabled=True, clock_ms=lambda: 5000,
        )
        values = iter(range(10, 100))
        factory = CommandIdentityFactory(lambda: uuid.UUID(int=next(values)))
        self.service = ConfirmedFlatCleanupService(self.store, self.app, factory)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def result(self, cause=FlatCause.MARKET, orders=()):
        flat_position = position_event(side=PositionSide.FLAT, size="0", updated=5000)
        transition = FlatTransitionEvidence(
            KEY, PositionSide.LONG, Quantity(Decimal("1")), flat_position,
            5000, 10, cause,
        )
        generation = {
            FlatCause.MARKET: 2, FlatCause.STOP_LOSS: 3,
            FlatCause.TAKE_PROFIT: 4,
        }.get(cause, 5)
        checkpoint = ReconciliationCheckpointRecord(
            KEY, generation, "converged", 5000, 10, 4000, 5000, 2, 5000
        )
        return ReconciliationResult(
            TrustState.CONVERGED, KEY, tuple(orders), (), 0, 0,
            checkpoint, transition, (),
        )

    def test_market_sl_tp_trigger_and_unknown_external_do_not(self):
        for cause in (FlatCause.MARKET, FlatCause.STOP_LOSS, FlatCause.TAKE_PROFIT):
            with self.subTest(cause=cause):
                result = self.service.start(self.result(cause), connectivity=ConnectivityState.ONLINE)
                self.assertTrue(result.triggered)
        for cause in (FlatCause.EXTERNAL_OTHER, FlatCause.UNKNOWN):
            with self.subTest(cause=cause):
                self.assertFalse(self.service.start(
                    self.result(cause), connectivity=ConnectivityState.ONLINE
                ).triggered)

    def test_filter_selects_all_origin_ordinary_current_symbol_only(self):
        ordinary = order_event(order_id="ordinary", link=None)
        external = order_event(order_id="external", link="metascalp")
        conditional = replace(order_event(order_id="sl"), stop_order_type="StopLoss", trigger_price=Decimal("90"))
        other = replace(order_event(order_id="other"), symbol="ETHUSDT")
        final = order_event(order_id="final", status=NormalizedOrderStatus.CANCELLED, leaves="0")
        result = self.service.start(
            self.result(orders=(ordinary, external, conditional, other, final)),
            connectivity=ConnectivityState.ONLINE,
        )
        self.assertEqual({item.order_id.value for item in result.items}, {"ordinary", "external"})
        self.assertEqual(len(self.adapter.calls), 2)
        self.assertFalse(hasattr(self.app.adapter, "cancel_all_orders"))

    def test_repeat_is_idempotent_and_unknown_is_not_retried(self):
        from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition

        self.adapter.disposition = MutationDisposition.UNKNOWN
        evidence = self.result(orders=(order_event(order_id="one"),))
        first = self.service.start(evidence, connectivity=ConnectivityState.ONLINE)
        second = self.service.start(evidence, connectivity=ConnectivityState.ONLINE)
        self.assertEqual(first.run.cleanup_id, second.run.cleanup_id)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(second.items[0].status, "unknown")

    def test_offline_persists_obligation_without_call_and_restart_loads_it(self):
        result = self.service.start(
            self.result(orders=(order_event(order_id="one"),)),
            connectivity=ConnectivityState.OFFLINE,
        )
        self.assertEqual(result.run.status, CleanupStatus.DEFERRED_OFFLINE.value)
        self.assertEqual(self.adapter.calls, [])
        cleanup_id = result.run.cleanup_id
        self.store.close()
        self.store = SQLiteStore.open(Path(self.temp.name) / "db.sqlite3")
        self.assertIsNotNone(self.store.get_cleanup_run(cleanup_id))
        self.assertEqual(len(self.store.load_cleanup_items(cleanup_id)), 1)
        adapter = Adapter()
        app = TradingApplication(
            Guard(admitted()), self.store, adapter, ExecutionEngine(self.store),
            mutations_enabled=True, clock_ms=lambda: 6000,
        )
        resumed = ConfirmedFlatCleanupService(self.store, app).start(
            self.result(orders=(order_event(order_id="one"),)),
            connectivity=ConnectivityState.ONLINE,
        )
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(resumed.items[0].status, "cancel_pending")

    def test_cancel_confirmation_and_racing_fill_reopens_truthfully(self):
        started = self.service.start(
            self.result(orders=(order_event(order_id="one"),)),
            connectivity=ConnectivityState.ONLINE,
        )
        cancelled = order_event(
            order_id="one", status=NormalizedOrderStatus.CANCELLED, leaves="0", updated=6000
        )
        flat = position_event(side=PositionSide.FLAT, size="0", updated=6000)
        completed = self.service.reconcile(
            started.run.cleanup_id, position=flat, active_orders=(),
            observed_orders=(cancelled,), occurred_at_ms=6000,
        )
        self.assertEqual(completed.run.status, CleanupStatus.COMPLETE.value)

        reopened = position_event(side=PositionSide.LONG, size="0.1", updated=7000)
        raced = self.service.reconcile(
            started.run.cleanup_id, position=reopened, active_orders=(),
            observed_orders=(replace(cancelled, status=NormalizedOrderStatus.FILLED),),
            occurred_at_ms=7000,
        )
        self.assertEqual(raced.run.status, CleanupStatus.REOPENED.value)


if __name__ == "__main__":
    unittest.main()
