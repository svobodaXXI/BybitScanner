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
from terminal.domain.states import CommandState
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
        if self.disposition == "crash":
            raise SimulatedCrash()
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


class SimulatedCrash(BaseException):
    pass


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


def request(
    generation=1, *, account_id="bybit-main", action_id="action-1", amount="10",
    symbol="BTCUSDT", side=OrderSide.BUY, slippage_type="Percent", slippage_value="0.5",
):
    return LiveMarketCommandRequest(
        ClientActionId(action_id), account_id, generation, symbol, side,
        VolumeRequest(VolumeUnit.USDT, Decimal(amount)), Decimal("50000"),
        slippage_type, Decimal(slippage_value),
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
            acceptance_single_flight=gate_overrides.get("single_flight", False),
        )
        return LiveMarketMutationCoordinator(
            self.manager, self.store, lambda _account: self.adapter,
            instrument_provider=lambda _symbol: instrument(), gates=gates,
            writable_account_provider=lambda _account: True,
            read_adapter_provider=(lambda _account: read_adapter) if read_adapter else None,
            clock_ms=lambda: 1000,
        )

    def restart(self, read_adapter=None):
        database_path = Path(self.temp.name) / "live.sqlite3"
        self.store.close()
        self.store = SQLiteStore.open(database_path)
        self.manager = TradingAccountManager((TradingAccount(
            ACCOUNT_ID, "Main Bybit", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ),), active_account_id=ACCOUNT_ID)
        self.adapter = FakeMutationAdapter()
        return self.coordinator(read_adapter)

    def crash_while_submitting(self):
        self.adapter.disposition = "crash"
        with self.assertRaises(SimulatedCrash):
            self.coordinator().submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        self.assertIsNotNone(action)
        self.assertIs(self.store.get_command(action.command_id).current_state, CommandState.SUBMITTING)
        return action

    def test_ready_writable_ack_is_pending_and_duplicate_dispatches_once(self):
        coordinator = self.coordinator()
        first = coordinator.submit(request())
        second = coordinator.submit(request())
        self.assertEqual(first.status.value, "accepted_pending")
        self.assertEqual(second.command_id, first.command_id)
        self.assertEqual(second.order_link_id, first.order_link_id)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.adapter.calls[0], {
            "symbol": "BTCUSDT", "side": "Buy", "qty": Decimal("0.0002"),
            "order_link_id": first.order_link_id, "reduce_only": False,
            "slippage_tolerance_type": "Percent",
            "slippage_tolerance": Decimal("0.5"),
        })

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

    def test_acceptance_single_flight_blocks_distinct_action_after_first_filled(self):
        coordinator = self.coordinator(single_flight=True)
        first = coordinator.submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        execution = ExecutionEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", ExecutionId("acceptance-exec"),
            OrderId("exchange-1"), action.order_link_id, OrderSide.BUY,
            Decimal("50000"), Decimal("0.0002"), Decimal("0.01"),
            Decimal("10"), False, 1001, None,
        )
        read = FakeReadAdapter(executions=(execution,))
        coordinator._read_adapter_provider = lambda _account: read
        resolved = coordinator.submit(request())
        second = coordinator.submit(request(action_id="action-2"))
        self.assertEqual(first.status.value, "accepted_pending")
        self.assertEqual(resolved.status.value, "completed")
        self.assertEqual(second.reason_code, "acceptance_permit_consumed")
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

    def test_account_switch_after_final_validation_fences_adapter(self):
        paper = TradingAccount(
            TradingAccountId("paper"), "Paper", TradingAccountProvider.PAPER,
            TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
        )
        self.manager.register_inactive(paper)
        coordinator = self.coordinator()
        coordinator.after_final_validation = lambda: self.manager.activate(TradingAccountId("paper"))
        result = coordinator.submit(request())
        self.assertEqual(result.reason_code, "stale_account_session")
        self.assertEqual(self.adapter.calls, [])

    def test_final_validation_blocks_invalid_payload_without_adapter(self):
        invalid_requests = (
            request(action_id="bad-symbol", symbol="ETHUSDT"),
            request(action_id="bad-slippage-type", slippage_type="Unknown"),
            request(action_id="bad-slippage-value", slippage_value="10.01"),
            request(action_id="bad-tick-slippage", slippage_type="TickSize", slippage_value="1.5"),
        )
        expected = (
            "invalid_live_market_symbol", "invalid_live_market_slippage",
            "invalid_live_market_slippage", "invalid_live_market_slippage",
        )
        for item, reason in zip(invalid_requests, expected):
            with self.subTest(reason=reason, action=item.client_action_id.value):
                result = self.coordinator().submit(item)
                self.assertEqual(result.reason_code, reason)
        self.assertEqual(self.adapter.calls, [])

    def test_final_authoritative_notional_ceiling_rechecked_before_adapter(self):
        coordinator = self.coordinator(ceiling="20")
        coordinator.before_dispatch = lambda: setattr(
            coordinator, "_gates", LiveMarketMutationGates(True, True, Decimal("9")),
        )
        result = coordinator.submit(request())
        self.assertEqual(result.reason_code, "acceptance_notional_exceeded")
        self.assertEqual(self.adapter.calls, [])

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

    def test_restart_submitting_found_by_original_link_without_mutation(self):
        action = self.crash_while_submitting()
        evidence = OrderEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", OrderId("exchange-restart"),
            action.order_link_id, 0, OrderSide.BUY, NormalizedOrderType.MARKET,
            "Market", None, Decimal("0.0002"), Decimal("0"), Decimal("0.0002"),
            None, NormalizedOrderStatus.OPEN, "New", False, False,
            None, None, None, None, None, 1000, 1000,
        )
        coordinator = self.restart(FakeReadAdapter(orders=(evidence,)))
        recovered = coordinator.recover_unresolved()
        self.assertIs(recovered[0].current_state, CommandState.OPEN)
        self.assertEqual(self.adapter.calls, [])

    def test_restart_submitting_without_evidence_remains_unknown(self):
        action = self.crash_while_submitting()
        coordinator = self.restart(FakeReadAdapter())
        recovered = coordinator.recover_unresolved()
        self.assertIs(recovered[0].current_state, CommandState.UNKNOWN)
        self.assertEqual(recovered[0].command_id, action.command_id)
        self.assertEqual(self.adapter.calls, [])

    def test_restart_unknown_execution_fills_and_same_action_never_redispatches(self):
        self.adapter.disposition = "raise"
        first = self.coordinator().submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        execution = ExecutionEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", ExecutionId("restart-exec"),
            OrderId("restart-order"), action.order_link_id, OrderSide.BUY,
            Decimal("50000"), Decimal("0.0002"), Decimal("0.01"),
            Decimal("10"), False, 1001, None,
        )
        coordinator = self.restart(FakeReadAdapter(executions=(execution,)))
        recovered = coordinator.recover_unresolved()
        repeated = coordinator.submit(request(generation=2))
        self.assertIs(recovered[0].current_state, CommandState.FILLED)
        self.assertEqual(repeated.command_id, first.command_id)
        self.assertEqual(repeated.order_link_id, first.order_link_id)
        self.assertEqual(self.adapter.calls, [])

    def test_restart_acknowledged_open_and_unresolved_blocks_new_session(self):
        first = self.coordinator().submit(request())
        action = self.store.get_live_market_action(ACCOUNT_ID, 1, "action-1")
        evidence = OrderEvent(
            ACCOUNT_ID, Category.LINEAR, "BTCUSDT", OrderId("exchange-1"),
            action.order_link_id, 0, OrderSide.BUY, NormalizedOrderType.MARKET,
            "Market", None, Decimal("0.0002"), Decimal("0"), Decimal("0.0002"),
            None, NormalizedOrderStatus.OPEN, "New", False, False,
            None, None, None, None, None, 1000, 1000,
        )
        coordinator = self.restart(FakeReadAdapter(orders=(evidence,)))
        self.assertIs(coordinator.recover_unresolved()[0].current_state, CommandState.OPEN)
        self.assertEqual(self.adapter.calls, [])

    def test_restart_unresolved_blocks_conflicting_live_market(self):
        self.crash_while_submitting()
        coordinator = self.restart()
        blocked = coordinator.submit(request(action_id="conflicting"))
        self.assertEqual(blocked.reason_code, "unresolved_live_market_command")
        self.assertEqual(self.adapter.calls, [])

    def test_restart_recovery_late_account_switch_never_refreshes_new_projection(self):
        self.crash_while_submitting()
        paper = TradingAccount(
            TradingAccountId("paper"), "Paper", TradingAccountProvider.PAPER,
            TradingAccountEnvironment.PAPER, TradingAccountStatus.READY,
        )
        coordinator = self.restart()
        self.manager.register_inactive(paper)
        refreshes = []
        read = FakeReadAdapter(before_read=lambda: self.manager.activate(TradingAccountId("paper")))
        coordinator._read_adapter_provider = lambda _account: read
        coordinator._projection_refresher = refreshes.append
        coordinator.recover_unresolved()
        self.assertEqual(refreshes, [])
        self.assertEqual(self.adapter.calls, [])

    def test_recovery_never_obtains_mutation_adapter(self):
        self.crash_while_submitting()
        coordinator = self.restart(FakeReadAdapter())
        mutation_provider_calls = []

        def forbidden_mutation_provider(account_id):
            mutation_provider_calls.append(account_id)
            raise AssertionError("recovery must not obtain a mutation adapter")

        coordinator._mutation_adapter_provider = forbidden_mutation_provider
        coordinator.recover_unresolved()
        self.assertEqual(mutation_provider_calls, [])
        self.assertEqual(self.adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
