"""Default-off, account-fenced orchestration for manual LIVE MARKET mutations."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Callable

from terminal.api.models import (
    CommandResultStatus, LiveMarketCommandRequest, LiveMarketCommandResult, VolumeUnit,
)
from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.trading_accounts import (
    AccountSessionToken, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.domain.models import (
    Category, Controller, Notional, Origin, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.domain.states import CommandState
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition, MutationKind, MutationOutcome,
)
from terminal.market_data.models import BookHealth
from terminal.persistence.sqlite_store import CommandRecord, DuplicateIdentity, SQLiteStore


@dataclass(frozen=True, slots=True)
class LiveMarketMutationGates:
    live_market_mutations_enabled: bool = False
    live_mainnet_authorized: bool = False
    acceptance_notional_ceiling: Decimal = Decimal("0")


class LiveMarketMutationCoordinator:
    """Own one durable client action from eligibility through one adapter attempt."""

    def __init__(
        self,
        manager: TradingAccountManager,
        store: SQLiteStore,
        mutation_adapter_provider: Callable[[TradingAccountId], object],
        *,
        instrument_provider: Callable[[str], object],
        book_provider: object | None = None,
        writable_account_provider: Callable[[TradingAccountId], bool] = lambda _account: False,
        read_adapter_provider: Callable[[TradingAccountId], object] | None = None,
        projection_refresher: Callable[[str], object] | None = None,
        gates: LiveMarketMutationGates = LiveMarketMutationGates(),
        identity_factory: CommandIdentityFactory | None = None,
        clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
    ) -> None:
        self._manager = manager
        self._store = store
        self._mutation_adapter_provider = mutation_adapter_provider
        self._instrument_provider = instrument_provider
        self._book_provider = book_provider
        self._writable_account_provider = writable_account_provider
        self._read_adapter_provider = read_adapter_provider
        self._projection_refresher = projection_refresher
        self._gates = gates
        self._identity_factory = identity_factory or CommandIdentityFactory()
        self._clock_ms = clock_ms
        self._engine = ExecutionEngine(store)
        self.before_dispatch: Callable[[], object] | None = None

    def submit(self, request: LiveMarketCommandRequest) -> LiveMarketCommandResult:
        account_id = TradingAccountId(request.account_id)
        existing = self._store.get_live_market_action(
            account_id, request.session_generation, request.client_action_id.value,
        )
        fingerprint = _fingerprint(request)
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                return _blocked(request, "client_action_conflict")
            command = self._store.get_command(existing.command_id)
            command = self._reconcile_existing(request, command)
            return _result(request, command, existing.order_link_id)

        token_or_result = self._eligibility(request, account_id)
        if isinstance(token_or_result, LiveMarketCommandResult):
            return token_or_result
        token = token_or_result
        if self._store.has_unresolved_live_market_action(account_id, token.generation):
            return _blocked(request, "unresolved_live_market_command")
        instrument = self._instrument_provider(request.symbol.upper())
        authoritative_price = self._fresh_reference_price(request)
        if authoritative_price is None:
            return _blocked(request, "live_market_context_unavailable")
        normalized_quantity = _normalize_quantity(request, instrument, authoritative_price)
        if normalized_quantity is None:
            return _blocked(request, "invalid_live_market_size")

        identity = self._identity_factory.create()
        now = self._clock_ms()
        record = CommandRecord(
            identity.command_id, identity.order_link_id, account_id, Category.LINEAR,
            Symbol(request.symbol), 0, "create_market", request.side,
            Notional(request.volume.amount), Price(authoritative_price),
            Quantity(normalized_quantity), Origin.TERMINAL_MANUAL, Controller.MANUAL,
            CommandState.ADMITTED, 1, None, now, now,
        )
        try:
            action, created = self._store.claim_live_market_action(
                record, session_generation=request.session_generation,
                client_action_id=request.client_action_id.value,
                request_fingerprint=fingerprint,
            )
        except DuplicateIdentity:
            return _blocked(request, "client_action_conflict")
        if not created:
            return _result(request, self._store.get_command(action.command_id), action.order_link_id)

        if self.before_dispatch is not None:
            self.before_dispatch()
        if self._manager.session_token != token:
            return _blocked(request, "stale_account_session", action.command_id.value, action.order_link_id)
        command = self._store.begin_live_market_dispatch(action, occurred_at_ms=self._clock_ms())
        if command is None:
            return _result(request, self._store.get_command(action.command_id), action.order_link_id)

        try:
            outcome = self._mutation_adapter_provider(account_id).create_market_order(
                symbol=request.symbol.upper(), side=request.side.value, qty=normalized_quantity,
                order_link_id=action.order_link_id, reduce_only=False,
                slippage_tolerance_type=request.slippage_type,
                slippage_tolerance=request.slippage_value,
            )
        except Exception as exc:
            outcome = MutationOutcome(
                MutationKind.CREATE, MutationDisposition.UNKNOWN,
                reason=f"mutation transport outcome is ambiguous ({type(exc).__name__})",
            )
        command = self._engine.ingest_mutation_outcome(
            command, outcome, occurred_at_ms=self._clock_ms(),
        )
        # The command remains account/session scoped. Projection publication is a
        # separate reconciliation step and must re-check this token.
        command = self._reconcile_existing(request, command)
        return _result(request, command, action.order_link_id)

    def _eligibility(self, request, account_id):
        if not self._gates.live_market_mutations_enabled:
            return _blocked(request, "live_market_disabled")
        if not self._gates.live_mainnet_authorized:
            return _blocked(request, "live_mainnet_unauthorized")
        if (
            self._gates.acceptance_notional_ceiling <= 0
            or request.volume.amount > self._gates.acceptance_notional_ceiling
        ):
            return _blocked(request, "acceptance_notional_exceeded")
        if account_id != self._manager.active_account_id:
            return _blocked(request, "inactive_account")
        token = self._manager.session_token
        if request.session_generation != token.generation:
            return _blocked(request, "stale_account_session")
        account = self._manager.active_account
        if not (
            account.provider is TradingAccountProvider.BYBIT
            and account.environment is TradingAccountEnvironment.MAINNET
            and account.status is TradingAccountStatus.READY
            and self._writable_account_provider(account_id)
        ):
            return _blocked(request, "live_account_not_writable_ready")
        if request.volume.unit is not VolumeUnit.USDT:
            return _blocked(request, "live_market_requires_usdt")
        return AccountSessionToken(account_id, token.generation)

    def _fresh_reference_price(self, request) -> Decimal | None:
        if self._book_provider is None:
            return request.sizing_reference_price
        book = self._book_provider.get_book(Symbol(request.symbol))
        if book is None or book.health is not BookHealth.READY:
            return None
        if self._clock_ms() - book.received_at_ms > 1000:
            return None
        levels = book.asks if request.side.value == "Buy" else book.bids
        return levels[0].price.value if levels else None

    def _reconcile_existing(self, request, command):
        if command is None or self._read_adapter_provider is None or command.current_state not in {
            CommandState.ACKNOWLEDGED, CommandState.UNKNOWN, CommandState.RECONCILING,
        }:
            return command
        token = AccountSessionToken(TradingAccountId(request.account_id), request.session_generation)
        try:
            adapter = self._read_adapter_provider(token.active_account_id)
            orders = (
                *adapter.list_active_orders(request.symbol),
                *adapter.list_order_history(request.symbol),
            )
            executions = adapter.list_executions(request.symbol)
            adapter.get_position(request.symbol)
        except Exception:
            return command
        if self._manager.session_token != token:
            return command
        resolved = self._engine.resolve_command(
            command, order_evidence=tuple(orders), execution_evidence=tuple(executions),
            occurred_at_ms=self._clock_ms(),
        )
        if self._projection_refresher is not None and self._manager.session_token == token:
            try:
                self._projection_refresher(request.account_id)
            except Exception:
                pass
        return resolved


def _normalize_quantity(request, instrument, price: Decimal) -> Decimal | None:
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        return None
    raw = request.volume.amount / price
    step = instrument.quantity_step
    quantity = (raw / step).to_integral_value(rounding=ROUND_FLOOR) * step
    if quantity < instrument.min_order_quantity or quantity > instrument.max_market_order_quantity:
        return None
    if quantity * price < instrument.min_notional_value:
        return None
    return quantity


def _fingerprint(request: LiveMarketCommandRequest) -> str:
    payload = {
        "account_id": request.account_id, "session_generation": request.session_generation,
        "symbol": request.symbol.upper(), "side": request.side.value,
        "volume_unit": request.volume.unit.value, "volume": str(request.volume.amount),
        "sizing_reference_price": str(request.sizing_reference_price),
        "slippage_type": request.slippage_type, "slippage_value": str(request.slippage_value),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _blocked(request, code, command_id=None, order_link_id=None):
    return LiveMarketCommandResult(
        request.client_action_id.value, CommandResultStatus.BLOCKED, code,
        command_id, order_link_id, False,
    )


def _result(request, command, order_link_id):
    if command is None:
        return _blocked(request, "live_command_unavailable")
    mapping = {
        CommandState.ACKNOWLEDGED: (CommandResultStatus.ACCEPTED_PENDING, "accepted_pending", False),
        CommandState.OPEN: (CommandResultStatus.ACCEPTED_PENDING, "open", False),
        CommandState.PARTIALLY_FILLED: (CommandResultStatus.ACCEPTED_PENDING, "partially_filled", False),
        CommandState.REJECTED: (CommandResultStatus.REJECTED, "exchange_rejected", False),
        CommandState.FILLED: (CommandResultStatus.COMPLETED, "filled", False),
        CommandState.UNKNOWN: (CommandResultStatus.UNKNOWN, "unknown_reconciling", True),
        CommandState.RECONCILING: (CommandResultStatus.UNKNOWN, "unknown_reconciling", True),
        CommandState.SUBMITTING: (CommandResultStatus.UNKNOWN, "unknown_reconciling", True),
    }
    status, code, reconcile = mapping.get(
        command.current_state,
        (CommandResultStatus.BLOCKED, "live_command_not_dispatchable", False),
    )
    return LiveMarketCommandResult(
        request.client_action_id.value, status, code, command.command_id.value,
        order_link_id, reconcile,
    )
