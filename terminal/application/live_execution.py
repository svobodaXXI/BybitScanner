"""Account-fenced LIVE parity facade over the existing TradingApplication."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Callable
from uuid import UUID, uuid5

from terminal.api.models import CommandResult, CommandResultStatus, LimitCommandRequest, VolumeUnit
from terminal.api.rest import ServerCommandContext, TerminalCommandApi
from terminal.application.execution_engine import ExecutionEngine
from terminal.application.command_identity import CommandIdentityFactory
from terminal.application.live_limit_acceptance import LiveLimitAcceptanceService
from terminal.application.models import ProtectionEvidence, ReconciliationResult, TrustState
from terminal.application.pretrade_guard import (
    MutationGate, NotionalIntent, OrderKind, PreTradeContext, PreTradeGuard,
    PreTradeIntent, WorkingVolumeIntent,
)
from terminal.application.trading_accounts import (
    AccountSessionToken, TradingAccountEnvironment, TradingAccountManager,
    TradingAccountProvider, TradingAccountStatus,
)
from terminal.application.trading_application import TradingApplication
from terminal.domain.models import Category, OrderId, PositionKey, PositionSide, Symbol, TradingAccountId
from terminal.domain.states import CommandState, ConnectivityState
from terminal.exchange.events import NormalizedPositionStatus, PositionEvent
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition, MutationKind, MutationOutcome,
)
from terminal.persistence.sqlite_store import LiveLimitActionRecord, PersistenceError, SQLiteStore
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
            and item.command_id != self._owner._ignored_limit_command_id
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
        live_limit_acceptance: LiveLimitAcceptanceService | None = None,
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
        self._live_limit_acceptance = live_limit_acceptance
        self._gates = gates
        self._clock_ms = clock_ms
        self._captured: AccountSessionToken | None = None
        self._mutation_scope = "parity"
        self._ignored_limit_command_id = None
        context = _LiveContextProvider(self)
        self._engine = ExecutionEngine(store)
        application = TradingApplication(
            PreTradeGuard(gate=MutationGate(mutations_enabled=True)), store,
            _FencedExecutionPort(self), self._engine,
            mutations_enabled=True, clock_ms=clock_ms,
        )
        self._application = application
        self.api = TerminalCommandApi(application, context)

    def recover_unresolved(self, account_id: TradingAccountId | None = None):
        """REST-only reconciliation; it never obtains the mutation adapter."""
        recovered = []
        live_limit_command_ids = set()
        for action in self._store.load_unresolved_live_limit_actions(account_id):
            live_limit_command_ids.add(action.command_id)
            recovered.append(self._reconcile_live_limit_action(action))
        ambiguous = {
            CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
            CommandState.CANCEL_PENDING, CommandState.UNKNOWN, CommandState.RECONCILING,
        }
        for command in self._store.load_unfinished_commands():
            if command.current_state not in ambiguous or (account_id and command.trading_account_id != account_id):
                continue
            if command.command_id in live_limit_command_ids:
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
        return CommandResult(
            client_action_id, CommandResultStatus.BLOCKED,
            "live_limit_amend_cancel_durable_ownership_required",
            "LIVE Limit amend/cancel requires durable owned-order wiring",
            None, False,
        )

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
                "live_limit_amend_cancel_durable_ownership_required",
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
        service = self._live_limit_acceptance
        if service is None:
            raise RuntimeError("live_limit_durable_admission_required")
        token = self._captured
        assert token is not None
        now = self._clock_ms()
        symbol = Symbol(request.symbol)
        session = service.select_session(
            account_id=account_id, session_generation=token.generation,
            symbol=symbol, client_action_id=request.client_action_id.value,
            occurred_at_ms=now,
        )
        existing = self._store.get_live_limit_action(
            session.acceptance_session_id, account_id, token.generation,
            request.client_action_id.value,
        )
        self._ignored_limit_command_id = existing.command_id if existing else None
        try:
            context = _LiveContextProvider(self).context_for(symbol.value)
            if request.volume.unit is VolumeUnit.WORKING_VOLUME:
                if context.one_wv_usdt is None:
                    raise ValueError("working-volume setting is unavailable")
                volume = WorkingVolumeIntent(request.volume.amount, context.one_wv_usdt)
            else:
                volume = NotionalIntent(request.volume.amount)
            decision, record = self._application.prepare(
                PreTradeIntent(
                    symbol.value, request.side, OrderKind.LIMIT, volume,
                    request.sizing_reference_price, request.limit_price, None,
                ),
                context.pretrade,
            )
        finally:
            self._ignored_limit_command_id = None
        if not decision.admitted or record is None:
            code = decision.reason_code.value if decision.reason_code else "blocked"
            return CommandResult(
                request.client_action_id.value, CommandResultStatus.BLOCKED,
                code, decision.reason, None, False,
            )
        assert record.normalized_price is not None
        assert record.normalized_quantity is not None
        conservative_notional = max(
            record.requested_notional.value,
            record.normalized_price.value * record.normalized_quantity.value,
        )
        admission = service.admit_create(
            acceptance_session_id=session.acceptance_session_id,
            session_generation=token.generation,
            client_action_id=request.client_action_id.value,
            request_fingerprint=_live_limit_fingerprint(
                account_id, token.generation, request, record, conservative_notional,
            ),
            record=record, reserved_notional=conservative_notional,
            occurred_at_ms=record.updated_at_ms,
        )
        if not admission.created:
            return self._live_limit_result(admission.action)
        action = admission.action
        submitting = self._store.begin_live_limit_dispatch(
            action, runtime=service.runtime_attribution, occurred_at_ms=self._clock_ms(),
        )
        dispatch_action = self._store.get_live_limit_action(
            action.acceptance_session_id, action.trading_account_id,
            action.session_generation, action.client_action_id,
        )
        if dispatch_action is None:
            raise PersistenceError("LIVE Limit dispatch ownership disappeared")
        try:
            dispatch_account = self._require_dispatch_authority()
            if dispatch_account != dispatch_action.trading_account_id:
                raise RuntimeError("stale_account_session")
            assert submitting.normalized_quantity is not None
            assert submitting.normalized_price is not None
            outcome = self._adapter_provider(dispatch_account).create_limit_order(
                symbol=dispatch_action.symbol.value, side=submitting.side.value,
                qty=submitting.normalized_quantity.value,
                price=submitting.normalized_price.value,
                order_link_id=dispatch_action.order_link_id, reduce_only=False,
            )
            if outcome.order_link_id not in {None, dispatch_action.order_link_id}:
                outcome = MutationOutcome(
                    MutationKind.CREATE, MutationDisposition.UNKNOWN,
                    reason="exchange response orderLinkId mismatch",
                )
        except Exception as exc:
            outcome = MutationOutcome(
                MutationKind.CREATE, MutationDisposition.UNKNOWN,
                reason=f"ambiguous adapter exception: {type(exc).__name__}",
            )
        persisted = self._store.record_live_limit_outcome(
            dispatch_action, disposition=outcome.disposition.value,
            exchange_order_id=OrderId(outcome.order_id) if outcome.order_id else None,
            reason=outcome.reason or f"exchange {outcome.disposition.value}",
            occurred_at_ms=self._clock_ms(),
            outcome_code=outcome.reject_code,
        )
        return self._live_limit_result(persisted)

    def _live_limit_result(self, action: LiveLimitActionRecord) -> CommandResult:
        command = self._store.get_command(action.command_id)
        if command is None:
            raise PersistenceError("LIVE Limit action command is unavailable")
        if action.outcome_disposition == "rejected" or command.current_state is CommandState.REJECTED:
            return CommandResult(
                action.client_action_id, CommandResultStatus.REJECTED,
                "exchange_rejected", action.outcome_reason or "exchange rejected the request",
                command.command_id.value, False,
            )
        if action.dispatch_state in {"DISPATCHING", "UNKNOWN"} or command.current_state is CommandState.UNKNOWN:
            return CommandResult(
                action.client_action_id, CommandResultStatus.UNKNOWN,
                "mutation_unknown", "mutation outcome requires reconciliation",
                command.command_id.value, True,
            )
        status = (
            CommandResultStatus.COMPLETED
            if command.current_state is CommandState.FILLED
            else CommandResultStatus.ACCEPTED_PENDING
        )
        return CommandResult(
            action.client_action_id, status, status.value,
            "request is durably owned and will not be redispatched",
            command.command_id.value, action.reconciliation_state == "REQUIRED",
        )

    def _reconcile_live_limit_action(self, action: LiveLimitActionRecord):
        """Use only persisted identity and read adapters; never acquire mutation authority."""
        if action.dispatch_state == "OWNED":
            return action
        try:
            command = self._store.get_command(action.command_id)
            if command is None:
                raise PersistenceError("LIVE Limit reconciliation command is unavailable")
            adapter = self._read_adapter_provider(action.trading_account_id)
            orders = (
                *adapter.list_active_orders(action.symbol.value),
                *adapter.list_order_history(action.symbol.value),
            )
            executions = adapter.list_executions(action.symbol.value)
            matching_orders = tuple(order for order in orders if (
                order.trading_account_id == action.trading_account_id
                and order.category is Category.LINEAR
                and order.symbol == action.symbol.value
                and order.position_idx == 0
                and order.side is command.side
                and order.order_type.value == "limit"
                and not order.reduce_only
                and _matches_persisted_limit_identity(
                    action, order.order_id, order.order_link_id,
                )
            ))
            matching_executions = tuple(execution for execution in executions if (
                execution.trading_account_id == action.trading_account_id
                and execution.category is Category.LINEAR
                and execution.symbol == action.symbol.value
                and execution.side is command.side
                and _matches_persisted_limit_identity(
                    action, execution.order_id, execution.order_link_id,
                )
            ))
            order_ids = {item.order_id for item in (*matching_orders, *matching_executions)}
            if len(order_ids) > 1:
                if action.dispatch_state in {"DISPATCHING", "ACKNOWLEDGED"}:
                    self._store.mark_live_limit_unknown(
                        action, occurred_at_ms=self._clock_ms(),
                    )
                return self._store.get_live_limit_action(
                    action.acceptance_session_id, action.trading_account_id,
                    action.session_generation, action.client_action_id,
                )
            if not order_ids:
                if action.dispatch_state in {"DISPATCHING", "ACKNOWLEDGED"}:
                    self._store.mark_live_limit_unknown(
                        action, occurred_at_ms=self._clock_ms(),
                    )
                return self._store.get_live_limit_action(
                    action.acceptance_session_id, action.trading_account_id,
                    action.session_generation, action.client_action_id,
                )
            self._engine.replace_order_inventory(matching_orders)
            for execution in matching_executions:
                self._engine.apply_execution(execution)
            self._engine.resolve_command(
                command, order_evidence=matching_orders,
                execution_evidence=matching_executions,
                occurred_at_ms=self._clock_ms(),
            )
            return self._store.complete_live_limit_reconciliation(
                action, exchange_order_id=next(iter(order_ids)),
                occurred_at_ms=self._clock_ms(),
            )
        except Exception:
            if action.dispatch_state in {"DISPATCHING", "ACKNOWLEDGED"}:
                try:
                    self._store.mark_live_limit_unknown(
                        action, occurred_at_ms=self._clock_ms(),
                    )
                except Exception:
                    pass
            return self._store.get_live_limit_action(
                action.acceptance_session_id, action.trading_account_id,
                action.session_generation, action.client_action_id,
            ) or action

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


def _live_limit_fingerprint(
    account_id: TradingAccountId, session_generation: int,
    request: LimitCommandRequest, record, reserved_notional: Decimal,
) -> str:
    payload = {
        "account_id": account_id.value,
        "session_generation": session_generation,
        "symbol": record.symbol.value,
        "side": record.side.value,
        "quantity": str(record.normalized_quantity.value),
        "price": str(record.normalized_price.value),
        "reserved_notional": str(reserved_notional),
        "time_in_force": request.time_in_force.value,
        "position_idx": record.position_idx,
        "reduce_only": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _matches_persisted_limit_identity(
    action: LiveLimitActionRecord, order_id: OrderId, order_link_id: str | None,
) -> bool:
    if order_link_id == action.order_link_id:
        return action.exchange_order_id is None or order_id == action.exchange_order_id
    return (
        action.exchange_order_id is not None
        and order_id == action.exchange_order_id
        and not order_link_id
    )
