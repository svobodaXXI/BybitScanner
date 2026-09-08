from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.api.models import ClientActionId, FullCloseCommandRequest
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.live_execution import LiveExecutionCoordinator, LiveParityMutationGates
from terminal.application.models import ProtectionEvidence, ProtectionState
from terminal.application.trading_accounts import (
    TradingAccount,
    TradingAccountEnvironment,
    TradingAccountManager,
    TradingAccountProvider,
    TradingAccountStatus,
)
from terminal.domain.models import (
    Category,
    ExecutionId,
    OrderId,
    OrderSide,
    PositionKey,
    PositionSide,
    Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition,
    MutationKind,
    MutationOutcome,
)
from terminal.exchange.events import (
    ExecutionEvent,
    InstrumentSnapshot,
    NormalizedOrderStatus,
    NormalizedOrderType,
    NormalizedPositionStatus,
    OrderEvent,
    PositionEvent,
)
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("bybit-main")
SYMBOL = Symbol("BTCUSDT")
POSITION_KEY = PositionKey(ACCOUNT, Category.LINEAR, SYMBOL, 0)


def _instrument() -> InstrumentSnapshot:
    return InstrumentSnapshot(
        Category.LINEAR,
        SYMBOL.value,
        "LinearPerpetual",
        "Trading",
        "BTC",
        "USDT",
        "USDT",
        Decimal("1"),
        Decimal("1000000"),
        Decimal("0.5"),
        Decimal("0.001"),
        Decimal("100"),
        Decimal("50"),
        Decimal("0.001"),
        Decimal("5"),
    )


def _open_position() -> PositionEvent:
    return PositionEvent(
        POSITION_KEY,
        PositionSide.LONG,
        Decimal("0.01"),
        Decimal("50000"),
        Decimal("50000"),
        Decimal("500"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        NormalizedPositionStatus.NORMAL,
        "Normal",
        None,
        None,
        None,
        None,
        1000,
    )


class _MutationAdapter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create_market_order(self, **payload):
        self.calls.append(payload)
        return MutationOutcome(
            MutationKind.CREATE,
            MutationDisposition.ACKNOWLEDGED,
            "exchange-close",
            payload.get("order_link_id"),
        )


class _ReadAdapter:
    def __init__(self, *, position, history=(), executions=()) -> None:
        self.position = position
        self.history = history
        self.executions = executions

    def get_position(self, _symbol):
        return self.position

    def list_active_orders(self, _symbol):
        return ()

    def list_order_history(self, _symbol):
        return self.history

    def list_executions(self, _symbol):
        return self.executions


class LiveFullCloseProtectionReconciliationTests(unittest.TestCase):
    def test_filled_full_close_with_authoritative_flat_clears_stale_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = SQLiteStore.open(root / "commands.sqlite3")
            live_store = LiveAccountProjectionStore(root / "live.sqlite3")
            try:
                live_store.publish(
                    LiveAccountSnapshot(
                        ACCOUNT.value,
                        "MAINNET",
                        False,
                        1,
                        Decimal("1000"),
                        Decimal("1000"),
                        Decimal("1000"),
                        1000,
                        (),
                        (),
                        1000,
                    )
                )
                manager = TradingAccountManager(
                    (
                        TradingAccount(
                            ACCOUNT,
                            "Main",
                            TradingAccountProvider.BYBIT,
                            TradingAccountEnvironment.MAINNET,
                            TradingAccountStatus.READY,
                        ),
                    ),
                    active_account_id=ACCOUNT,
                )
                mutation = _MutationAdapter()
                initial_read = _ReadAdapter(position=_open_position())
                coordinator = LiveExecutionCoordinator(
                    manager,
                    store,
                    lambda _account: mutation,
                    read_adapter_provider=lambda _account: initial_read,
                    instrument_provider=lambda _symbol: _instrument(),
                    live_account_store=live_store,
                    writable_account_provider=lambda _account: True,
                    gates=LiveParityMutationGates(
                        parity_mutations_enabled=True,
                        mainnet_authorized=True,
                    ),
                    clock_ms=lambda: 1000,
                )

                accepted = coordinator.execute_full_close(
                    ACCOUNT.value,
                    1,
                    "close-once",
                    lambda api: api.full_close(
                        FullCloseCommandRequest(ClientActionId("close-once"), SYMBOL.value)
                    ),
                )
                self.assertEqual(accepted.status.value, "accepted_pending")
                self.assertEqual(len(mutation.calls), 1)

                command = store.load_unfinished_commands()[0]
                self.assertEqual(command.current_state, CommandState.ACKNOWLEDGED)
                self.assertEqual(command.command_kind, "create_market")

                ExecutionEngine(store).ingest_protection_evidence(
                    ProtectionEvidence(
                        POSITION_KEY,
                        Decimal("52000"),
                        None,
                        Decimal("0"),
                        1001,
                    )
                )
                before = store.get_protection_projection(POSITION_KEY)
                self.assertEqual(before.status, ProtectionState.CONFIRMED_ACTIVE.value)
                self.assertEqual(before.take_profit, Decimal("52000"))

                filled_order = OrderEvent(
                    ACCOUNT,
                    Category.LINEAR,
                    SYMBOL.value,
                    OrderId("exchange-close"),
                    command.order_link_id,
                    0,
                    OrderSide.SELL,
                    NormalizedOrderType.MARKET,
                    "Market",
                    None,
                    Decimal("0.01"),
                    Decimal("0.01"),
                    Decimal("0"),
                    Decimal("50010"),
                    NormalizedOrderStatus.FILLED,
                    "Filled",
                    True,
                    False,
                    None,
                    None,
                    None,
                    None,
                    None,
                    1000,
                    1100,
                )
                execution = ExecutionEvent(
                    ACCOUNT,
                    Category.LINEAR,
                    SYMBOL.value,
                    ExecutionId("exec-close"),
                    OrderId("exchange-close"),
                    command.order_link_id,
                    OrderSide.SELL,
                    Decimal("50010"),
                    Decimal("0.01"),
                    Decimal("-0.01"),
                    Decimal("500.1"),
                    False,
                    1100,
                    None,
                )
                flat_read = _ReadAdapter(
                    position=None,
                    history=(filled_order,),
                    executions=(execution,),
                )
                recovery = LiveExecutionCoordinator(
                    manager,
                    store,
                    lambda _account: (_ for _ in ()).throw(
                        AssertionError("recovery must not acquire mutation authority")
                    ),
                    read_adapter_provider=lambda _account: flat_read,
                    instrument_provider=lambda _symbol: _instrument(),
                    live_account_store=live_store,
                    writable_account_provider=lambda _account: True,
                    gates=LiveParityMutationGates(),
                    clock_ms=lambda: 1200,
                )

                recovery.recover_unresolved(ACCOUNT)

                resolved = store.get_command(command.command_id)
                self.assertEqual(resolved.current_state, CommandState.FILLED)
                projection = store.get_protection_projection(POSITION_KEY)
                self.assertEqual(
                    projection.status,
                    ProtectionState.NO_PROTECTION_CONFIGURED.value,
                )
                self.assertIsNone(projection.take_profit)
                self.assertIsNone(projection.stop_loss)
                self.assertEqual(projection.trailing_stop, Decimal("0"))
                self.assertIsNone(projection.pending_command_id)
                self.assertEqual(len(mutation.calls), 1)
            finally:
                store.close()
                live_store.close()


if __name__ == "__main__":
    unittest.main()
