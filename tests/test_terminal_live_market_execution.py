from __future__ import annotations

import threading
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from terminal.api.models import ClientActionId, LiveMarketCommandRequest, VolumeRequest, VolumeUnit
from terminal.application.live_market_execution import (
    LiveMarketMutationCoordinator,
    LiveMarketMutationGates,
)
from terminal.application.trading_accounts import (
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
)
from terminal.domain.models import Category, ExecutionId, OrderId, OrderSide, TradingAccountId
from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition, MutationKind, MutationOutcome
from terminal.exchange.events import (
    ExecutionEvent, InstrumentSnapshot, NormalizedOrderStatus, NormalizedOrderType, OrderEvent,
)
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT_ID = TradingAccountId("bybit-main")


class FakeMutationAdapter:
    def __init__(self, disposition=MutationDisposition.ACKNOWLEDGED):
        self.disposition = disposition
        self.calls = []

    def create_market_order(self, **kwargs):
        self.calls.append(kwargs)
        if self.disposition == "raise":
            raise TimeoutError("lost response")
        return MutationOutcome(
            MutationKind.CREATE,
            self.disposition,
            order_id="exchange-1" if self.disposition is MutationDisposition.ACKNOWLEDGED else None,
            order_link_id=kwargs["order_link_id"],
            reason="test outcome",
        )


class FakeReadAdapter:
    def __init__(self, *, orders=(), executions=(), before_read=None):
        self.orders = orders
        self.executions = executions
        self.before_read = before_read

    def list_active_orders(self, _symbol):
        if self.before_read: self.before_read()
        return self.orders

    def list_order_history(self, _symbol): return self.orders
    def list_executions(self, _symbol): return self.executions
    def get_position(self, _symbol): return object()


def instrument():
    return InstrumentSnapshot(
        category=__import__("terminal.domain.models", fromlist=["Category"]).Category.LINEAR,
        symbol="BTCUSDT", contract_type="LinearPerpetual", status="Trading",
        base_coin="BTC", quote_coin="USDT", settle_coin="USDT",
        tick_size=Decimal("0.1"), quantity_step=Decimal("0.0001"),
        min_order_quantity=Decimal("0.0001"), max_order_quantity=Decimal("100"),
        min_price=Decimal("1"), max_price=Decimal("1000000"),
        min_notional_value=Decimal("5"), max_market_order_quantity=Decimal("100"),
    )


def request(generation=1, *, account_id="bybit-main", action_id="action-1", amount="10"):
    return LiveMarketCommandRequest(
        ClientActionId(action_id), account_id, generation, "BTCUSDT", OrderSide.BUY,
        VolumeRequest(VolumeUnit.USDT, Decimal(amount)), Decimal("50000"),
        "Percent", Decimal("0.5"),
    )


class LiveMarketExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp.name) / "live.sqlite3")
        self.manager = TradingAccountManager((TradingAccount(
            ACCOUNT_ID, "Main Bybit", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ),), active_account_id=ACCOUNT_ID)
        self.adapter = FakeMutationAdapter()

    def tearDown(self):
        if self.store is not None:
            self.store.close()
        self.temp.cleanup()

    def coordinator(self, read_adapter=None, **gate_overrides):
        gates = LiveMarketMutationGates(
            live_market_mutations_enabled=gate_overrides.get("enabled", True),
            live_mainnet_authorized=gate_overrides.get("authorized", True),
            acceptance_notional_ceiling=Decimal(gate_overrides.get("ceiling", "20")),
        )
        return LiveMarketMutationCoordinator(
            self.manager, self.store, lambda _account: self.adapter,
            instrument_provider=lambda _symbol: instrument(), gates=gates,
            writable_account_provider=lambda _account: True,
            read_adapter_provider=(lambda _account: read_adapter) if read_adapter else None,
            clock_ms=lambda: 1000,
        )

    def test_ready_writable_ack_is_pending_and_duplicate_dispatches_once(self):
        coordinator = self.coordinator()
        first = coordinator.submit(request())
        second = coordinator.submit(request())
        self.assertEqual(first.status.value, "accepted_pending")
        self.assertEqual(second.command_id, first.command_id)
        self.assertEqual(second.order_link_id, first.order_link_id)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_concurrent_duplicate_dispatches_once(self):
        database_path = Path(self.temp.name) / "live.sqlite3"
        self.store.close()
        self.store = None
        results = []
        errors = []

        def submit_from_independent_http_owner():
            store = SQLiteStore.open(database_path)
            try:
                manager = TradingAccountManager((TradingAccount(
                    ACCOUNT_ID, "Main Bybit", TradingAccountProvider.BYBIT,
                    TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
                ),), active_account_id=ACCOUNT_ID)
                coordinator = LiveMarketMutationCoordinator(
                    manager, store, lambda _account: self.adapter,
                    instrument_provider=lambda _symbol: instrument(),
                    writable_account_provider=lambda _account: True,
                    gates=LiveMarketMutationGates(True, True, Decimal("20")),
                    clock_ms=lambda: 1000,
                )
                results.append(coordinator.submit(request()))
            except Exception as exc:
                errors.append(exc)
            finally:
                store.close()

        threads = [threading.Thread(target=submit_from_independent_http_owner) for _ in range(2)]
        for item in threads: item.start()
        for item in threads: item.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual({item.command_id for item in results}, {results[0].command_id})

    def test_timeout_is_unknown_and_repeat_never_retries(self):
        self.adapter.disposition = "raise"
        coordinator = self.coordinator()
        first = coordinator.submit(request())
        second = coordinator.submit(request())
        self.assertEqual(first.status.value, "unknown")
        self.assertTrue(first.reconciliation_required)
        self.assertEqual(second.command_id, first.command_id)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_deterministic_reject_is_not_retried(self):
        self.adapter.disposition = MutationDisposition.REJECTED
        coordinator = self.coordinator()
        self.assertEqual(coordinator.submit(request()).status.value, "rejected")
        self.assertEqual(coordinator.submit(request()).status.value, "rejected")
        self.assertEqual(len(self.adapter.calls), 1)

    def test_feature_gates_and_ceiling_block_before_adapter(self):
        self.assertEqual(self.coordinator(enabled=False).submit(request()).reason_code, "live_market_disabled")
        self.assertEqual(self.coordinator(authorized=False).submit(request()).reason_code, "live_mainnet_unauthorized")
        self.assertEqual(self.coordinator(ceiling="9").submit(request()).reason_code, "acceptance_notional_exceeded")
        self.assertEqual(len(self.adapter.calls), 0)

    def test_account_and_session_eligibility_fail_closed(self):
        coordinator = self.coordinator()
        self.assertEqual(coordinator.submit(request(account_id="other")).reason_code, "inactive_account")
        self.assertEqual(coordinator.submit(request(generation=2)).reason_code, "stale_account_session")
        for status in (TradingAccountStatus.READ_ONLY, TradingAccountStatus.ERROR, TradingAccountStatus.RECONCILING):
            self.manager.update_status(ACCOUNT_ID, status)
            self.assertEqual(coordinator.submit(request(action_id=f"status-{status.value}")).status.value, "blocked")
        self.assertEqual(len(self.adapter.calls), 0)

    def test_account_switch_before_dispatch_fences_adapter(self):
        paper = TradingAccount(
            TradingAccountId("paper"), "Paper", TradingAccountProvider.PAPER,
            TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
        )
        self.manager.register_inactive(paper)
        coordinator = self.coordinator()
        coordinator.before_dispatch = lambda: self.manager.activate(TradingAccountId("paper"))
        result = coordinator.submit(request())
        self.assertEqual(result.reason_code, "stale_account_session")
        self.assertEqual(len(self.adapter.calls), 0)

    def test_unknown_reconciliation_execution_resolves_original_filled(self):
        self.adapter.disposition = "raise"
        execution = ExecutionEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", ExecutionId("exec-1"),
            OrderId("exchange-1"), None, OrderSide.BUY, Decimal("50000"),
            Decimal("0.0002"), Decimal("0.01"), Decimal("10"), False, 1000, None,
        )
        read = FakeReadAdapter(executions=(execution,))
        coordinator = self.coordinator(read)
        first = coordinator.submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        execution = ExecutionEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", ExecutionId("exec-2"),
            OrderId("exchange-1"), action.order_link_id, OrderSide.BUY,
            Decimal("50000"), Decimal("0.0002"), Decimal("0.01"),
            Decimal("10"), False, 1001, None,
        )
        read.executions = (execution,)
        resolved = coordinator.submit(request())
        self.assertEqual(first.status.value, "unknown")
        self.assertEqual(resolved.status.value, "completed")
        self.assertEqual(resolved.command_id, first.command_id)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_stale_reconciliation_does_not_resolve_old_session(self):
        paper = TradingAccount(
            TradingAccountId("paper"), "Paper", TradingAccountProvider.PAPER,
            TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
        )
        self.manager.register_inactive(paper)
        self.adapter.disposition = "raise"
        coordinator = self.coordinator()
        first = coordinator.submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        evidence = OrderEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", OrderId("exchange-1"),
            action.order_link_id, 0, OrderSide.BUY, NormalizedOrderType.MARKET,
            "Market", None, Decimal("0.0002"), Decimal("0.0002"), Decimal("0"),
            Decimal("50000"), NormalizedOrderStatus.FILLED, "Filled", False, False,
            None, None, None, None, None, 1000, 1000,
        )
        read = FakeReadAdapter(
            orders=(evidence,), before_read=lambda: self.manager.activate(TradingAccountId("paper")),
        )
        coordinator._read_adapter_provider = lambda _account: read
        stale = coordinator.submit(request())
        self.assertEqual(stale.status.value, "unknown")
        self.assertEqual(stale.command_id, first.command_id)


if __name__ == "__main__":
    unittest.main()
