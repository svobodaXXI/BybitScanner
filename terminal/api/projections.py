"""Pure normalized presentation projections derived from supplied Stage 3/6 facts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from terminal.api.models import PROTOCOL_VERSION, ServiceHealth, TradingReadiness
from terminal.application.cleanup import CleanupStatus
from terminal.application.models import ProtectionState, TrustState
from terminal.domain.models import Category, Execution, PositionKey
from terminal.domain.states import CommandState, ConnectivityState
from terminal.exchange.events import (
    InstrumentSnapshot, NormalizedOrderStatus, NormalizedOrderType, OrderEvent, PositionEvent,
)
from terminal.persistence.sqlite_store import (
    CleanupItemRecord, CleanupRunRecord, CommandRecord, ProtectionProjectionRecord,
)


class OrderClassification(str, Enum):
    ORDINARY_LIMIT = "ordinary_limit"
    PROTECTION_CONDITIONAL = "protection_conditional"
    CONDITIONAL = "conditional"
    OTHER = "other"


class PresentationOrigin(str, Enum):
    TERMINAL_MANUAL = "terminal_manual"
    EXTERNAL_UNKNOWN = "external_unknown"


@dataclass(frozen=True, slots=True)
class CapabilitySettingsProjection:
    one_wv_usdt: Decimal | None
    buy_quick_volume: Decimal | None
    sell_quick_volume: Decimal | None
    market_slippage_type: str | None
    market_slippage_value: Decimal | None
    mutations_enabled: bool
    environment: str
    live_authorized: bool


@dataclass(frozen=True, slots=True)
class InstrumentProjection:
    symbol: str
    tick_size: Decimal
    quantity_step: Decimal
    min_order_quantity: Decimal
    max_order_quantity: Decimal
    max_market_order_quantity: Decimal
    min_notional_value: Decimal


@dataclass(frozen=True, slots=True)
class OrderProjection:
    entity_id: str
    entity_version: int
    account_id: str
    category: str
    symbol: str
    order_id: str
    order_link_id: str | None
    side: str
    price: Decimal | None
    original_quantity: Decimal
    cumulative_filled_quantity: Decimal
    remaining_quantity: Decimal
    remaining_notional: Decimal | None
    status: str
    pending_cancel: bool
    pending_amend: bool
    classification: OrderClassification
    origin: PresentationOrigin
    external: bool


@dataclass(frozen=True, slots=True)
class ChartOrderProjection:
    entity_id: str
    order_id: str
    side: str
    price: Decimal | None
    remaining_quantity: Decimal
    remaining_notional: Decimal | None
    status: str
    pending_cancel: bool
    pending_amend: bool
    external: bool


@dataclass(frozen=True, slots=True)
class PositionProjection:
    entity_id: str
    entity_version: int
    side: str
    size: Decimal
    position_value: Decimal | None
    average_entry: Decimal | None
    mark_price: Decimal | None
    unrealized_pnl: Decimal | None
    current_realized_pnl: Decimal | None
    cumulative_realized_pnl: Decimal | None
    exchange_status: str
    trust: str
    protection_status: str
    reopened_after_cleanup: bool


@dataclass(frozen=True, slots=True)
class ProtectionProjection:
    status: str
    take_profit: Decimal | None
    stop_loss: Decimal | None
    trailing_stop: Decimal | None
    pending_command_id: str | None
    warning: str | None


@dataclass(frozen=True, slots=True)
class CleanupItemProjection:
    order_id: str
    status: str


@dataclass(frozen=True, slots=True)
class CleanupProjection:
    cleanup_id: str | None
    cause: str | None
    lifecycle: str | None
    targeted_count: int
    pending_count: int
    cancelled_count: int
    filled_count: int
    unknown_count: int
    remaining_count: int
    items: tuple[CleanupItemProjection, ...]
    reopened_position_warning: bool


@dataclass(frozen=True, slots=True)
class ExecutionProjection:
    entity_id: str
    order_id: str
    symbol: str
    side: str
    price: Decimal
    quantity: Decimal
    fee: Decimal
    occurred_at_ms: int


@dataclass(frozen=True, slots=True)
class EventStreamBoundary:
    stream_id: str
    initial_event_sequence: int


@dataclass(frozen=True, slots=True)
class TerminalSnapshot:
    snapshot_id: str
    protocol_version: str
    account_id: str
    category: str
    symbol: str
    service_health: str
    trading_readiness: str
    connectivity: str
    trust_state: str
    reconciliation_generation: int
    position: PositionProjection | None
    active_orders: tuple[OrderProjection, ...]
    chart_orders: tuple[ChartOrderProjection, ...]
    executions: tuple[ExecutionProjection, ...]
    protection: ProtectionProjection
    cleanup: CleanupProjection
    instrument: InstrumentProjection
    warnings: tuple[str, ...]
    unresolved_command_ids: tuple[str, ...]
    capability: CapabilitySettingsProjection
    event_stream: EventStreamBoundary


@dataclass(frozen=True, slots=True)
class SnapshotFacts:
    snapshot_id: str
    stream_id: str
    position_key: PositionKey
    service_health: ServiceHealth
    connectivity: ConnectivityState
    trust_state: TrustState
    reconciliation_generation: int
    position: PositionEvent | None
    active_orders: tuple[OrderEvent, ...]
    executions: tuple[Execution, ...]
    commands: tuple[CommandRecord, ...]
    protection: ProtectionProjectionRecord | None
    cleanup_run: CleanupRunRecord | None
    cleanup_items: tuple[CleanupItemRecord, ...]
    instrument: InstrumentSnapshot
    warnings: tuple[str, ...]
    unresolved_command_ids: tuple[str, ...]
    capability: CapabilitySettingsProjection


def build_terminal_snapshot(facts: SnapshotFacts) -> TerminalSnapshot:
    key = facts.position_key
    orders = tuple(
        project_order(order, facts.commands)
        for order in facts.active_orders
        if _same_scope(order, key)
    )
    protection = project_protection(facts.protection)
    cleanup = project_cleanup(facts.cleanup_run, facts.cleanup_items)
    position = (
        project_position(facts.position, facts.trust_state, protection.status, cleanup)
        if facts.position is not None else None
    )
    executions = tuple(
        ExecutionProjection(
            item.dedup_key.exec_id.value, item.order_id.value, item.symbol.value,
            item.side.value, item.price.value, item.quantity.value, item.fee,
            item.exchange_timestamp_ms,
        )
        for item in facts.executions
        if item.dedup_key.trading_account_id == key.trading_account_id
        and item.dedup_key.category is key.category and item.symbol == key.symbol
    )
    warnings = list(facts.warnings)
    if protection.warning:
        warnings.append(protection.warning)
    if cleanup.reopened_position_warning:
        warnings.append("position reopened during confirmed-FLAT cleanup")
    return TerminalSnapshot(
        facts.snapshot_id, PROTOCOL_VERSION, key.trading_account_id.value,
        key.category.value, key.symbol.value, facts.service_health.value,
        _readiness(facts).value, facts.connectivity.value, facts.trust_state.value,
        facts.reconciliation_generation, position, orders,
        tuple(project_chart_order(order) for order in orders), executions,
        protection, cleanup, _project_instrument(facts.instrument), tuple(dict.fromkeys(warnings)),
        facts.unresolved_command_ids, facts.capability,
        EventStreamBoundary(facts.stream_id, 0),
    )


def project_order(order: OrderEvent, commands: tuple[CommandRecord, ...]) -> OrderProjection:
    correlated = tuple(command for command in commands if _command_matches(command, order))
    pending_cancel = any(
        command.command_kind == "cancel" and command.current_state in {
            CommandState.SUBMITTING, CommandState.ACKNOWLEDGED,
            CommandState.CANCEL_PENDING, CommandState.UNKNOWN,
        } for command in correlated
    )
    pending_amend = any(
        command.command_kind == "amend" and command.current_state in {
            CommandState.SUBMITTING, CommandState.ACKNOWLEDGED, CommandState.UNKNOWN,
        } for command in correlated
    )
    terminal = bool(correlated) or any(
        command.order_link_id == order.order_link_id for command in commands
        if order.order_link_id is not None
    )
    remaining_notional = (
        order.leaves_quantity * order.price if order.price is not None else None
    )
    return OrderProjection(
        order.order_id.value, max(0, order.updated_at_ms),
        order.trading_account_id.value, order.category.value, order.symbol,
        order.order_id.value, order.order_link_id, order.side.value, order.price,
        order.quantity, order.cumulative_filled_quantity, order.leaves_quantity,
        remaining_notional, order.status.value, pending_cancel, pending_amend,
        _classification(order),
        PresentationOrigin.TERMINAL_MANUAL if terminal else PresentationOrigin.EXTERNAL_UNKNOWN,
        not terminal,
    )


def project_chart_order(order: OrderProjection) -> ChartOrderProjection:
    return ChartOrderProjection(
        order.entity_id, order.order_id, order.side, order.price,
        order.remaining_quantity, order.remaining_notional, order.status,
        order.pending_cancel, order.pending_amend, order.external,
    )


def project_position(
    event: PositionEvent, trust: TrustState, protection_status: str,
    cleanup: CleanupProjection,
) -> PositionProjection:
    return PositionProjection(
        f"{event.position_key.symbol.value}:{event.position_key.position_idx}",
        max(0, event.updated_at_ms), event.side.value, event.size,
        event.position_value, event.average_entry, event.mark_price,
        event.unrealized_pnl, event.current_realized_pnl,
        event.cumulative_realized_pnl, event.status.value, trust.value,
        protection_status, cleanup.reopened_position_warning,
    )


def project_protection(record: ProtectionProjectionRecord | None) -> ProtectionProjection:
    if record is None:
        return ProtectionProjection(
            ProtectionState.NO_PROTECTION_CONFIGURED.value, None, None, None, None, None,
        )
    warning = None
    if record.status == ProtectionState.UNKNOWN.value:
        warning = "protection state requires reconciliation"
    elif record.status == ProtectionState.FAILED_UNPROTECTED.value:
        warning = "position is unprotected after failed protection mutation"
    return ProtectionProjection(
        record.status, record.take_profit, record.stop_loss, record.trailing_stop,
        record.pending_command_id.value if record.pending_command_id else None, warning,
    )


def project_cleanup(
    run: CleanupRunRecord | None, items: tuple[CleanupItemRecord, ...],
) -> CleanupProjection:
    if run is None:
        return CleanupProjection(None, None, None, 0, 0, 0, 0, 0, 0, (), False)
    statuses = tuple(item.status for item in items)
    final = {"cancelled", "filled", "final_not_active"}
    projected_items = tuple(CleanupItemProjection(item.order_id.value, item.status) for item in items)
    return CleanupProjection(
        run.cleanup_id, run.cause, run.status, len(items),
        sum(status in {"planned", "cancel_pending", "reconciling"} for status in statuses),
        statuses.count("cancelled"), statuses.count("filled"), statuses.count("unknown"),
        sum(status not in final for status in statuses), projected_items,
        run.status == CleanupStatus.REOPENED.value,
    )


def _classification(order: OrderEvent) -> OrderClassification:
    if (
        order.order_type is NormalizedOrderType.LIMIT and not order.stop_order_type
        and order.trigger_price is None and not order.close_on_trigger
    ):
        return OrderClassification.ORDINARY_LIMIT
    if order.take_profit is not None or order.stop_loss is not None or order.close_on_trigger:
        return OrderClassification.PROTECTION_CONDITIONAL
    if order.stop_order_type or order.trigger_price is not None:
        return OrderClassification.CONDITIONAL
    return OrderClassification.OTHER


def _command_matches(command: CommandRecord, order: OrderEvent) -> bool:
    return (
        command.exchange_order_id == order.order_id
        or (order.order_link_id is not None and command.order_link_id == order.order_link_id)
    )


def _same_scope(order: OrderEvent, key: PositionKey) -> bool:
    return (
        order.trading_account_id == key.trading_account_id and order.category is key.category
        and order.symbol == key.symbol.value and order.position_idx == key.position_idx
    )


def _project_instrument(value: InstrumentSnapshot) -> InstrumentProjection:
    return InstrumentProjection(
        value.symbol, value.tick_size, value.quantity_step, value.min_order_quantity,
        value.max_order_quantity, value.max_market_order_quantity, value.min_notional_value,
    )


def _readiness(facts: SnapshotFacts) -> TradingReadiness:
    if not facts.capability.mutations_enabled:
        return TradingReadiness.DISABLED
    if facts.connectivity is ConnectivityState.OFFLINE:
        return TradingReadiness.OFFLINE
    if facts.trust_state is TrustState.RECONCILING:
        return TradingReadiness.RECONCILING
    if facts.trust_state in {TrustState.UNTRUSTED_STARTUP, TrustState.FAILED_INCONSISTENT}:
        return TradingReadiness.UNKNOWN
    if facts.trust_state is TrustState.DEGRADED:
        return TradingReadiness.DEGRADED
    return TradingReadiness.READY
