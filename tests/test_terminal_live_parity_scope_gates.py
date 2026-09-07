from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    ClientActionId, FullCloseCommandRequest, ProtectionCommandRequest,
)
from terminal.application.live_execution import LiveExecutionCoordinator, LiveParityMutationGates
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition, MutationKind, MutationOutcome
from terminal.exchange.events import (
    InstrumentSnapshot, NormalizedPositionStatus, PositionEvent,
)
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("bybit-main")


def instrument():
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading", "BTC", "USDT", "USDT",
        Decimal("1"), Decimal("1000000"), Decimal("0.5"), Decimal("0.001"),
        Decimal("100"), Decimal("50"), Decimal("0.001"), Decimal("5"),
    )


def position():
    return PositionEvent(
        PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0),
        PositionSide.LONG, Decimal("0.01"), Decimal("50000"), Decimal("50000"),
        Decimal("500"), Decimal("0"), Decimal("0"), Decimal("0"),
        NormalizedPositionStatus.NORMAL, "Normal", None, None, None, None, 1000,
    )


class MutationAdapter:
    def __init__(self):
        self.calls = []

    def create_market_order(self, **payload):
        self.calls.append(("full_close", payload))
        return MutationOutcome(MutationKind.CREATE, MutationDisposition.ACKNOWLEDGED)

    def set_trading_stop(self, **payload):
        self.calls.append(("protection", payload))
        return MutationOutcome(MutationKind.PROTECTION, MutationDisposition.ACKNOWLEDGED)

    def create_limit_order(self, **_payload):
        raise AssertionError("Limit must not enter this regression")

    def amend_order(self, **_payload):
        raise AssertionError("amend must not enter this regression")

    def cancel_order(self, **_payload):
        raise AssertionError("cancel must not enter this regression")


class ReadAdapter:
    def get_position(self, _symbol):
        return position()

    def list_active_orders(self, _symbol):
        return ()

    def list_order_history(self, _symbol):
        return ()

    def list_executions(self, _symbol):
        return ()


class LiveParityScopeGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = SQLiteStore.open(root / "commands.sqlite3")
        self.live_store = LiveAccountProjectionStore(root / "live.sqlite3")
        self.live_store.publish(LiveAccountSnapshot(
            ACCOUNT.value, "MAINNET", False, 1,
            Decimal("1000"), Decimal("1000"), Decimal("1000"),
            1000, (), (), 1000,
        ))
        self.manager = TradingAccountManager((TradingAccount(
            ACCOUNT, "Main", TradingAccountProvider.BYBIT,
            TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
        ),), active_account_id=ACCOUNT)
        self.adapter = MutationAdapter()

    def tearDown(self):
        self.store.close()
        self.live_store.close()
        self.temp.cleanup()

    def coordinator(self, *, protection=False, full_close=False):
        return LiveExecutionCoordinator(
            self.manager, self.store, lambda _account: self.adapter,
            read_adapter_provider=lambda _account: ReadAdapter(),
            instrument_provider=lambda _symbol: instrument(),
            live_account_store=self.live_store,
            writable_account_provider=lambda _account: True,
            gates=LiveParityMutationGates(
                protection_mutations_enabled=protection,
                full_close_mutations_enabled=full_close,
                mainnet_authorized=True,
            ),
            clock_ms=lambda: 1000,
        )

    def test_protection_gate_does_not_authorize_full_close(self):
        coordinator = self.coordinator(protection=True, full_close=False)
        protection = ProtectionCommandRequest(
            ClientActionId("stop"), "BTCUSDT", None, Decimal("48000"),
        )
        close = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")

        protection_result = coordinator.execute_protection(
            ACCOUNT.value, 1, "stop", lambda api: api.protection(protection),
        )
        close_result = coordinator.execute_full_close(
            ACCOUNT.value, 1, "close", lambda api: api.full_close(close),
        )

        self.assertEqual(protection_result.status.value, "accepted_pending")
        self.assertEqual(close_result.reason_code, "live_full_close_disabled")
        self.assertEqual([kind for kind, _ in self.adapter.calls], ["protection"])

    def test_full_close_gate_does_not_authorize_protection(self):
        coordinator = self.coordinator(protection=False, full_close=True)
        protection = ProtectionCommandRequest(
            ClientActionId("stop"), "BTCUSDT", None, Decimal("48000"),
        )
        close = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")

        protection_result = coordinator.execute_protection(
            ACCOUNT.value, 1, "stop", lambda api: api.protection(protection),
        )
        close_result = coordinator.execute_full_close(
            ACCOUNT.value, 1, "close", lambda api: api.full_close(close),
        )

        self.assertEqual(protection_result.reason_code, "live_protection_disabled")
        self.assertEqual(close_result.status.value, "accepted_pending")
        self.assertEqual([kind for kind, _ in self.adapter.calls], ["full_close"])

    def test_legacy_broad_execute_is_fail_closed(self):
        coordinator = self.coordinator(protection=True, full_close=True)
        close = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")

        result = coordinator.execute(
            ACCOUNT.value, 1, "close", lambda api: api.full_close(close),
        )

        self.assertEqual(result.reason_code, "live_mutations_disabled")
        self.assertEqual(self.adapter.calls, [])


if __name__ == "__main__":
    unittest.main()
