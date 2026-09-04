from __future__ import annotations

import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest import mock

from terminal.api.models import (
    AmendCommandRequest, CancelCommandRequest, ClientActionId, CommandResultStatus,
    FullCloseCommandRequest,
    LimitCommandRequest, ProtectionCommandRequest, TimeInForce, VolumeRequest, VolumeUnit,
)
from terminal.application.live_execution import LiveExecutionCoordinator, LiveParityMutationGates
from terminal.application.live_limit_acceptance import (
    LIVE_LIMIT_ACCEPTANCE_CAPABILITY, LiveLimitAcceptanceService,
    RuntimeProcessIdentity,
)
from terminal.application.trading_accounts import (
    TradingAccount, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import Category, OrderId, OrderSide, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import MutationDisposition, MutationKind, MutationOutcome
from terminal.exchange.events import (
    ExecutionEvent,
    InstrumentSnapshot, NormalizedOrderStatus, NormalizedOrderType,
    NormalizedPositionStatus, OrderEvent, PositionEvent,
)
from terminal.persistence.live_account_store import LiveAccountProjectionStore, LiveAccountSnapshot
from terminal.persistence.sqlite_store import (
    LiveLimitAcceptanceSessionRecord, LiveLimitAcceptanceState, PersistenceError,
    SQLiteStore,
)


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
    def __init__(self, outcome=None, raises=False):
        self.calls = []
        self.outcome = outcome
        self.raises = raises
        self.lock = threading.Lock()
    def _call(self, kind, payload):
        with self.lock:
            self.calls.append((kind, payload))
        if self.raises:
            raise TimeoutError("transport timeout")
        return self.outcome or MutationOutcome(
            kind, MutationDisposition.ACKNOWLEDGED,
            "exchange-new", payload.get("order_link_id"),
        )
    def create_market_order(self, **payload): return self._call(MutationKind.CREATE, payload)
    def create_limit_order(self, **payload): return self._call(MutationKind.CREATE, payload)
    def amend_order(self, **payload): return self._call(MutationKind.AMEND, payload)
    def cancel_order(self, **payload): return self._call(MutationKind.CANCEL, payload)
    def set_trading_stop(self, **payload): return self._call(MutationKind.PROTECTION, payload)


class ReadAdapter:
    def __init__(self, before_position=None, *, orders=None, executions=()):
        self.before_position = before_position
        self.orders = orders
        self.executions = executions
        self.calls = []
    def get_position(self, _symbol):
        self.calls.append("position")
        if self.before_position: self.before_position()
        return position()
    def list_active_orders(self, _symbol):
        self.calls.append("active_orders")
        return (order(),) if self.orders is None else self.orders
    def list_order_history(self, _symbol):
        self.calls.append("order_history")
        return ()
    def list_executions(self, _symbol):
        self.calls.append("executions")
        return self.executions


class LiveExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.root = root
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
        limit_ceiling="0", read_adapter=None, acceptance=None, store=None,
        live_store=None, adapter=None,
    ):
        return LiveExecutionCoordinator(
            self.manager, store or self.store, lambda _account: adapter or self.adapter,
            read_adapter_provider=lambda _account: read_adapter or ReadAdapter(),
            instrument_provider=lambda _symbol: instrument(),
            live_account_store=live_store or self.live_store,
            writable_account_provider=lambda _account: True,
            live_limit_acceptance=acceptance,
            gates=LiveParityMutationGates(
                parity_enabled, authorized, limit_enabled, Decimal(limit_ceiling),
            ), clock_ms=lambda: 1000,
        )

    def acceptance_service(self, store=None):
        owner = store or self.store
        return LiveLimitAcceptanceService(
            self.manager, owner, build_sha="test-build",
            process_identity=RuntimeProcessIdentity(
                "test-process", 500, os.getpid(), "test-host/test-deployment",
            ), writable_account_provider=lambda _: True,
        )

    def arm(self, store=None, *, session_id="acceptance", max_count=1,
            aggregate="100", generation=1):
        owner = store or self.store
        return owner.create_live_limit_acceptance_session(
            LiveLimitAcceptanceSessionRecord(
                session_id, ACCOUNT, "MAINNET", Symbol("BTCUSDT"),
                LIVE_LIMIT_ACCEPTANCE_CAPABILITY, LiveLimitAcceptanceState.ARMED,
                max_count, Decimal(aggregate), Decimal("100"), 0, Decimal("0"),
                500, 2000, "test-build", owner.database_identity,
                "CR-TRADING-WORKSPACE-001-r3.2/test", generation, 500,
            )
        )

    def limit_request(self, action_id="limit-1", amount="100"):
        return LimitCommandRequest(
            ClientActionId(action_id), "BTCUSDT", OrderSide.BUY,
            VolumeRequest(VolumeUnit.USDT, Decimal(amount)), Decimal("50000"),
            Decimal("49000"), TimeInForce.GTC,
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

    def test_limit_amend_cancel_without_acceptance_service_fails_closed(self):
        coordinator = self.coordinator(parity_enabled=False, limit_enabled=True)
        amend = lambda api: api.amend(AmendCommandRequest(
            ClientActionId("amend-limit"), "BTCUSDT", order_id="exchange-limit",
            changed_price=Decimal("48500"),
        ))
        cancel = lambda api: api.cancel(CancelCommandRequest(
            ClientActionId("cancel-limit"), "BTCUSDT", order_id="exchange-limit",
        ))
        amended = coordinator.execute_limit_amend(
            ACCOUNT.value, 1, AmendCommandRequest(
                ClientActionId("amend-limit"), "BTCUSDT", order_id="exchange-limit",
                changed_price=Decimal("48500"),
            ),
        )
        stale = coordinator.execute_limit_cancel(
            ACCOUNT.value, 2, CancelCommandRequest(
                ClientActionId("cancel-limit"), "BTCUSDT", order_id="exchange-limit",
            ),
        )
        self.assertEqual(
            amended.reason_code, "live_limit_amend_cancel_durable_ownership_required",
        )
        self.assertEqual(
            stale.reason_code, "stale_account_session",
        )
        self.assertEqual(self.adapter.calls, [])

    def test_durable_limit_create_replay_uses_one_persisted_identity_and_one_attempt(self):
        self.arm()
        service = self.acceptance_service()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=service,
        )
        first = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        second = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        self.assertEqual(first.status.value, "accepted_pending")
        self.assertEqual(second.command_id, first.command_id)
        self.assertEqual(len(self.adapter.calls), 1)
        action = self.store.load_unresolved_live_limit_actions()[0]
        self.assertEqual(self.adapter.calls[0][1]["order_link_id"], action.order_link_id)
        self.assertEqual(action.outcome_disposition, "acknowledged")
        self.assertEqual(action.exchange_order_id, OrderId("exchange-new"))

    def test_distinct_identity_is_blocked_before_second_adapter_attempt(self):
        self.arm()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(),
        )
        coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request("first"))
        second = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request("second"))
        self.assertEqual(second.status.value, "blocked")
        self.assertEqual(len(self.adapter.calls), 1)

    def test_timeout_becomes_unknown_and_replay_never_redispatches(self):
        self.adapter = MutationAdapter(raises=True)
        self.arm()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(), adapter=self.adapter,
        )
        first = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        replay = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        self.assertEqual(first.status.value, "unknown")
        self.assertEqual(replay.status.value, "unknown")
        self.assertEqual(len(self.adapter.calls), 1)
        action = self.store.load_unresolved_live_limit_actions()[0]
        self.assertEqual(action.dispatch_state, "UNKNOWN")
        self.assertEqual(action.outcome_disposition, "unknown")

    def test_deterministic_rejection_is_persisted_without_retry(self):
        self.adapter = MutationAdapter(MutationOutcome(
            MutationKind.CREATE, MutationDisposition.REJECTED,
            reject_code=110003, reason="price outside allowed range",
        ))
        self.arm()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(), adapter=self.adapter,
        )
        first = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        replay = coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        self.assertEqual(first.status.value, "rejected")
        self.assertEqual(replay.status.value, "rejected")
        self.assertEqual(len(self.adapter.calls), 1)
        action = self.store.get_live_limit_action("acceptance", ACCOUNT, 1, "limit-1")
        self.assertEqual(action.outcome_disposition, "rejected")
        self.assertEqual(action.outcome_code, 110003)
        self.assertEqual(action.reconciliation_state, "RESOLVED")

    def _evidence_order(self, link, *, order_id="exchange-new", status=NormalizedOrderStatus.OPEN,
                        filled="0", leaves="0.002"):
        return OrderEvent(
            ACCOUNT, Category.LINEAR, "BTCUSDT", OrderId(order_id), link, 0,
            OrderSide.BUY, NormalizedOrderType.LIMIT, "Limit", Decimal("49000"),
            Decimal("0.002"), Decimal(filled), Decimal(leaves),
            Decimal("49000") if Decimal(filled) else None, status, status.value,
            False, False, None, None, None, None, None, 1000, 1100,
        )

    def _execution(self, link, exec_id, quantity="0.001"):
        from terminal.domain.models import ExecutionId
        return ExecutionEvent(
            ACCOUNT, Category.LINEAR, "BTCUSDT", ExecutionId(exec_id),
            OrderId("exchange-new"), link, OrderSide.BUY, Decimal("49000"),
            Decimal(quantity), Decimal("-0.001"),
            Decimal("49"), False, 1100, None,
        )

    def _unknown_action(self):
        self.adapter = MutationAdapter(raises=True)
        self.arm()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(), adapter=self.adapter,
        )
        coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        return self.store.load_unresolved_live_limit_actions()[0]

    def _owned_order_coordinator(self, *, operation_adapter=None, price="49000"):
        self.arm()
        service = self.acceptance_service()
        self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=service,
        ).execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        action = self.store.load_unresolved_live_limit_actions()[0]
        evidence = self._evidence_order(action.order_link_id)
        if price != "49000":
            evidence = OrderEvent(
                evidence.trading_account_id, evidence.category, evidence.symbol,
                evidence.order_id, evidence.order_link_id, evidence.position_idx,
                evidence.side, evidence.order_type, evidence.raw_order_type,
                Decimal(price), evidence.quantity, evidence.cumulative_filled_quantity,
                evidence.leaves_quantity, evidence.average_price, evidence.status,
                evidence.raw_status, evidence.reduce_only, evidence.close_on_trigger,
                evidence.stop_order_type, evidence.trigger_price, evidence.take_profit,
                evidence.stop_loss, evidence.tpsl_mode, evidence.created_at_ms,
                evidence.updated_at_ms,
            )
        read = ReadAdapter(orders=(evidence,))
        self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=read,
        ).recover_unresolved(ACCOUNT)
        self.adapter.calls.clear()
        return self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=service, read_adapter=read,
            adapter=operation_adapter or self.adapter,
        ), action, read

    def test_owned_non_increasing_amend_is_single_attempt_and_replay_safe(self):
        coordinator, action, _ = self._owned_order_coordinator()
        request = AmendCommandRequest(
            ClientActionId("amend-owned"), "BTCUSDT",
            order_id="exchange-new", changed_price=Decimal("48000"),
        )
        first = coordinator.execute_limit_amend(ACCOUNT.value, 1, request)
        replay = coordinator.execute_limit_amend(ACCOUNT.value, 1, request)
        self.assertEqual(first.status, CommandResultStatus.ACCEPTED_PENDING)
        self.assertEqual(replay.command_id, first.command_id)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.adapter.calls[0][0], MutationKind.AMEND)
        self.assertEqual(self.adapter.calls[0][1]["order_id"], "exchange-new")
        self.assertIsNone(self.adapter.calls[0][1]["order_link_id"])
        operation = self.store.get_live_limit_operation(
            action.acceptance_session_id, ACCOUNT, 1, "amend-owned",
        )
        self.assertEqual(operation.parent_order_link_id, action.order_link_id)

    def test_exposure_increase_quantity_change_and_unowned_targets_are_zero_dispatch(self):
        coordinator, _, _ = self._owned_order_coordinator()
        cases = (
            AmendCommandRequest(ClientActionId("increase"), "BTCUSDT",
                                order_id="exchange-new", changed_price=Decimal("51000")),
            AmendCommandRequest(ClientActionId("quantity"), "BTCUSDT",
                                order_id="exchange-new", resulting_total_quantity=Decimal("0.003")),
            AmendCommandRequest(ClientActionId("unowned"), "BTCUSDT",
                                order_id="exchange-limit", changed_price=Decimal("48000")),
        )
        for request in cases:
            result = coordinator.execute_limit_amend(ACCOUNT.value, 1, request)
            self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        cancel = coordinator.execute_limit_cancel(
            ACCOUNT.value, 1, CancelCommandRequest(
                ClientActionId("unowned-cancel"), "BTCUSDT", order_id="exchange-limit",
            ),
        )
        self.assertEqual(cancel.status, CommandResultStatus.BLOCKED)
        self.assertEqual(self.adapter.calls, [])

    def test_same_operation_identity_different_fingerprint_is_rejected(self):
        coordinator, _, _ = self._owned_order_coordinator()
        coordinator.execute_limit_amend(ACCOUNT.value, 1, AmendCommandRequest(
            ClientActionId("amend-same"), "BTCUSDT", order_id="exchange-new",
            changed_price=Decimal("48000"),
        ))
        changed = coordinator.execute_limit_amend(ACCOUNT.value, 1, AmendCommandRequest(
            ClientActionId("amend-same"), "BTCUSDT", order_id="exchange-new",
            changed_price=Decimal("47000"),
        ))
        self.assertEqual(changed.status, CommandResultStatus.BLOCKED)
        self.assertEqual(len(self.adapter.calls), 1)

    def test_ambiguous_amend_is_unknown_and_restart_reconciliation_is_read_only(self):
        ambiguous = MutationAdapter(raises=True)
        coordinator, action, _ = self._owned_order_coordinator(operation_adapter=ambiguous)
        request = AmendCommandRequest(
            ClientActionId("amend-unknown"), "BTCUSDT", order_id="exchange-new",
            changed_price=Decimal("48000"),
        )
        first = coordinator.execute_limit_amend(ACCOUNT.value, 1, request)
        replay = coordinator.execute_limit_amend(ACCOUNT.value, 1, request)
        self.assertEqual((first.status, replay.status),
                         (CommandResultStatus.UNKNOWN, CommandResultStatus.UNKNOWN))
        self.assertEqual(len(ambiguous.calls), 1)
        amended_evidence = self._evidence_order(action.order_link_id)
        amended_evidence = OrderEvent(
            amended_evidence.trading_account_id, amended_evidence.category,
            amended_evidence.symbol, amended_evidence.order_id,
            amended_evidence.order_link_id, amended_evidence.position_idx,
            amended_evidence.side, amended_evidence.order_type,
            amended_evidence.raw_order_type, Decimal("48000"),
            amended_evidence.quantity, amended_evidence.cumulative_filled_quantity,
            amended_evidence.leaves_quantity, amended_evidence.average_price,
            amended_evidence.status, amended_evidence.raw_status,
            amended_evidence.reduce_only, amended_evidence.close_on_trigger,
            amended_evidence.stop_order_type, amended_evidence.trigger_price,
            amended_evidence.take_profit, amended_evidence.stop_loss,
            amended_evidence.tpsl_mode, amended_evidence.created_at_ms,
            amended_evidence.updated_at_ms,
        )
        self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=ReadAdapter(orders=(amended_evidence,)), adapter=ambiguous,
        ).recover_unresolved(ACCOUNT)
        operation = self.store.get_live_limit_operation("acceptance", ACCOUNT, 1, "amend-unknown")
        self.assertEqual(operation.reconciliation_state, "RESOLVED")
        self.assertEqual(len(ambiguous.calls), 1)

    def test_owned_cancel_is_single_attempt_and_does_not_rearm_capacity(self):
        coordinator, action, _ = self._owned_order_coordinator()
        session_before = self.store.get_live_limit_acceptance_session(
            "acceptance", ACCOUNT, "MAINNET", Symbol("BTCUSDT"),
            LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        request = CancelCommandRequest(
            ClientActionId("cancel-owned"), "BTCUSDT", order_id="exchange-new",
        )
        first = coordinator.execute_limit_cancel(ACCOUNT.value, 1, request)
        replay = coordinator.execute_limit_cancel(ACCOUNT.value, 1, request)
        session_after = self.store.get_live_limit_acceptance_session(
            "acceptance", ACCOUNT, "MAINNET", Symbol("BTCUSDT"),
            LIVE_LIMIT_ACCEPTANCE_CAPABILITY,
        )
        self.assertEqual(first.status, CommandResultStatus.ACCEPTED_PENDING)
        self.assertEqual(replay.command_id, first.command_id)
        self.assertEqual(len(self.adapter.calls), 1)
        self.assertEqual(self.adapter.calls[0][0], MutationKind.CANCEL)
        self.assertEqual(
            (session_after.state, session_after.reserved_count, session_after.reserved_notional),
            (session_before.state, session_before.reserved_count, session_before.reserved_notional),
        )

    def test_ambiguous_cancel_reconciles_read_only_without_retry(self):
        ambiguous = MutationAdapter(raises=True)
        coordinator, action, _ = self._owned_order_coordinator(operation_adapter=ambiguous)
        request = CancelCommandRequest(
            ClientActionId("cancel-unknown"), "BTCUSDT", order_id="exchange-new",
        )
        result = coordinator.execute_limit_cancel(ACCOUNT.value, 1, request)
        self.assertEqual(result.status, CommandResultStatus.UNKNOWN)
        cancelled = self._evidence_order(
            action.order_link_id, status=NormalizedOrderStatus.CANCELLED,
            leaves="0",
        )
        self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=ReadAdapter(orders=(cancelled,)), adapter=ambiguous,
        ).recover_unresolved(ACCOUNT)
        operation = self.store.get_live_limit_operation(
            "acceptance", ACCOUNT, 1, "cancel-unknown",
        )
        self.assertEqual(operation.reconciliation_state, "RESOLVED")
        self.assertEqual(self.store.get_command(operation.command_id).current_state,
                         CommandState.CANCELLED)
        self.assertEqual(len(ambiguous.calls), 1)

    def test_operation_provenance_mismatch_and_persistence_failure_are_zero_dispatch(self):
        coordinator, _, read = self._owned_order_coordinator()
        mismatched = LiveLimitAcceptanceService(
            self.manager, self.store, build_sha="different-build",
            process_identity=RuntimeProcessIdentity(
                "other-process", 500, os.getpid(), "test-host/test-deployment",
            ), writable_account_provider=lambda _: True,
        )
        result = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=mismatched, read_adapter=read,
        ).execute_limit_cancel(
            ACCOUNT.value, 1, CancelCommandRequest(
                ClientActionId("cancel-mismatch"), "BTCUSDT", order_id="exchange-new",
            ),
        )
        self.assertEqual(result.status, CommandResultStatus.BLOCKED)
        self.assertEqual(self.adapter.calls, [])
        with mock.patch.object(
            self.store, "admit_live_limit_operation", side_effect=PersistenceError("failed"),
        ):
            failed = coordinator.execute_limit_cancel(
                ACCOUNT.value, 1, CancelCommandRequest(
                    ClientActionId("cancel-persistence"), "BTCUSDT",
                    order_id="exchange-new",
                ),
            )
        self.assertEqual(failed.status, CommandResultStatus.BLOCKED)
        self.assertEqual(self.adapter.calls, [])

    def test_restart_unknown_uses_read_only_reconciliation_and_original_order_link(self):
        action = self._unknown_action()
        mutation_calls = len(self.adapter.calls)
        evidence = self._evidence_order(action.order_link_id)
        read = ReadAdapter(orders=(evidence,))
        self.store.close()
        self.store = SQLiteStore.open(self.root / "commands.sqlite3")
        restarted = self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=read, acceptance=None, adapter=self.adapter,
        )
        restarted.recover_unresolved(ACCOUNT)
        resolved = self.store.get_live_limit_action("acceptance", ACCOUNT, 1, "limit-1")
        self.assertEqual(resolved.reconciliation_state, "RESOLVED")
        self.assertEqual(resolved.exchange_order_id, OrderId("exchange-new"))
        self.assertEqual(len(self.adapter.calls), mutation_calls)
        self.assertEqual(read.calls, ["active_orders", "order_history", "executions"])

    def test_reconciliation_deduplicates_exec_ids(self):
        action = self._unknown_action()
        first = self._execution(action.order_link_id, "exec-1")
        second = self._execution(action.order_link_id, "exec-2")
        read = ReadAdapter(
            orders=(), executions=(first, first, second),
        )
        restarted = self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=read, adapter=self.adapter,
        )
        restarted.recover_unresolved(ACCOUNT)
        self.assertEqual(len(self.store.load_executions()), 2)
        self.assertEqual(len(self.adapter.calls), 1)
        command = self.store.get_command(action.command_id)
        self.assertEqual(command.current_state, CommandState.FILLED)

    def test_no_exchange_evidence_remains_unknown_and_locks_session(self):
        self._unknown_action()
        read = ReadAdapter(orders=(), executions=())
        restarted = self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=read, adapter=self.adapter,
        )
        restarted.recover_unresolved(ACCOUNT)
        action = self.store.get_live_limit_action("acceptance", ACCOUNT, 1, "limit-1")
        self.assertEqual((action.dispatch_state, action.reconciliation_state), ("UNKNOWN", "REQUIRED"))
        self.assertEqual(len(self.adapter.calls), 1)

    def test_acknowledged_without_authoritative_evidence_becomes_unknown(self):
        self.arm()
        coordinator = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(),
        )
        coordinator.execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        mutation_calls = len(self.adapter.calls)
        read_only = ReadAdapter(orders=(), executions=())
        self.coordinator(
            parity_enabled=False, limit_enabled=False, authorized=False,
            read_adapter=read_only,
        ).recover_unresolved(ACCOUNT)
        action = self.store.get_live_limit_action("acceptance", ACCOUNT, 1, "limit-1")
        self.assertEqual((action.dispatch_state, action.reconciliation_state), ("UNKNOWN", "REQUIRED"))
        self.assertEqual(len(self.adapter.calls), mutation_calls)
        blocked = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=self.acceptance_service(), adapter=self.adapter,
        ).execute_limit_create(ACCOUNT.value, 1, self.limit_request("distinct"))
        self.assertEqual(blocked.status.value, "blocked")
        self.assertEqual(len(self.adapter.calls), 1)

    def test_provenance_mismatch_blocks_before_adapter(self):
        self.arm()
        mismatched = LiveLimitAcceptanceService(
            self.manager, self.store, build_sha="different-build",
            process_identity=RuntimeProcessIdentity(
                "other-process", 500, os.getpid(), "test-host/test-deployment",
            ), writable_account_provider=lambda _: True,
        )
        result = self.coordinator(
            parity_enabled=False, limit_enabled=True, limit_ceiling="100",
            acceptance=mismatched,
        ).execute_limit_create(ACCOUNT.value, 1, self.limit_request())
        self.assertEqual(result.status.value, "blocked")
        self.assertEqual(self.adapter.calls, [])

    def test_concurrent_same_identity_has_one_dispatch_and_one_adapter_call(self):
        self.arm()
        self.store.close()
        shared_adapter = MutationAdapter()

        def worker(_):
            store = SQLiteStore.open(self.root / "commands.sqlite3", busy_timeout_ms=5000)
            live_store = LiveAccountProjectionStore(self.root / "live.sqlite3")
            try:
                service = self.acceptance_service(store)
                coordinator = self.coordinator(
                    parity_enabled=False, limit_enabled=True, limit_ceiling="100",
                    acceptance=service, store=store, live_store=live_store,
                    adapter=shared_adapter,
                )
                return coordinator.execute_limit_create(
                    ACCOUNT.value, 1, self.limit_request("concurrent"),
                )
            finally:
                live_store.close()
                store.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(worker, range(2)))
        self.store = SQLiteStore.open(self.root / "commands.sqlite3")
        self.assertEqual(len(shared_adapter.calls), 1)
        self.assertEqual(len({result.command_id for result in results}), 1)
        action = self.store.get_live_limit_action("acceptance", ACCOUNT, 1, "concurrent")
        history = self.store.load_command_history(action.command_id)
        self.assertEqual(
            sum(item.next_state is CommandState.SUBMITTING for item in history), 1,
        )


if __name__ == "__main__":
    unittest.main()
