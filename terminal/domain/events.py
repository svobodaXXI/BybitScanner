"""Normalized evidence types; no transport payloads or side effects."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CommandId, Execution, OrderId, PositionKey, PositionSide, Quantity
from .states import OrderState


@dataclass(frozen=True, slots=True)
class ExchangeAcknowledgement:
    """Acceptance evidence only; deliberately carries no fill fields."""

    command_id: CommandId
    accepted: bool
    order_id: OrderId | None = None


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    """Immutable economic evidence that may affect projections once."""

    execution: Execution


@dataclass(frozen=True, slots=True)
class OrderStateEvidence:
    order_id: OrderId
    state: OrderState
    remaining_quantity: Quantity


@dataclass(frozen=True, slots=True)
class PositionSnapshotEvidence:
    """Position state evidence, explicitly not execution/fill evidence."""

    position_key: PositionKey
    side: PositionSide
    quantity: Quantity

    def __post_init__(self) -> None:
        if self.side is PositionSide.FLAT and self.quantity.value != 0:
            raise ValueError("flat position must have zero quantity")
        if self.side is not PositionSide.FLAT and self.quantity.value == 0:
            raise ValueError("open position must have positive quantity")
