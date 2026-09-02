"""Default-off, account-fenced orchestration for manual LIVE MARKET mutations."""

from __future__ import annotations

import hashlib
import json
import re
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
    Category, Controller, Notional, OrderSide, Origin, Price, Quantity, Symbol,
    TradingAccountId,
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
    acceptance_single_flight: bool = False


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
        self._acceptance_permit_consumed = False
        self.before_dispatch: Callable[[], object] | None = None
        self.after_final_validation: Callable[[], object] | None = None

    def submit(self, request: LiveMarketCommandRequest) -> LiveMarketCommandResult:
        account_id = TradingAccountId(request.account_id)
        existing = self._store.get_live_market_action(
            account_id, request.session_generation, request.client_action_id.value,
        )
        if existing is None:
            existing = self._store.find_live_market_action(
                account_id, request.client_action_id.value,
            )
        fingerprint = _fingerprint(request)
        if existing is not None:
            if (
                existing.session_generation == request.session_generation
                and existing.request_fingerprint != fingerprint
            ):
                return _blocked(request, "client_action_conflict")
            command = self._store.get_command(existing.command_id)
            command = (
                self._reconcile_existing(request, command)
                if existing.session_generation == request.session_generation
                else self._reconcile_action(existing, command)
            )
            return _result(request, command, existing.order_link_id)

        token_or_result = self._eligibility(request, account_id)
        if isinstance(token_or_result, LiveMarketCommandResult):
            return token_or_result
        token = token_or_result
        if self._gates.acceptance_single_flight and self._acceptance_permit_consumed:
            return _blocked(request, "acceptance_permit_consumed")
        if self._store.load_unresolved_live_market_actions(account_id):
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
        validation_error = self._final_pre_dispatch_validation(
            request, token, instrument, authoritative_price, normalized_quantity,
            action.order_link_id,
        )
        if validation_error is not None:
            return _blocked(
                request, validation_error, action.command_id.value, action.order_link_id,
            )
        if self.after_final_validation is not None:
            self.after_final_validation()
        validation_error = self._final_pre_dispatch_validation(
            request, token, instrument, authoritative_price, normalized_quantity,
            action.order_link_id,
        )
        if validation_error is not None:
            return _blocked(
                request, validation_error, action.command_id.value, action.order_link_id,
            )
        command = self._store.begin_live_market_dispatch(action, occurred_at_ms=self._clock_ms())
        if command is None:
            return _result(request, self._store.get_command(action.command_id), action.order_link_id)
        if self._gates.acceptance_single_flight:
            self._acceptance_permit_consumed = True

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

    def recover_unresolved(
        self, account_id: TradingAccountId | None = None,
    ) -> tuple[CommandRecord, ...]:
        """Reconcile persisted LIVE actions through read adapters only."""
        recovered = []
        for action in self._store.load_unresolved_live_market_actions(account_id):
            command = self._store.get_command(action.command_id)
            if command is not None:
                recovered.append(self._reconcile_action(action, command))
        return tuple(recovered)

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

    def _final_pre_dispatch_validation(
        self, request, token, instrument, authoritative_price, normalized_quantity,
        order_link_id,
    ) -> str | None:
        if self._manager.session_token != token:
            return "stale_account_session"
        account = self._manager.active_account
        if not (
            account.id == token.active_account_id
            and account.provider is TradingAccountProvider.BYBIT
            and account.environment is TradingAccountEnvironment.MAINNET
            and account.status is TradingAccountStatus.READY
            and self._writable_account_provider(account.id)
        ):
            return "live_account_not_writable_ready"
        symbol = request.symbol.strip().upper() if isinstance(request.symbol, str) else ""
        if (
            not re.fullmatch(r"[A-Z0-9]+", symbol)
            or symbol != instrument.symbol.upper()
        ):
            return "invalid_live_market_symbol"
        if request.side not in {OrderSide.BUY, OrderSide.SELL}:
            return "invalid_live_market_side"
        expected_quantity = _normalize_quantity(request, instrument, authoritative_price)
        if (
            expected_quantity is None
            or normalized_quantity != expected_quantity
            or not normalized_quantity.is_finite()
            or normalized_quantity <= 0
        ):
            return "invalid_live_market_size"
        if not (
            isinstance(order_link_id, str)
            and len(order_link_id) == 36
            and re.fullmatch(r"tw_[0-9a-f]{33}", order_link_id)
        ):
            return "invalid_live_order_link_id"
        if request.slippage_type not in {"Percent", "TickSize"}:
            return "invalid_live_market_slippage"
        slippage = request.slippage_value
        if not isinstance(slippage, Decimal) or not slippage.is_finite() or slippage <= 0:
            return "invalid_live_market_slippage"
        if request.slippage_type == "Percent" and not Decimal("0.01") <= slippage <= Decimal("10"):
            return "invalid_live_market_slippage"
        if request.slippage_type == "TickSize" and (
            slippage != slippage.to_integral_value() or slippage > Decimal("10000")
        ):
            return "invalid_live_market_slippage"
        authoritative_notional = normalized_quantity * authoritative_price
        if (
            not authoritative_notional.is_finite()
            or authoritative_notional <= 0
            or authoritative_notional > self._gates.acceptance_notional_ceiling
        ):
            return "acceptance_notional_exceeded"
        return None

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

    def _reconcile_action(self, action, command):
        if command is None or command.current_state not in {
            CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
            CommandState.UNKNOWN, CommandState.RECONCILING,
        }:
            return command
        if self._read_adapter_provider is None:
            return self._mark_reconciliation_required(command)
        try:
            adapter = self._read_adapter_provider(action.trading_account_id)
            symbol = command.symbol.value
            orders = (*adapter.list_active_orders(symbol), *adapter.list_order_history(symbol))
            executions = adapter.list_executions(symbol)
            adapter.get_position(symbol)
        except Exception:
            return self._mark_reconciliation_required(command)
        resolved = self._engine.resolve_command(
            command, order_evidence=tuple(orders), execution_evidence=tuple(executions),
            occurred_at_ms=self._clock_ms(),
        )
        captured = AccountSessionToken(action.trading_account_id, action.session_generation)
        if self._projection_refresher is not None and self._manager.session_token == captured:
            try:
                self._projection_refresher(action.trading_account_id.value)
            except Exception:
                pass
        return resolved

    def _mark_reconciliation_required(self, command):
        if command.current_state is CommandState.SUBMITTING:
            return self._engine.resolve_command(
                command, order_evidence=(), execution_evidence=(),
                occurred_at_ms=self._clock_ms(),
            )
        if command.current_state in {CommandState.ACKNOWLEDGED, CommandState.UNKNOWN}:
            return self._store.transition_command_state(
                command.command_id, command.current_state, CommandState.RECONCILING,
                expected_version=command.version,
                reason="restart-safe LIVE reconciliation requires authoritative REST evidence",
                occurred_at_ms=self._clock_ms(),
            )
        return command


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
