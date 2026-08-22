"""Single offline owner for applying normalized exchange facts to durable state."""

from __future__ import annotations

from decimal import Decimal

from terminal.domain.models import (
    CommandId,
    Execution,
    Notional,
    OrderId,
    OrderSide,
    PositionSide,
    Price,
    Quantity,
    Symbol,
)
from terminal.domain.states import COMMAND_TRANSITIONS, CommandState
from terminal.exchange.events import (
    ExecutionEvent,
    NormalizedOrderStatus,
    OrderEvent,
    PositionEvent,
)
from terminal.exchange.bybit_v5_mutation_adapter import (
    MutationDisposition,
    MutationKind,
    MutationOutcome,
)
from terminal.persistence.sqlite_store import (
    CommandRecord,
    ExecutionApplyResult,
    PositionProjectionRecord,
    PositionProjectionUpdate,
    SQLiteStore,
    ProtectionProjectionRecord,
)
from terminal.application.models import ProtectionEvidence, ProtectionState


_ACTIVE_ORDER_STATES = frozenset(
    {
        NormalizedOrderStatus.PENDING_TRIGGER,
        NormalizedOrderStatus.OPEN,
        NormalizedOrderStatus.PARTIALLY_FILLED_OPEN,
        NormalizedOrderStatus.UNKNOWN,
    }
)


class ExecutionEngine:
    """Applies facts through Stage 0 policies and Stage 1 atomic persistence."""

    def __init__(self, store: SQLiteStore):
        self._store = store
        self._orders: dict[str, OrderEvent] = {}

    @property
    def store(self) -> SQLiteStore:
        return self._store

    @property
    def active_orders(self) -> tuple[OrderEvent, ...]:
        return tuple(sorted(self._orders.values(), key=lambda item: (item.symbol, item.order_id.value)))

    def replace_order_inventory(self, orders: tuple[OrderEvent, ...]) -> None:
        """Accept a complete exchange inventory without inferring ownership."""

        inventory: dict[str, OrderEvent] = {}
        for order in orders:
            if order.status in _ACTIVE_ORDER_STATES:
                inventory[order.order_id.value] = order
        self._orders = inventory

    def ingest_order(self, order: OrderEvent) -> None:
        if order.status in _ACTIVE_ORDER_STATES:
            self._orders[order.order_id.value] = order
        else:
            self._orders.pop(order.order_id.value, None)

    def ingest_mutation_outcome(
        self,
        command: CommandRecord,
        outcome: MutationOutcome,
        *,
        occurred_at_ms: int,
    ) -> CommandRecord:
        """Persist one REST mutation outcome without inventing final order facts."""

        current = self._store.get_command(command.command_id)
        if current is None:
            raise ValueError("mutation outcome references an unknown command")
        if current.current_state is not CommandState.SUBMITTING:
            return current
        order_id = OrderId(outcome.order_id) if outcome.order_id else None
        if outcome.disposition is MutationDisposition.REJECTED:
            return self._transition(
                current, CommandState.REJECTED, occurred_at_ms,
                outcome.reason or "deterministic exchange rejection", order_id,
            )
        if outcome.disposition is MutationDisposition.UNKNOWN:
            return self._transition(
                current, CommandState.UNKNOWN, occurred_at_ms,
                outcome.reason or "mutation outcome is ambiguous", order_id,
            )
        acknowledged = self._transition(
            current, CommandState.ACKNOWLEDGED, occurred_at_ms,
            outcome.reason or "exchange acknowledged mutation", order_id,
        )
        if outcome.kind is MutationKind.CANCEL:
            return self._transition(
                acknowledged, CommandState.CANCEL_PENDING, occurred_at_ms,
                "cancel ACK awaits confirmed order evidence", order_id,
            )
        return acknowledged

    def ingest_protection_evidence(
        self, evidence: ProtectionEvidence,
    ) -> ProtectionProjectionRecord:
        """Project only Bybit protection facts and resolve a matching pending intent."""

        current = self._store.get_protection_projection(evidence.position_key)
        pending_id = current.pending_command_id if current is not None else None
        state = (
            ProtectionState.CONFIRMED_ACTIVE
            if any(value is not None and value != 0 for value in (
                evidence.take_profit, evidence.stop_loss, evidence.trailing_stop
            ))
            else ProtectionState.NO_PROTECTION_CONFIGURED
        )
        if pending_id is not None:
            intent = self._store.get_protection_intent(pending_id)
            command = self._store.get_command(pending_id)
            matches = intent is not None and (
                (intent.take_profit or Decimal("0")) == (evidence.take_profit or Decimal("0"))
                and (intent.stop_loss or Decimal("0")) == (evidence.stop_loss or Decimal("0"))
            )
            if matches and command is not None and command.current_state is CommandState.ACKNOWLEDGED:
                self._transition(
                    command, CommandState.AMENDED, evidence.evidence_at_ms,
                    "Bybit protection evidence confirmed desired state", None,
                )
                self._store.update_protection_intent_status(
                    pending_id, status=state.value, updated_at_ms=evidence.evidence_at_ms,
                )
                pending_id = None
            elif not matches:
                state = ProtectionState.UNKNOWN
                if command is not None and command.current_state is CommandState.ACKNOWLEDGED:
                    self._transition(
                        command, CommandState.UNKNOWN, evidence.evidence_at_ms,
                        "Bybit protection evidence does not confirm desired state", None,
                    )
                if intent is not None:
                    self._store.update_protection_intent_status(
                        pending_id, status=state.value, updated_at_ms=evidence.evidence_at_ms,
                    )
        record = ProtectionProjectionRecord(
            evidence.position_key, state.value, evidence.take_profit, evidence.stop_loss,
            evidence.trailing_stop, pending_id,
            current.version if current else 1, evidence.evidence_at_ms, evidence.evidence_at_ms,
        )
        return self._store.upsert_protection_projection(
            record, expected_version=current.version if current else None,
        )

    def apply_execution(self, event: ExecutionEvent) -> ExecutionApplyResult:
        """Apply one immutable economic fact at most once."""

        execution = _domain_execution(event)
        current = self._store.get_position_projection(
            _position_key_for_execution(event, self._orders)
        )
        projection = _projection_after_execution(event, current)
        command = self._find_command(event.order_link_id, event.order_id.value)
        return self._store.apply_execution_once(
            execution,
            projection,
            command_id=command.command_id if command is not None else None,
        )

    def projection_from_authoritative_position(
        self,
        event: PositionEvent,
        *,
        sync_state: str,
    ) -> PositionProjectionUpdate:
        """Translate a supplied Bybit snapshot without fabricating an execution."""

        current = self._store.get_position_projection(event.position_key)
        realized_pnl = _first_decimal(
            event.cumulative_realized_pnl,
            event.current_realized_pnl,
            current.realized_pnl if current is not None else Decimal("0"),
        )
        accumulated_fee = current.accumulated_fee if current is not None else Decimal("0")
        if event.side is PositionSide.FLAT:
            average_entry = None
            engaged_notional = Decimal("0")
        else:
            average_entry = event.average_entry
            if event.position_value is not None:
                engaged_notional = abs(event.position_value)
            elif average_entry is not None:
                engaged_notional = event.size * average_entry
            else:
                engaged_notional = Decimal("0")
        return PositionProjectionUpdate(
            position_key=event.position_key,
            side=event.side,
            quantity=Quantity(event.size),
            average_entry=Price(average_entry) if average_entry is not None else None,
            realized_pnl=realized_pnl,
            accumulated_fee=accumulated_fee,
            engaged_notional=Notional(engaged_notional),
            sync_state=sync_state,
            expected_version=current.version if current is not None else None,
            updated_at_ms=event.updated_at_ms,
        )

    def resolve_command(
        self,
        command: CommandRecord,
        *,
        order_evidence: tuple[OrderEvent, ...],
        execution_evidence: tuple[ExecutionEvent, ...],
        occurred_at_ms: int,
    ) -> CommandRecord:
        """Resolve one command from sufficient multi-source normalized evidence."""

        matching_orders = tuple(item for item in order_evidence if _matches_command(command, item))
        matching_executions = tuple(
            item for item in execution_evidence if _execution_matches_command(command, item)
        )
        order_id = _correlated_order_id(matching_orders, matching_executions)
        target = _command_target(command, matching_orders, matching_executions)
        if target is None:
            if command.current_state is CommandState.SUBMITTING:
                return self._transition(
                    command,
                    CommandState.UNKNOWN,
                    occurred_at_ms,
                    "submission outcome remains unknown after reconciliation",
                    order_id,
                )
            return command
        return self._transition_via_reconciliation(
            command,
            target,
            occurred_at_ms,
            "normalized exchange evidence resolved command",
            order_id,
        )

    def _transition_via_reconciliation(
        self,
        command: CommandRecord,
        target: CommandState,
        occurred_at_ms: int,
        reason: str,
        order_id,
    ) -> CommandRecord:
        if command.current_state is target or command.current_state in {
            CommandState.FILLED,
            CommandState.CANCELLED,
            CommandState.REJECTED,
            CommandState.FAILED,
        }:
            return command
        if target in COMMAND_TRANSITIONS[command.current_state]:
            return self._transition(command, target, occurred_at_ms, reason, order_id)
        if CommandState.RECONCILING not in COMMAND_TRANSITIONS[command.current_state]:
            return command
        reconciling = self._transition(
            command,
            CommandState.RECONCILING,
            occurred_at_ms,
            "authoritative reconciliation started for command",
            order_id,
        )
        if target not in COMMAND_TRANSITIONS[reconciling.current_state]:
            return reconciling
        return self._transition(reconciling, target, occurred_at_ms, reason, order_id)

    def _transition(
        self,
        command: CommandRecord,
        target: CommandState,
        occurred_at_ms: int,
        reason: str,
        order_id,
    ) -> CommandRecord:
        return self._store.transition_command_state(
            command.command_id,
            command.current_state,
            target,
            expected_version=command.version,
            reason=reason,
            occurred_at_ms=occurred_at_ms,
            exchange_order_id=order_id,
        )

    def _find_command(self, order_link_id: str | None, order_id: str) -> CommandRecord | None:
        for command in self._store.load_unfinished_commands():
            if order_link_id and command.order_link_id == order_link_id:
                return command
            if command.exchange_order_id is not None and command.exchange_order_id.value == order_id:
                return command
        return None


def _domain_execution(event: ExecutionEvent) -> Execution:
    return Execution(
        dedup_key=event.dedup_identity,
        order_id=event.order_id,
        symbol=Symbol(event.symbol),
        side=event.side,
        price=Price(event.execution_price),
        quantity=Quantity(event.execution_quantity),
        fee=event.execution_fee,
        exchange_timestamp_ms=event.executed_at_ms,
    )


def _position_key_for_execution(event: ExecutionEvent, orders: dict[str, OrderEvent]):
    order = orders.get(event.order_id.value)
    if order is not None:
        return _position_key_from_order(order)
    from terminal.domain.models import PositionKey

    return PositionKey(event.trading_account_id, event.category, Symbol(event.symbol), 0)


def _position_key_from_order(order: OrderEvent):
    from terminal.domain.models import PositionKey

    return PositionKey(
        order.trading_account_id,
        order.category,
        Symbol(order.symbol),
        order.position_idx,
    )


def _projection_after_execution(
    event: ExecutionEvent,
    current: PositionProjectionRecord | None,
) -> PositionProjectionUpdate:
    current_quantity = current.quantity.value if current is not None else Decimal("0")
    current_side = current.side if current is not None else PositionSide.FLAT
    signed_current = _signed_quantity(current_side, current_quantity)
    signed_fill = event.execution_quantity if event.side is OrderSide.BUY else -event.execution_quantity
    signed_result = signed_current + signed_fill
    result_side = (
        PositionSide.LONG
        if signed_result > 0
        else PositionSide.SHORT
        if signed_result < 0
        else PositionSide.FLAT
    )
    result_quantity = abs(signed_result)
    old_average = current.average_entry.value if current and current.average_entry else None
    average = _average_after_fill(
        signed_current,
        old_average,
        signed_fill,
        event.execution_price,
        signed_result,
    )
    realized_delta = _realized_pnl(
        signed_current,
        old_average,
        signed_fill,
        event.execution_price,
    )
    realized = (current.realized_pnl if current else Decimal("0")) + realized_delta
    fees = (current.accumulated_fee if current else Decimal("0")) + event.execution_fee
    engaged = result_quantity * average if average is not None else Decimal("0")
    return PositionProjectionUpdate(
        position_key=_position_key_for_execution(event, {}),
        side=result_side,
        quantity=Quantity(result_quantity),
        average_entry=Price(average) if average is not None else None,
        realized_pnl=realized,
        accumulated_fee=fees,
        engaged_notional=Notional(engaged),
        sync_state="reconciliation_required",
        expected_version=current.version if current is not None else None,
        updated_at_ms=event.executed_at_ms,
    )


def _signed_quantity(side: PositionSide, quantity: Decimal) -> Decimal:
    if side is PositionSide.LONG:
        return quantity
    if side is PositionSide.SHORT:
        return -quantity
    return Decimal("0")


def _average_after_fill(
    current: Decimal,
    current_average: Decimal | None,
    fill: Decimal,
    fill_price: Decimal,
    result: Decimal,
) -> Decimal | None:
    if result == 0:
        return None
    if current == 0 or current * fill > 0:
        if current == 0 or current_average is None:
            return fill_price
        return (
            abs(current) * current_average + abs(fill) * fill_price
        ) / abs(result)
    if current * result > 0:
        return current_average
    return fill_price


def _realized_pnl(
    current: Decimal,
    current_average: Decimal | None,
    fill: Decimal,
    fill_price: Decimal,
) -> Decimal:
    if current == 0 or current_average is None or current * fill >= 0:
        return Decimal("0")
    closed = min(abs(current), abs(fill))
    if current > 0:
        return closed * (fill_price - current_average)
    return closed * (current_average - fill_price)


def _first_decimal(*values: Decimal | None) -> Decimal:
    for value in values:
        if value is not None:
            return value
    return Decimal("0")


def _matches_command(command: CommandRecord, order: OrderEvent) -> bool:
    return (
        order.order_link_id == command.order_link_id
        or (
            command.exchange_order_id is not None
            and order.order_id == command.exchange_order_id
        )
    )


def _execution_matches_command(command: CommandRecord, execution: ExecutionEvent) -> bool:
    return (
        execution.order_link_id == command.order_link_id
        or (
            command.exchange_order_id is not None
            and execution.order_id == command.exchange_order_id
        )
    )


def _correlated_order_id(orders, executions):
    if orders:
        return orders[-1].order_id
    if executions:
        return executions[-1].order_id
    return None


def _command_target(command, orders, executions):
    if orders:
        latest = max(orders, key=lambda item: item.updated_at_ms)
        if command.command_kind == "cancel":
            if latest.status is NormalizedOrderStatus.CANCELLED:
                return CommandState.CANCELLED
            if latest.status is NormalizedOrderStatus.FILLED:
                return CommandState.FILLED
            return None
        if (
            command.command_kind == "amend"
            and latest.updated_at_ms >= command.created_at_ms
            and latest.status in {
                NormalizedOrderStatus.OPEN,
                NormalizedOrderStatus.PARTIALLY_FILLED_OPEN,
            }
            and _matches_amend_evidence(command, latest)
        ):
            return CommandState.AMENDED
        mapping = {
            NormalizedOrderStatus.OPEN: CommandState.OPEN,
            NormalizedOrderStatus.PARTIALLY_FILLED_OPEN: CommandState.PARTIALLY_FILLED,
            NormalizedOrderStatus.FILLED: CommandState.FILLED,
            NormalizedOrderStatus.CANCELLED: CommandState.CANCELLED,
            NormalizedOrderStatus.REJECTED: CommandState.REJECTED,
        }
        target = mapping.get(latest.status)
        if target is not None:
            return target
    if executions:
        filled = sum((item.execution_quantity for item in executions), Decimal("0"))
        requested = (
            command.normalized_quantity.value
            if command.normalized_quantity is not None
            else None
        )
        if requested is not None and filled >= requested:
            return CommandState.FILLED
        return CommandState.PARTIALLY_FILLED
    return None


def _matches_amend_evidence(command: CommandRecord, order: OrderEvent) -> bool:
    price_matches = (
        command.normalized_price is None
        or order.price == command.normalized_price.value
    )
    quantity_matches = (
        command.normalized_quantity is None
        or order.quantity == command.normalized_quantity.value
    )
    return price_matches and quantity_matches
