"""Durable confirmed-FLAT ordinary-Limit cleanup orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from terminal.application.command_identity import CommandIdentityCandidate, CommandIdentityFactory
from terminal.application.models import FlatCause, ReconciliationResult, TrustState
from terminal.application.trading_application import CancelIntent, TradingApplication
from terminal.domain.models import OrderId, PositionSide
from terminal.domain.states import CommandState, ConnectivityState
from terminal.exchange.events import NormalizedOrderStatus, NormalizedOrderType, OrderEvent, PositionEvent
from terminal.persistence.sqlite_store import CleanupItemRecord, CleanupRunRecord, SQLiteStore


class CleanupStatus(str, Enum):
    CANCELLING = "cancelling"
    RECONCILING = "reconciling"
    COMPLETE = "complete"
    DEFERRED_OFFLINE = "deferred_offline"
    REOPENED = "reopened"


_TRIGGER_CAUSES = {FlatCause.MARKET, FlatCause.STOP_LOSS, FlatCause.TAKE_PROFIT}
_FINAL_ITEM_STATES = {"cancelled", "filled", "final_not_active"}


@dataclass(frozen=True, slots=True)
class CleanupResult:
    run: CleanupRunRecord | None
    items: tuple[CleanupItemRecord, ...]
    triggered: bool


class ConfirmedFlatCleanupService:
    def __init__(
        self, store: SQLiteStore, trading: TradingApplication,
        identity_factory: CommandIdentityFactory | None = None,
    ) -> None:
        self._store = store
        self._trading = trading
        self._identity_factory = identity_factory or CommandIdentityFactory()

    def start(
        self, result: ReconciliationResult, *, connectivity: ConnectivityState,
    ) -> CleanupResult:
        flat = result.flat_transition
        if (
            not result.converged or flat is None or flat.cause not in _TRIGGER_CAUSES
            or result.checkpoint is None
        ):
            return CleanupResult(None, (), False)
        key = flat.position_key
        cleanup_id = (
            f"cleanup_{key.trading_account_id.value}_{key.symbol.value}_"
            f"{result.checkpoint.generation}_{flat.confirmed_at_ms}"
        )
        now = flat.confirmed_at_ms
        run = self._store.get_cleanup_run(cleanup_id)
        if run is None:
            run = self._store.create_cleanup_run(CleanupRunRecord(
                cleanup_id, key, flat.cause.value, result.checkpoint.generation,
                flat.confirmed_at_ms, CleanupStatus.CANCELLING.value, 1, now, now,
            ))
        selected = tuple(order for order in result.active_orders if is_ordinary_active_limit(order, key))
        for order in selected:
            item = self._store.get_cleanup_item(cleanup_id, order.order_id)
            if item is None:
                identity = self._identity_factory.create()
                item = self._store.add_cleanup_item(CleanupItemRecord(
                    cleanup_id, order.order_id, order.order_link_id, identity.command_id,
                    identity.order_link_id, "planned", 1, now, now,
                ))
            if connectivity is ConnectivityState.OFFLINE:
                continue
            if item.status != "planned" or self._store.get_command(item.cancel_command_id) is not None:
                continue
            identity = CommandIdentityCandidate(
                item.cancel_command_id, item.cancel_order_link_id,
            )
            cancel = self._trading.cancel(CancelIntent(
                key.trading_account_id, key.symbol.value, order.side, order,
                order_id=order.order_id.value, identity=identity,
            ))
            state = _item_state(cancel.command.current_state)
            self._store.update_cleanup_item(
                cleanup_id, item.order_id, expected_version=item.version,
                status=state, updated_at_ms=now,
            )
        if connectivity is ConnectivityState.OFFLINE:
            run = self._store.update_cleanup_run(
                cleanup_id, expected_version=run.version,
                status=CleanupStatus.DEFERRED_OFFLINE.value, updated_at_ms=now,
            )
        elif selected:
            run = self._store.update_cleanup_run(
                cleanup_id, expected_version=run.version,
                status=CleanupStatus.RECONCILING.value, updated_at_ms=now,
            )
        else:
            run = self._store.update_cleanup_run(
                cleanup_id, expected_version=run.version,
                status=CleanupStatus.COMPLETE.value, updated_at_ms=now,
            )
        return CleanupResult(run, self._store.load_cleanup_items(cleanup_id), True)

    def reconcile(
        self, cleanup_id: str, *, position: PositionEvent,
        active_orders: tuple[OrderEvent, ...], observed_orders: tuple[OrderEvent, ...],
        occurred_at_ms: int,
    ) -> CleanupResult:
        run = self._store.get_cleanup_run(cleanup_id)
        if run is None:
            raise ValueError("cleanup run does not exist")
        facts = {order.order_id: order for order in observed_orders + active_orders}
        for item in self._store.load_cleanup_items(cleanup_id):
            fact = facts.get(item.order_id)
            if fact is None:
                continue
            if fact.status is NormalizedOrderStatus.CANCELLED:
                status = "cancelled"
            elif fact.status is NormalizedOrderStatus.FILLED:
                status = "filled"
            else:
                continue
            if item.status != status:
                self._store.update_cleanup_item(
                    cleanup_id, item.order_id, expected_version=item.version,
                    status=status, updated_at_ms=occurred_at_ms,
                )
        remaining = tuple(order for order in active_orders if is_ordinary_active_limit(order, run.position_key))
        items = self._store.load_cleanup_items(cleanup_id)
        if position.side is not PositionSide.FLAT or position.size != 0:
            status = CleanupStatus.REOPENED
        elif remaining or any(item.status not in _FINAL_ITEM_STATES for item in items):
            status = CleanupStatus.RECONCILING
        else:
            status = CleanupStatus.COMPLETE
        if run.status != status.value:
            run = self._store.update_cleanup_run(
                cleanup_id, expected_version=run.version,
                status=status.value, updated_at_ms=occurred_at_ms,
            )
        return CleanupResult(run, self._store.load_cleanup_items(cleanup_id), True)


def is_ordinary_active_limit(order: OrderEvent, key) -> bool:
    return (
        order.trading_account_id == key.trading_account_id
        and order.category is key.category
        and order.symbol == key.symbol.value
        and order.position_idx == key.position_idx
        and order.order_type is NormalizedOrderType.LIMIT
        and order.status in {NormalizedOrderStatus.OPEN, NormalizedOrderStatus.PARTIALLY_FILLED_OPEN}
        and not order.stop_order_type
        and order.trigger_price is None
        and not order.close_on_trigger
    )


def _item_state(state: CommandState) -> str:
    return {
        CommandState.CANCEL_PENDING: "cancel_pending",
        CommandState.UNKNOWN: "unknown",
        CommandState.REJECTED: "rejected",
        CommandState.FAILED: "failed",
    }.get(state, "reconciling")
