"""Offline startup/reconnect convergence over normalized exchange evidence."""

from __future__ import annotations

from terminal.domain.models import PositionSide, Quantity
from terminal.domain.states import CommandState
from terminal.exchange.events import (
    NormalizedOrderStatus,
    NormalizedOrderType,
    StreamLifecycleKind,
)
from terminal.persistence.sqlite_store import (
    ExecutionApplyResult,
    ReconciliationCheckpointUpdate,
)

from .execution_engine import ExecutionEngine
from .models import (
    FlatCause,
    FlatTransitionEvidence,
    ReconciliationResult,
    RecoveryBundle,
    TrustState,
)


_UNRESOLVED_COMMAND_STATES = frozenset(
    {
        CommandState.SUBMITTING,
        CommandState.UNKNOWN,
        CommandState.RECONCILING,
        CommandState.CANCEL_PENDING,
    }
)


class ReconciliationCoordinator:
    """Coordinates facts; all business-state application remains in ExecutionEngine."""

    def __init__(self, engine: ExecutionEngine):
        self._engine = engine
        self._store = engine.store

    def reconcile(
        self,
        bundle: RecoveryBundle,
        *,
        generation: int,
        started_at_ms: int,
        completed_at_ms: int,
    ) -> ReconciliationResult:
        current_checkpoint = self._store.get_reconciliation_checkpoint(bundle.position_key)
        checkpoint = self._store.begin_reconciliation(
            bundle.position_key,
            generation=generation,
            exchange_snapshot_at_ms=started_at_ms,
            exchange_sequence=None,
            started_at_ms=started_at_ms,
            expected_version=current_checkpoint.version if current_checkpoint else None,
            updated_at_ms=started_at_ms,
        )
        reasons: list[str] = []
        if not _bundle_scope_is_consistent(bundle):
            reasons.append("normalized evidence contains a mismatched account/symbol scope")
            return self._result(
                bundle,
                TrustState.FAILED_INCONSISTENT,
                (),
                0,
                0,
                checkpoint,
                None,
                reasons,
            )

        self._engine.replace_order_inventory(bundle.open_orders)
        for order in sorted(bundle.buffered_orders, key=lambda item: item.updated_at_ms):
            self._engine.ingest_order(order)

        try:
            execution_evidence = _validated_execution_sequence(
                bundle.executions + bundle.buffered_executions
            )
        except ValueError as exc:
            reasons.append(str(exc))
            return self._result(
                bundle,
                TrustState.FAILED_INCONSISTENT,
                (),
                0,
                0,
                checkpoint,
                None,
                reasons,
            )
        applied = 0
        duplicates = 0
        for execution in execution_evidence:
            result = self._engine.apply_execution(execution)
            if result is ExecutionApplyResult.APPLIED:
                applied += 1
            else:
                duplicates += 1

        all_orders = bundle.open_orders + bundle.order_history + bundle.buffered_orders
        unresolved: list[str] = []
        for supplied in bundle.unfinished_commands:
            command = self._store.get_command(supplied.command_id) or supplied
            resolved = self._engine.resolve_command(
                command,
                order_evidence=all_orders,
                execution_evidence=execution_evidence,
                occurred_at_ms=completed_at_ms,
            )
            if resolved.current_state in _UNRESOLVED_COMMAND_STATES:
                unresolved.append(resolved.command_id.value)

        position = _latest_position(bundle)
        if not bundle.authoritative_inputs_complete or position is None:
            reasons.append("authoritative REST recovery inputs are incomplete")
            return self._result(
                bundle,
                TrustState.RECONCILING,
                tuple(unresolved),
                applied,
                duplicates,
                checkpoint,
                None,
                reasons,
            )

        lifecycle_trusted = _lifecycle_permits_convergence(bundle)
        if not lifecycle_trusted:
            reasons.append("private stream lifecycle remains untrusted")
        if unresolved:
            reasons.append("one or more command outcomes remain unresolved")

        previous = self._store.get_position_projection(bundle.position_key)
        flat_transition = _flat_transition(bundle, previous, position)
        trust = (
            TrustState.CONVERGED
            if lifecycle_trusted and not unresolved
            else TrustState.RECONCILING
        )
        projection = self._engine.projection_from_authoritative_position(
            position,
            sync_state=(
                "synchronized" if trust is TrustState.CONVERGED else "reconciliation_required"
            ),
        )
        checkpoint_update = ReconciliationCheckpointUpdate(
            position_key=bundle.position_key,
            generation=generation,
            outcome=trust.value,
            exchange_snapshot_at_ms=position.updated_at_ms,
            exchange_sequence=position.sequence,
            started_at_ms=started_at_ms,
            completed_at_ms=completed_at_ms,
            expected_version=checkpoint.version,
            updated_at_ms=completed_at_ms,
        )
        _, committed_checkpoint = self._store.commit_authoritative_position_snapshot(
            projection,
            checkpoint_update,
        )
        return self._result(
            bundle,
            trust,
            tuple(unresolved),
            applied,
            duplicates,
            committed_checkpoint,
            flat_transition,
            reasons,
        )

    def _result(
        self,
        bundle,
        trust,
        unresolved,
        applied,
        duplicates,
        checkpoint,
        flat_transition,
        reasons,
    ) -> ReconciliationResult:
        return ReconciliationResult(
            trust_state=trust,
            position_key=bundle.position_key,
            active_orders=self._engine.active_orders,
            unresolved_command_ids=unresolved,
            applied_execution_count=applied,
            duplicate_execution_count=duplicates,
            checkpoint=checkpoint,
            flat_transition=flat_transition,
            reasons=tuple(reasons),
        )


def _bundle_scope_is_consistent(bundle: RecoveryBundle) -> bool:
    key = bundle.position_key
    events = (
        bundle.open_orders
        + bundle.order_history
        + bundle.buffered_orders
        + bundle.executions
        + bundle.buffered_executions
    )
    for event in events:
        if event.trading_account_id != key.trading_account_id:
            return False
        if event.category is not key.category or event.symbol != key.symbol.value:
            return False
    positions = tuple(item for item in (bundle.position_snapshot,) if item is not None) + bundle.buffered_positions
    if not all(item.position_key == key for item in positions):
        return False
    if not all(item.trading_account_id == key.trading_account_id for item in bundle.stream_lifecycle):
        return False
    if not all(
        item.trading_account_id == key.trading_account_id
        and item.category is key.category
        and item.symbol == key.symbol
        and item.position_idx == key.position_idx
        for item in bundle.unfinished_commands
    ):
        return False
    if bundle.persisted_projection is not None and bundle.persisted_projection.position_key != key:
        return False
    if bundle.persisted_checkpoint is not None and bundle.persisted_checkpoint.position_key != key:
        return False
    return True


def _validated_execution_sequence(events):
    unique = {}
    for event in events:
        existing = unique.get(event.dedup_identity)
        if existing is not None and existing != event:
            raise ValueError("one execution identity carries conflicting normalized evidence")
        unique[event.dedup_identity] = event
    return tuple(
        sorted(
            events,
            key=lambda item: (item.executed_at_ms, item.exec_id.value),
        )
    )


def _latest_position(bundle: RecoveryBundle):
    candidates = tuple(item for item in (bundle.position_snapshot,) if item is not None) + bundle.buffered_positions
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item.updated_at_ms, item.sequence or -1))


def _lifecycle_permits_convergence(bundle: RecoveryBundle) -> bool:
    if not bundle.stream_lifecycle:
        return True
    latest = bundle.stream_lifecycle[-1].kind
    return latest is StreamLifecycleKind.CONNECTED_UNTRUSTED


def _flat_transition(bundle, previous, position):
    if (
        previous is None
        or previous.side is PositionSide.FLAT
        or previous.quantity.value <= 0
        or position.side is not PositionSide.FLAT
        or position.size != 0
    ):
        return None
    return FlatTransitionEvidence(
        position_key=bundle.position_key,
        previous_side=previous.side,
        previous_quantity=previous.quantity,
        confirmed_position=position,
        confirmed_at_ms=position.updated_at_ms,
        exchange_sequence=position.sequence,
        cause=_flat_cause(bundle, previous.side),
    )


def _flat_cause(bundle: RecoveryBundle, previous_side: PositionSide) -> FlatCause:
    closing_side = "Sell" if previous_side is PositionSide.LONG else "Buy"
    candidates = [
        order
        for order in bundle.order_history + bundle.buffered_orders
        if order.status is NormalizedOrderStatus.FILLED and order.side.value == closing_side
    ]
    if len(candidates) != 1:
        return FlatCause.UNKNOWN
    order = candidates[0]
    stop_type = (order.stop_order_type or "").lower()
    if "stoploss" in stop_type or stop_type in {"sl", "stop_loss"}:
        return FlatCause.STOP_LOSS
    if "takeprofit" in stop_type or stop_type in {"tp", "take_profit"}:
        return FlatCause.TAKE_PROFIT
    if order.order_type is NormalizedOrderType.MARKET:
        return FlatCause.MARKET
    if not order.order_link_id:
        return FlatCause.EXTERNAL_OTHER
    return FlatCause.UNKNOWN
