from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.api.models import (
    AmendCommandRequest, CancelCommandRequest, ClientActionId, FullCloseCommandRequest,
    LimitCommandRequest, ProtectionCommandRequest, TimeInForce, VolumeRequest, VolumeUnit,
)
from terminal.application.live_execution import LiveExecutionCoordinator, LiveParityMutationGates
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import Category, OrderId, OrderSide, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition, MutationKind, MutationOutcome
from terminal.exchange.events import (
    InstrumentSnapshot, NormalizedOrderStatus, NormalizedOrderType,
    NormalizedPositionStatus, OrderEvent, PositionEvent,
)
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT = TradingAccountId("bybit-main")
OTHER_ACCOUNT = TradingAccountId("bybit-other")


def instrument():
    return InstrumentSnapshot(
        Category.LINEAR, "BTCUSDT", "LinearPerpetual", "Trading", "BTC", "USDT", "USDT",
        Decimal("1"), Decimal("1000000"), Decimal("0.5"), Decimal("0.001"),
        Decimal("100"), Decimal("50"), Decimal("0.001"), Decimal("5"),
    )


def position(side=PositionSide.LONG, size=Decimal("0.01")):
    return PositionEvent(
        PositionKey(ACCOUNT, Category.LINEAR, Symbol("BTCUSDT"), 0), side, size,
        Decimal("50000"), Decimal("50000"), Decimal("500"), Decimal("0"),
        Decimal("0"), Decimal("0"), NormalizedPositionStatus.NORMAL, "Normal",
        None, None, None, None, 1000,
    )


def order():
    return OrderEvent(
        ACCOUNT, Category.LINEAR, "BTCUSDT", OrderId("exchange-limit"), "existing-link", 0,
        OrderSide.BUY, NormalizedOrderType.LIMIT, "Limit", Decimal("49000"), Decimal("0.01"),
        Decimal("0"), Decimal("0.01"), None, NormalizedOrderStatus.OPEN, "New", False, False,
        None, None, None, None, None, 1, 1000,
    )


class MutationAdapter:
    def __init__(self): self.calls = []
    def _call(self, kind, payload):
        self.calls.append((kind, payload))
        return MutationOutcome(kind, MutationDisposition.ACKNOWLEDGED, "exchange-new", payload.get("order_link_id"))
    def create_market_order(self, **payload): return self._call(MutationKind.CREATE, payload)
    def create_limit_order(self, **payload): return self._call(MutationKind.CREATE, payload)
    def amend_order(self, **payload): return self._call(MutationKind.AMEND, payload)
    def cancel_order(self, **payload): return self._call(MutationKind.CANCEL, payload)
    def set_trading_stop(self, **payload): return self._call(MutationKind.PROTECTION, payload)


class ReadAdapter:
    def __init__(self, before_position=None): self.before_position = before_position
    def get_position(self, _symbol):
        if self.before_position: self.before_position()
        return position()
    def list_active_orders(self, _symbol): return (order(),)
    def list_order_history(self, _symbol): return ()


class LiveExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = SQLiteStore.open(root / "commands.sqlite3")
        self.live_store = LiveAccountProjectionStore(root / "live.sqlite3")
        self.live_store.publish(LiveAccountSnapshot(
            ACCOUNT.value, "MAINNET", False, 1, Decimal("1000"), Decimal("1000"),
            Decimal("1000"), 1000, (), (), 1000,
        ))
        self.manager = TradingAccountManager((
            TradingAccount(
                ACCOUNT, "Main", TradingAccountProvider.BYBIT,
                TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
            ),
            TradingAccount(
                OTHER_ACCOUNT, "Other", TradingAccountProvider.BYBIT,
                TradingAccountEnvironment.MAINNET, TradingAccountStatus.READY,
            ),
        ), active_account_id=ACCOUNT)
        self.adapter = MutationAdapter()

    def tearDown(self):
        self.store.close(); self.live_store.close(); self.temp.cleanup()

    def coordinator(
        self, *, parity_enabled=True, limit_enabled=False, authorized=True,
        limit_ceiling="0", read_adapter=None,
    ):
        return LiveExecutionCoordinator(
            self.manager, self.store, lambda _account: self.adapter,
            read_adapter_provider=lambda _account: read_adapter or ReadAdapter(),
            instrument_provider=lambda _symbol: instrument(), live_account_store=self.live_store,
            writable_account_provider=lambda _account: True,
            gates=LiveParityMutationGates(
                parity_enabled, authorized, limit_enabled, Decimal(limit_ceiling),
            ), clock_ms=lambda: 1000,
        )

    def test_limit_create_cannot_reach_adapter_before_durable_admission_wiring(self):
        request = LimitCommandRequest(
            ClientActionId("limit-1"), "BTCUSDT", OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, Decimal("100")), Decimal("50000"),
            Decimal("49000"), TimeInForce.GTC,
        )
        result = self.coordinator(limit_enabled=True, limit_ceiling="100").execute_limit_create(
            ACCOUNT.value, 1, request,
        )
        self.assertEqual(result.status.value, "blocked")
        self.assertEqual(result.reason_code, "live_limit_durable_admission_required")
        self.assertEqual(self.adapter.calls, [])
        self.assertEqual(self.store.load_unfinished_commands(), ())

        replay = self.coordinator(limit_enabled=True, limit_ceiling="100").execute_limit_create(
            ACCOUNT.value, 1, request,
        )
        self.assertEqual(replay.reason_code, "live_limit_durable_admission_required")
        self.assertEqual(self.adapter.calls, [])

    def test_stale_session_and_default_off_gates_are_zero_dispatch(self):
        request = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")
        self.assertEqual(
            self.coordinator(parity_enabled=False).execute(ACCOUNT.value, 1, "close", lambda api: api.full_close(request)).reason_code,
            "live_mutations_disabled",
        )
        self.assertEqual(
            self.coordinator().execute(ACCOUNT.value, 2, "close", lambda api: api.full_close(request)).reason_code,
            "stale_account_session",
        )
        self.assertEqual(self.adapter.calls, [])

    def test_full_close_is_reduce_only(self):
        request = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")
        result = self.coordinator().execute(ACCOUNT.value, 1, "close", lambda api: api.full_close(request))
        self.assertEqual(result.status.value, "accepted_pending")
        self.assertTrue(self.adapter.calls[0][1]["reduce_only"])
        self.assertEqual(self.adapter.calls[0][1]["qty"], Decimal("0.01"))

    def test_session_change_during_fresh_read_blocks_before_adapter(self):
        request = FullCloseCommandRequest(ClientActionId("close"), "BTCUSDT")
        read = ReadAdapter(before_position=lambda: self.manager.activate(OTHER_ACCOUNT))
        result = self.coordinator(read_adapter=read).execute(
            ACCOUNT.value, 1, "close", lambda api: api.full_close(request),
        )
        self.assertEqual(result.status.value, "unavailable")
        self.assertEqual(self.adapter.calls, [])

    def test_limit_amend_cancel_and_stop_take_use_existing_application_paths(self):
        cases = (
            ("amend", lambda api: api.amend(AmendCommandRequest(
                ClientActionId("amend"), "BTCUSDT", order_id="exchange-limit", changed_price=Decimal("48500")))),
            ("cancel", lambda api: api.cancel(CancelCommandRequest(
                ClientActionId("cancel"), "BTCUSDT", order_id="exchange-limit"))),
            ("stop", lambda api: api.protection(ProtectionCommandRequest(
                ClientActionId("stop"), "BTCUSDT", None, Decimal("48000")))),
            ("take", lambda api: api.protection(ProtectionCommandRequest(
                ClientActionId("take"), "BTCUSDT", Decimal("52000"), None))),
        )
        for expected, action in cases:
            with self.subTest(expected):
                self.store.close()
                self.store = SQLiteStore.open(Path(self.temp.name) / f"{expected}.sqlite3")
                self.adapter.calls.clear()
                result = self.coordinator().execute(ACCOUNT.value, 1, expected, action)
                self.assertEqual(result.status.value, "accepted_pending")
                self.assertEqual(len(self.adapter.calls), 1)

    def test_limit_defaults_reject_without_dispatch(self):
        request = LimitCommandRequest(
            ClientActionId("limit-off"), "BTCUSDT", OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, Decimal("10")), Decimal("50000"),
            Decimal("49000"), TimeInForce.GTC,
        )
        result = self.coordinator(parity_enabled=False).execute_limit_create(ACCOUNT.value, 1, request)
        self.assertEqual(result.reason_code, "live_limit_disabled")
        self.assertEqual(self.adapter.calls, [])

    def test_limit_gate_does_not_enable_parity_mutations(self):
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="10",
        )
        actions = (
            ("close", lambda api: api.full_close(FullCloseCommandRequest(
                ClientActionId("close"), "BTCUSDT"))),
            ("stop", lambda api: api.protection(ProtectionCommandRequest(
                ClientActionId("stop"), "BTCUSDT", None, Decimal("48000")))),
            ("take", lambda api: api.protection(ProtectionCommandRequest(
                ClientActionId("take"), "BTCUSDT", Decimal("52000"), None))),
        )
        for action_id, action in actions:
            with self.subTest(action_id):
                result = coordinator.execute(ACCOUNT.value, 1, action_id, action)
                self.assertEqual(result.reason_code, "live_mutations_disabled")
        self.assertEqual(self.adapter.calls, [])

    def test_limit_create_enforces_positive_acceptance_ceiling(self):
        def request(action_id, amount):
            return LimitCommandRequest(
                ClientActionId(action_id), "BTCUSDT", OrderSide.BUY,
                VolumeRequest(VolumeUnit.USDT, Decimal(amount)), Decimal("50000"),
                Decimal("49000"), TimeInForce.GTC,
            )

        disabled = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="0",
        ).execute_limit_create(ACCOUNT.value, 1, request("zero", "1"))
        above = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
        ).execute_limit_create(ACCOUNT.value, 1, request("above", "100.01"))
        accepted = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
        ).execute_limit_create(ACCOUNT.value, 1, request("at", "100"))
        self.assertEqual(disabled.reason_code, "live_limit_acceptance_notional_exceeded")
        self.assertEqual(above.reason_code, "live_limit_acceptance_notional_exceeded")
        self.assertEqual(accepted.reason_code, "live_limit_durable_admission_required")
        self.assertEqual(self.adapter.calls, [])

    def test_limit_amend_cancel_use_limit_gate_and_session_fence(self):
        coordinator = self.coordinator(parity_enabled=False, limit_enabled=True)
        amend = lambda api: api.amend(AmendCommandRequest(
            ClientActionId("amend-limit"), "BTCUSDT", order_id="exchange-limit",
            changed_price=Decimal("48500"),
        ))
        cancel = lambda api: api.cancel(CancelCommandRequest(
            ClientActionId("cancel-limit"), "BTCUSDT", order_id="exchange-limit",
        ))
        amended = coordinator.execute_limit_amend_cancel(
            ACCOUNT.value, 1, "amend-limit", amend,
        )
        stale = coordinator.execute_limit_amend_cancel(
            ACCOUNT.value, 2, "cancel-limit", cancel,
        )
        self.assertEqual(amended.status.value, "accepted_pending")
        self.assertEqual(stale.reason_code, "stale_account_session")
        self.assertEqual(len(self.adapter.calls), 1)


if __name__ == "__main__":
    unittest.main()
