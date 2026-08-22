"""Immutable orchestration contracts for execution-state reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from terminal.domain.models import PositionKey, PositionSide, Quantity
from terminal.exchange.events import (
    ExecutionEvent,
    OrderEvent,
    PositionEvent,
    StreamLifecycleEvent,
)
from terminal.persistence.sqlite_store import (
    CommandRecord,
    PositionProjectionRecord,
    ReconciliationCheckpointRecord,
)


class TrustState(str, Enum):
    """Reconciliation assessment, not a trading-permission state machine."""

    UNTRUSTED_STARTUP = "untrusted_startup"
    DEGRADED = "degraded"
    RECONCILING = "reconciling"
    CONVERGED = "converged"
    FAILED_INCONSISTENT = "failed_inconsistent"


class FlatCause(str, Enum):
    MARKET = "market"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    EXTERNAL_OTHER = "external_other"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class FlatTransitionEvidence:
    position_key: PositionKey
    previous_side: PositionSide
    previous_quantity: Quantity
    confirmed_position: PositionEvent
    confirmed_at_ms: int
    exchange_sequence: int | None
    cause: FlatCause

    def __post_init__(self) -> None:
        if self.previous_side is PositionSide.FLAT or self.previous_quantity.value <= 0:
            raise ValueError("FLAT transition requires a previously open position")
        if self.confirmed_position.position_key != self.position_key:
            raise ValueError("FLAT transition position scopes differ")
        if self.confirmed_position.side is not PositionSide.FLAT:
            raise ValueError("confirmed FLAT transition requires a flat snapshot")
        if self.confirmed_position.size != 0:
            raise ValueError("confirmed FLAT transition requires zero size")


@dataclass(frozen=True, slots=True)
class RecoveryBundle:
    """Complete normalized inputs supplied to one reconciliation attempt."""

    position_key: PositionKey
    position_snapshot: PositionEvent | None
    open_orders: tuple[OrderEvent, ...]
    order_history: tuple[OrderEvent, ...]
    executions: tuple[ExecutionEvent, ...]
    buffered_orders: tuple[OrderEvent, ...] = ()
    buffered_executions: tuple[ExecutionEvent, ...] = ()
    buffered_positions: tuple[PositionEvent, ...] = ()
    stream_lifecycle: tuple[StreamLifecycleEvent, ...] = ()
    unfinished_commands: tuple[CommandRecord, ...] = ()
    persisted_executions_count: int = 0
    persisted_projection: PositionProjectionRecord | None = None
    persisted_checkpoint: ReconciliationCheckpointRecord | None = None
    rest_position_complete: bool = True
    rest_orders_complete: bool = True
    rest_history_complete: bool = True
    rest_executions_complete: bool = True

    @property
    def authoritative_inputs_complete(self) -> bool:
        return (
            self.position_snapshot is not None
            and self.rest_position_complete
            and self.rest_orders_complete
            and self.rest_history_complete
            and self.rest_executions_complete
        )


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    trust_state: TrustState
    position_key: PositionKey
    active_orders: tuple[OrderEvent, ...]
    unresolved_command_ids: tuple[str, ...]
    applied_execution_count: int
    duplicate_execution_count: int
    checkpoint: ReconciliationCheckpointRecord | None
    flat_transition: FlatTransitionEvidence | None
    reasons: tuple[str, ...]

    @property
    def converged(self) -> bool:
        return self.trust_state is TrustState.CONVERGED
