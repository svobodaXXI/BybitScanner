"""Account-fenced LIVE parity facade over the existing TradingApplication."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from uuid import UUID, uuid5

from terminal.api.models import CommandResult, CommandResultStatus, LimitCommandRequest, VolumeUnit
from terminal.api.rest import ServerCommandContext, TerminalCommandApi
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.models import ProtectionEvidence, ReconciliationResult, TrustState
from terminal.application.pretrade_guard import MutationGate, PreTradeContext, PreTradeGuard
from terminal.application.trading_accounts import (
    AccountSessionToken, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import Category, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.domain.states import CommandState, ConnectivityState
from terminal.exchange.events import NormalizedPositionStatus, PositionEvent
from terminal.persistence.sqlite_store import SQLiteStore
from terminal.runtime.paper_context import working_volume_usdt


@dataclass(frozen=True, slots=True)
class LiveParityMutationGates:
    parity_mutations_enabled: bool = False
    mainnet_authorized: bool = False
    limit_mutations_enabled: bool = False
    limit_acceptance_notional_ceiling: Decimal = Decimal("0")


class _FencedExecutionPort:
    def __init__(self, owner: "LiveExecutionCoordinator") -> None:
        self._owner = owner

    def _call(self, method: str, **payload):
        account_id = self._owner._require_dispatch_authority()
        return getattr(self._owner._adapter_provider(account_id), method)(**payload)

    def create_market_order(self, **payload):
        if payload.get("reduce_only") is not True:
            raise ValueError("LIVE parity market mutations must be reduceOnly")
        return self._call("create_market_order", **payload)

    def create_limit_order(self, **payload):
        raise RuntimeError("live_limit_durable_admission_required")

    def amend_order(self, **payload):
        return self._call("amend_order", **payload)

    def cancel_order(self, **payload):
        return self._call("cancel_order", **payload)

    def set_trading_stop(self, **payload):
        return self._call("set_trading_stop", **payload)


class _LiveContextProvider:
    def __init__(self, owner: "LiveExecutionCoordinator") -> None:
        self._owner = owner

    def context_for(self, symbol: str) -> ServerCommandContext:
        account_id = self._owner._require_dispatch_authority()
        adapter = self._owner._read_adapter_provider(account_id)
        normalized = symbol.strip().upper()
        instrument = self._owner._instrument_provider(normalized)
        position = adapter.get_position(normalized)
        if position is None:
            position = PositionEvent(
                PositionKey(account_id, Category.LINEAR, Symbol(normalized), 0),
                PositionSide.FLAT, Decimal("0"), None, None, None, None,
                Decimal("0"), Decimal("0"), NormalizedPositionStatus.NORMAL,
                "REST_EMPTY", None, None, None, None, self._owner._clock_ms(),
            )
        if position.position_key != PositionKey(account_id, Category.LINEAR, Symbol(normalized), 0):
            raise ValueError("fresh position account/symbol scope does not match")
        unresolved_states = {
            CommandState.ADMITTED, CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
            CommandState.CANCEL_PENDING, CommandState.UNKNOWN, CommandState.RECONCILING,
        }
        unresolved = tuple(
            item.command_id.value for item in self._owner._store.load_unfinished_commands()
            if item.trading_account_id == account_id and item.current_state in unresolved_states
        )
        reconciliation = ReconciliationResult(
            TrustState.CONVERGED, position.position_key, (), unresolved, 0, 0,
            None, None, ("unresolved mutation requires reconciliation",) if unresolved else (),
        )
        context = PreTradeContext(
            account_id, Category.LINEAR, position.position_key, 0, position.side,
            position.size, True, True, ConnectivityState.ONLINE, reconciliation,
            bool(unresolved), instrument,
        )
        snapshot = self._owner._live_account_store.get(account_id.value)
        if snapshot is None:
            raise ValueError("live account snapshot is unavailable")
        side = None
        if position.side is PositionSide.LONG:
            from terminal.domain.models import OrderSide
            side = OrderSide.SELL
        elif position.side is PositionSide.SHORT:
            from terminal.domain.models import OrderSide
            side = OrderSide.BUY
        return ServerCommandContext(
            context, instrument, position, working_volume_usdt(snapshot.wallet_balance_usdt), side,
        )

    def order_for(self, symbol: str, order_id: str | None, order_link_id: str | None):
        account_id = self._owner._require_dispatch_authority()
        adapter = self._owner._read_adapter_provider(account_id)
        normalized = symbol.strip().upper()
        orders = (*adapter.list_active_orders(normalized), *adapter.list_order_history(normalized))
        matches = [item for item in orders if (
            (order_id is not None and item.order_id.value == order_id)
            or (order_link_id is not None and item.order_link_id == order_link_id)
        )]
        if len(matches) != 1:
            raise ValueError("fresh LIVE order identity is missing or ambiguous")
        return matches[0]


class LiveExecutionCoordinator:
    """Reuse the canonical application while fencing every irreversible adapter call."""

    def __init__(
        self, manager: TradingAccountManager, store: SQLiteStore,
        adapter_provider: Callable[[TradingAccountId], object], *,
        read_adapter_provider: Callable[[TradingAccountId], object],
        instrument_provider: Callable[[str], object], live_account_store,
        writable_account_provider: Callable[[TradingAccountId], bool],
        gates: LiveParityMutationGates = LiveParityMutationGates(),
        clock_ms: Callable[[], int],
    ) -> None:
        self._manager = manager
        self._store = store
        self._adapter_provider = adapter_provider
        self._read_adapter_provider = read_adapter_provider
        self._instrument_provider = instrument_provider
        self._live_account_store = live_account_store
        self._writable_account_provider = writable_account_provider
        self._gates = gates
        self._clock_ms = clock_ms
        self._captured: AccountSessionToken | None = None
        self._mutation_scope = "parity"
        context = _LiveContextProvider(self)
        self._engine = ExecutionEngine(store)
        application = TradingApplication(
            PreTradeGuard(gate=MutationGate(mutations_enabled=True)), store,
            _FencedExecutionPort(self), self._engine,
            mutations_enabled=True, clock_ms=clock_ms,
        )
        self.api = TerminalCommandApi(application, context)

    def recover_unresolved(self, account_id: TradingAccountId | None = None):
        """REST-only reconciliation; it never obtains the mutation adapter."""
        recovered = []
        ambiguous = {
            CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
            CommandState.CANCEL_PENDING, CommandState.UNKNOWN, CommandState.RECONCILING,
        }
        for command in self._store.load_unfinished_commands():
            if command.current_state not in ambiguous or (account_id and command.trading_account_id != account_id):
                continue
            try:
                adapter = self._read_adapter_provider(command.trading_account_id)
                symbol = command.symbol.value
                orders = (*adapter.list_active_orders(symbol), *adapter.list_order_history(symbol))
                executions = adapter.list_executions(symbol)
                position = adapter.get_position(symbol)
                resolved = self._engine.resolve_command(
                    command, order_evidence=tuple(orders), execution_evidence=tuple(executions),
                    occurred_at_ms=self._clock_ms(),
                )
                if command.command_kind == "protection" and position is not None:
                    self._engine.ingest_protection_evidence(
                        ProtectionEvidence.from_position(position), occurred_at_ms=self._clock_ms(),
                    )
                recovered.append(resolved)
            except Exception:
                recovered.append(command)
        return tuple(recovered)

    def execute(
        self, account_id_text: str, session_generation: int, client_action_id: str,
        operation: Callable[[TerminalCommandApi], CommandResult],
    ):
        return self._execute(account_id_text, session_generation, client_action_id, "parity", operation)

    def execute_limit_create(
        self, account_id_text: str, session_generation: int, request: LimitCommandRequest,
    ):
        return self._execute(
            account_id_text, session_generation, request.client_action_id.value, "limit",
            lambda api: self._submit_limit_with_ceiling(api, request),
        )

    def execute_limit_amend_cancel(
        self, account_id_text: str, session_generation: int, client_action_id: str,
        operation: Callable[[TerminalCommandApi], CommandResult],
    ):
        return self._execute(account_id_text, session_generation, client_action_id, "limit", operation)

    def _execute(
        self, account_id_text: str, session_generation: int, client_action_id: str,
        mutation_scope: str, operation: Callable[[TerminalCommandApi], CommandResult],
    ):
        action_id = client_action_id
        try:
            account_id = TradingAccountId(account_id_text)
            token = AccountSessionToken(account_id, session_generation)
            self._captured = token
            self._mutation_scope = mutation_scope
            self._require_dispatch_authority()
            stable_uuid = uuid5(
                UUID("b55270c8-80c2-4c76-9aa0-15633ca9fdb5"),
                f"{account_id_text}\0{session_generation}\0{client_action_id}",
            )
            self.api._application.identity_factory = CommandIdentityFactory(lambda: stable_uuid)
            result = operation(self.api)
            return result
        except Exception as exc:
            code = str(exc) if str(exc) in {
                "live_mutations_disabled", "live_limit_disabled",
                "live_limit_durable_admission_required",
                "live_limit_acceptance_notional_exceeded", "live_mainnet_unauthorized", "inactive_account",
                "stale_account_session", "live_account_not_writable_ready",
            } else "live_parity_unavailable"
            return CommandResult(action_id, CommandResultStatus.BLOCKED, code, code, None, False)
        finally:
            self._captured = None
            self._mutation_scope = "parity"

    def _submit_limit_with_ceiling(
        self, api: TerminalCommandApi, request: LimitCommandRequest,
    ) -> CommandResult:
        account_id = self._require_dispatch_authority()
        ceiling = self._gates.limit_acceptance_notional_ceiling
        snapshot = self._live_account_store.get(account_id.value)
        if snapshot is None:
            raise RuntimeError("live_limit_acceptance_notional_exceeded")
        requested_notional = request.volume.amount
        if request.volume.unit is VolumeUnit.WORKING_VOLUME:
            requested_notional *= working_volume_usdt(snapshot.wallet_balance_usdt)
        if not ceiling.is_finite() or ceiling <= 0 or requested_notional > ceiling:
            raise RuntimeError("live_limit_acceptance_notional_exceeded")
        raise RuntimeError("live_limit_durable_admission_required")

    def _require_dispatch_authority(self) -> TradingAccountId:
        if self._mutation_scope == "limit":
            if not self._gates.limit_mutations_enabled:
                raise RuntimeError("live_limit_disabled")
        elif not self._gates.parity_mutations_enabled:
            raise RuntimeError("live_mutations_disabled")
        if not self._gates.mainnet_authorized:
            raise RuntimeError("live_mainnet_unauthorized")
        token = self._captured
        if token is None or token.active_account_id != self._manager.active_account_id:
            raise RuntimeError("inactive_account")
        if token != self._manager.session_token:
            raise RuntimeError("stale_account_session")
        account = self._manager.active_account
        if not (
            account.provider is TradingAccountProvider.BYBIT
            and account.environment is TradingAccountEnvironment.MAINNET
            and account.status is TradingAccountStatus.READY
            and self._writable_account_provider(account.id)
        ):
            raise RuntimeError("live_account_not_writable_ready")
        return account.id
