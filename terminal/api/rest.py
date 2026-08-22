"""Framework-neutral command endpoint service; never owns trading decisions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from terminal.api.models import (
    AmendCommandRequest, CancelCommandRequest, CommandResult, CommandResultStatus,
    LimitCommandRequest, MarketCommandRequest, ProtectionCommandRequest, VolumeUnit,
)
from terminal.application.pretrade_guard import (
    NotionalIntent, OrderKind, PreTradeContext, PreTradeIntent, SlippageMetadata,
    SlippageToleranceType, WorkingVolumeIntent,
)
from terminal.application.protection import ManualProtectionIntent
from terminal.application.trading_application import (
    AmendIntent, ApplicationMutationsDisabled, ApplicationResult, CancelIntent,
    TradingApplication,
)
from terminal.domain.states import CommandState
from terminal.domain.models import OrderSide, TradingAccountId
from terminal.exchange.events import InstrumentSnapshot, OrderEvent, PositionEvent
from terminal.persistence.sqlite_store import PersistenceError


@dataclass(frozen=True, slots=True)
class ServerCommandContext:
    pretrade: PreTradeContext
    instrument: InstrumentSnapshot
    position: PositionEvent
    one_wv_usdt: Decimal | None = None
    protection_command_side: OrderSide | None = None


class CommandContextProvider(Protocol):
    def context_for(self, symbol: str) -> ServerCommandContext: ...

    def order_for(
        self, symbol: str, order_id: str | None, order_link_id: str | None,
    ) -> OrderEvent: ...


class TerminalCommandApi:
    def __init__(self, application: TradingApplication, context: CommandContextProvider) -> None:
        self._application = application
        self._context = context

    def market(self, request: MarketCommandRequest) -> CommandResult:
        return self._submit(request, OrderKind.MARKET)

    def limit(self, request: LimitCommandRequest) -> CommandResult:
        return self._submit(request, OrderKind.LIMIT)

    def amend(self, request: AmendCommandRequest) -> CommandResult:
        def action():
            symbol = _symbol(request.symbol)
            context = self._context.context_for(symbol)
            order = self._context.order_for(symbol, request.order_id, request.order_link_id)
            return self._application.amend(AmendIntent(
                _account(context), symbol, order.side,
                context.instrument, order, request.order_id, request.order_link_id,
                request.resulting_total_quantity, request.changed_price,
            ))
        return self._execute(request.client_action_id.value, action)

    def cancel(self, request: CancelCommandRequest) -> CommandResult:
        def action():
            symbol = _symbol(request.symbol)
            context = self._context.context_for(symbol)
            order = self._context.order_for(symbol, request.order_id, request.order_link_id)
            return self._application.cancel(CancelIntent(
                _account(context), symbol, order.side, order,
                request.order_id, request.order_link_id,
            ))
        return self._execute(request.client_action_id.value, action)

    def protection(self, request: ProtectionCommandRequest) -> CommandResult:
        action_id = request.client_action_id.value
        try:
            symbol = _symbol(request.symbol)
            context = self._context.context_for(symbol)
            if context.protection_command_side is None:
                raise ValueError("server protection command side is unavailable")
            result = self._application.set_protection(ManualProtectionIntent(
                context.position.position_key, context.protection_command_side,
                context.position, context.instrument, request.take_profit, request.stop_loss,
                request.tp_trigger_by, request.sl_trigger_by, context.pretrade.connectivity,
            ))
            if result.state.value == "unknown":
                return _result(action_id, CommandResultStatus.UNKNOWN, "mutation_unknown",
                               "protection outcome requires reconciliation", result.command_id, True)
            if result.state.value == "failed_unprotected":
                return _result(action_id, CommandResultStatus.REJECTED, "exchange_rejected",
                               "protection request was rejected", result.command_id)
            return _result(action_id, CommandResultStatus.ACCEPTED_PENDING, "accepted_pending",
                           "protection request is pending exchange confirmation", result.command_id)
        except Exception as exc:
            return _safe_error(action_id, exc)

    def _submit(self, request: MarketCommandRequest | LimitCommandRequest, kind: OrderKind) -> CommandResult:
        def action():
            symbol = _symbol(request.symbol)
            context = self._context.context_for(symbol)
            volume = (
                WorkingVolumeIntent(request.volume.amount, _required_wv(context))
                if request.volume.unit is VolumeUnit.WORKING_VOLUME
                else NotionalIntent(request.volume.amount)
            )
            slippage = None
            limit_price = None
            if isinstance(request, MarketCommandRequest):
                slippage = SlippageMetadata(
                    SlippageToleranceType(request.slippage_type), request.slippage_value,
                )
            else:
                limit_price = request.limit_price
            intent = PreTradeIntent(
                symbol, request.side, kind, volume, request.sizing_reference_price,
                limit_price, slippage,
            )
            return self._application.submit(intent, context.pretrade)
        return self._execute(request.client_action_id.value, action)

    def _execute(self, action_id: str, action) -> CommandResult:
        try:
            return _application_result(action_id, action())
        except Exception as exc:
            return _safe_error(action_id, exc)


def _required_wv(context: ServerCommandContext) -> Decimal:
    value = context.one_wv_usdt
    if not isinstance(value, Decimal):
        raise ValueError("working-volume setting is unavailable")
    return value


def _application_result(action_id: str, result: ApplicationResult) -> CommandResult:
    if result.decision is not None and not result.decision.admitted:
        code = result.decision.reason_code.value if result.decision.reason_code else "blocked"
        return _result(action_id, CommandResultStatus.BLOCKED, code, result.decision.reason)
    command_id = result.command.command_id.value if result.command else None
    if result.outcome is not None:
        disposition = getattr(result.outcome.disposition, "value", result.outcome.disposition)
        if disposition == "unknown":
            return _result(action_id, CommandResultStatus.UNKNOWN, "mutation_unknown",
                           "mutation outcome requires reconciliation", command_id, True)
        if disposition == "rejected":
            return _result(action_id, CommandResultStatus.REJECTED, "exchange_rejected",
                           "exchange rejected the request", command_id)
    if result.command is not None and result.command.current_state is CommandState.UNKNOWN:
        return _result(action_id, CommandResultStatus.UNKNOWN, "mutation_unknown",
                       "mutation outcome requires reconciliation", command_id, True)
    return _result(action_id, CommandResultStatus.ACCEPTED_PENDING, "accepted_pending",
                   "request is pending authoritative exchange confirmation", command_id)


def _safe_error(action_id: str, exc: Exception) -> CommandResult:
    if isinstance(exc, PersistenceError):
        return _result(action_id, CommandResultStatus.PERSISTENCE_FAILURE,
                       "persistence_failure", "command could not be durably recorded")
    if isinstance(exc, ApplicationMutationsDisabled):
        return _result(action_id, CommandResultStatus.UNAVAILABLE,
                       "mutations_disabled", "trading mutations are disabled")
    if isinstance(exc, (ValueError, TypeError)):
        return _result(action_id, CommandResultStatus.VALIDATION_ERROR,
                       "validation_error", "command request is invalid")
    return _result(action_id, CommandResultStatus.UNAVAILABLE,
                   "service_unavailable", "command service is unavailable")


def _result(
    action_id: str, status: CommandResultStatus, code: str, message: str,
    command_id: str | None = None, reconciliation_required: bool = False,
) -> CommandResult:
    return CommandResult(action_id, status, code, message, command_id, reconciliation_required)


def _account(context: ServerCommandContext) -> TradingAccountId:
    account = context.pretrade.selected_account_id
    if account is None:
        raise ValueError("server-selected account is unavailable")
    return account


def _symbol(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("symbol is required")
    return value.strip().upper()
