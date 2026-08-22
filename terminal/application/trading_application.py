"""Single Stage 5 orchestration entry point for manual order mutations."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.normalization import floor_to_step, normalize_limit_price
from terminal.application.pretrade_guard import (
    AdmittedPreTradeRequest,
    OrderKind,
    PreTradeContext,
    PreTradeDecision,
    PreTradeGuard,
    PreTradeIntent,
)
from terminal.domain.models import (
    Category, Controller, Notional, OrderSide, Origin, Price, Quantity, Symbol,
    TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import BybitV5MutationAdapter, MutationOutcome
from terminal.exchange.events import InstrumentSnapshot, OrderEvent
from terminal.persistence.sqlite_store import CommandRecord, SQLiteStore


class ApplicationMutationsDisabled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AmendIntent:
    trading_account_id: TradingAccountId
    symbol: str
    side: OrderSide
    instrument: InstrumentSnapshot
    current_order: OrderEvent
    order_id: str | None = None
    order_link_id: str | None = None
    resulting_total_quantity: Decimal | None = None
    changed_price: Decimal | None = None


@dataclass(frozen=True, slots=True)
class CancelIntent:
    trading_account_id: TradingAccountId
    symbol: str
    side: OrderSide
    current_order: OrderEvent
    order_id: str | None = None
    order_link_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApplicationResult:
    decision: PreTradeDecision | None
    command: CommandRecord | None
    outcome: MutationOutcome | None


@dataclass(slots=True)
class TradingApplication:
    guard: PreTradeGuard
    store: SQLiteStore
    adapter: BybitV5MutationAdapter
    execution_engine: ExecutionEngine
    mutations_enabled: bool = False
    identity_factory: CommandIdentityFactory = field(default_factory=CommandIdentityFactory)
    clock_ms: Callable[[], int] = field(default=lambda: int(time.time() * 1000))

    def submit(self, intent: PreTradeIntent, context: PreTradeContext) -> ApplicationResult:
        self._require_enabled()
        decision = self.guard.evaluate(intent, context)
        if not decision.admitted:
            return ApplicationResult(decision, None, None)
        request = decision.request
        assert request is not None
        command = self._persist_submitting(self._create_record(request))
        outcome = self._create(request)
        resolved = self.execution_engine.ingest_mutation_outcome(
            command, outcome, occurred_at_ms=self.clock_ms()
        )
        return ApplicationResult(decision, resolved, outcome)

    def amend(self, intent: AmendIntent) -> ApplicationResult:
        self._require_enabled()
        _validate_scope(intent.trading_account_id, intent.symbol, intent.current_order)
        order_id, link_id = _selected_identity(intent.order_id, intent.order_link_id)
        _validate_selected_order_identity(intent.current_order, order_id, link_id)
        quantity = _normalized_amend_quantity(intent)
        price = _normalized_amend_price(intent)
        if quantity is None and price is None:
            raise ValueError("amend requires qty and/or price")
        identity = self.identity_factory.create()
        now = self.clock_ms()
        record = CommandRecord(
            command_id=identity.command_id, order_link_id=identity.order_link_id,
            trading_account_id=intent.trading_account_id, category=Category.LINEAR,
            symbol=Symbol(intent.symbol), position_idx=0, command_kind="amend",
            side=intent.side, requested_notional=Notional(Decimal("0")),
            normalized_price=Price(price) if price is not None else None,
            normalized_quantity=Quantity(quantity) if quantity is not None else None,
            origin=Origin.TERMINAL_MANUAL, controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED, version=1, exchange_order_id=None,
            created_at_ms=now, updated_at_ms=now,
        )
        command = self._persist_submitting(record)
        outcome = self.adapter.amend_order(
            symbol=intent.symbol, order_id=order_id, order_link_id=link_id,
            qty=quantity, price=price,
        )
        resolved = self.execution_engine.ingest_mutation_outcome(
            command, outcome, occurred_at_ms=self.clock_ms()
        )
        return ApplicationResult(None, resolved, outcome)

    def cancel(self, intent: CancelIntent) -> ApplicationResult:
        self._require_enabled()
        _validate_scope(intent.trading_account_id, intent.symbol, intent.current_order)
        order_id, link_id = _selected_identity(intent.order_id, intent.order_link_id)
        _validate_selected_order_identity(intent.current_order, order_id, link_id)
        identity = self.identity_factory.create()
        now = self.clock_ms()
        record = CommandRecord(
            command_id=identity.command_id, order_link_id=identity.order_link_id,
            trading_account_id=intent.trading_account_id, category=Category.LINEAR,
            symbol=Symbol(intent.symbol), position_idx=0, command_kind="cancel",
            side=intent.side, requested_notional=Notional(Decimal("0")),
            normalized_price=None, normalized_quantity=None,
            origin=Origin.TERMINAL_MANUAL, controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED, version=1, exchange_order_id=None,
            created_at_ms=now, updated_at_ms=now,
        )
        command = self._persist_submitting(record)
        outcome = self.adapter.cancel_order(
            symbol=intent.symbol, order_id=order_id, order_link_id=link_id,
        )
        resolved = self.execution_engine.ingest_mutation_outcome(
            command, outcome, occurred_at_ms=self.clock_ms()
        )
        return ApplicationResult(None, resolved, outcome)

    def _require_enabled(self) -> None:
        if not self.mutations_enabled:
            raise ApplicationMutationsDisabled("TradingApplication mutations are disabled")

    def _persist_submitting(self, record: CommandRecord) -> CommandRecord:
        eligibility = self.store.persist_command_before_submit(record)
        return self.store.transition_command_state(
            eligibility.command_id, CommandState.ADMITTED, CommandState.SUBMITTING,
            expected_version=eligibility.committed_version,
            reason="single mutation attempt durably started", occurred_at_ms=self.clock_ms(),
        )

    def _create_record(self, request: AdmittedPreTradeRequest) -> CommandRecord:
        now = self.clock_ms()
        return CommandRecord(
            command_id=request.identity.command_id, order_link_id=request.identity.order_link_id,
            trading_account_id=request.trading_account_id, category=request.category,
            symbol=Symbol(request.symbol), position_idx=request.position_idx,
            command_kind=f"create_{request.order_kind.value}", side=request.side,
            requested_notional=Notional(request.requested_notional),
            normalized_price=(Price(request.normalized_limit_price)
                              if request.normalized_limit_price is not None else None),
            normalized_quantity=Quantity(request.final_quantity),
            origin=Origin.TERMINAL_MANUAL, controller=Controller.MANUAL,
            current_state=CommandState.ADMITTED, version=1, exchange_order_id=None,
            created_at_ms=now, updated_at_ms=now,
        )

    def _create(self, request: AdmittedPreTradeRequest) -> MutationOutcome:
        common = dict(
            symbol=request.symbol, side=request.side.value, qty=request.final_quantity,
            order_link_id=request.identity.order_link_id,
        )
        if request.order_kind is OrderKind.MARKET:
            assert request.slippage is not None
            return self.adapter.create_market_order(
                **common, reduce_only=request.reduce_only,
                slippage_tolerance_type=request.slippage.tolerance_type.value,
                slippage_tolerance=request.slippage.value,
            )
        assert request.normalized_limit_price is not None
        return self.adapter.create_limit_order(
            **common, price=request.normalized_limit_price, reduce_only=False,
        )


def _selected_identity(order_id: str | None, order_link_id: str | None):
    if int(bool(order_id)) + int(bool(order_link_id)) != 1:
        raise ValueError("exactly one order identity is required")
    return order_id, order_link_id


def _validate_scope(account: TradingAccountId, symbol: str, order: OrderEvent) -> None:
    if (
        order.trading_account_id != account or order.category is not Category.LINEAR
        or order.symbol != symbol.upper() or order.position_idx != 0
    ):
        raise ValueError("fresh order account/symbol scope does not match")


def _validate_selected_order_identity(
    order: OrderEvent, order_id: str | None, order_link_id: str | None,
) -> None:
    if order_id is not None and order.order_id.value != order_id:
        raise ValueError("selected orderId does not match fresh order state")
    if order_link_id is not None and order.order_link_id != order_link_id:
        raise ValueError("selected orderLinkId does not match fresh order state")


def _normalized_amend_quantity(intent: AmendIntent) -> Decimal | None:
    value = intent.resulting_total_quantity
    if value is None:
        return None
    normalized = floor_to_step(value, intent.instrument.quantity_step)
    if normalized != value:
        raise ValueError("resulting total quantity is not normalized to quantity step")
    if normalized <= intent.current_order.cumulative_filled_quantity:
        raise ValueError("resulting total quantity must exceed already-filled quantity")
    if not (intent.instrument.min_order_quantity <= normalized <= intent.instrument.max_order_quantity):
        raise ValueError("resulting total quantity is outside instrument limits")
    return normalized


def _normalized_amend_price(intent: AmendIntent) -> Decimal | None:
    value = intent.changed_price
    if value is None:
        return None
    normalized = normalize_limit_price(value, intent.instrument.tick_size, intent.side)
    if normalized != value:
        raise ValueError("changed price is not normalized to tick size")
    if not (intent.instrument.min_price <= normalized <= intent.instrument.max_price):
        raise ValueError("changed price is outside instrument limits")
    return normalized
