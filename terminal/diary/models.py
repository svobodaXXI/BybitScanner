"""Immutable Trading Diary D1 observational read models.

These types are downstream of Terminal execution authority. They never dispatch
orders and never replace terminal.domain / terminal.exchange identities.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from terminal.domain.models import (
    Category,
    Execution,
    ExecutionDedupKey,
    OrderSide,
    PositionKey,
    PositionSide,
    Price,
    Quantity,
)


@dataclass(frozen=True, slots=True, order=True)
class TradeEpisodeId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("trade episode id must be a non-empty string")
        object.__setattr__(self, "value", self.value.strip())


class DiaryEnvironment(str, Enum):
    PAPER = "PAPER"
    LIVE = "LIVE"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"


class AllocationRole(str, Enum):
    OPEN = "OPEN"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"
    REVERSAL_OPEN = "REVERSAL_OPEN"


@dataclass(frozen=True, slots=True)
class ExecutionFactView:
    """Diary view of an already-persisted immutable Terminal execution fact."""

    execution: Execution
    environment: DiaryEnvironment
    provenance: str = "TERMINAL_PERSISTED_EXECUTION"

    def __post_init__(self) -> None:
        if not isinstance(self.execution, Execution):
            raise TypeError("execution must be terminal.domain.models.Execution")
        if not isinstance(self.environment, DiaryEnvironment):
            object.__setattr__(self, "environment", DiaryEnvironment(self.environment))
        if not self.provenance.strip():
            raise ValueError("provenance must be non-empty")

    @property
    def dedup_key(self) -> ExecutionDedupKey:
        return self.execution.dedup_key


@dataclass(frozen=True, slots=True)
class ExecutionAllocation:
    execution_key: ExecutionDedupKey
    trade_episode_id: TradeEpisodeId
    role: AllocationRole
    quantity: Decimal
    fee: Decimal
    occurred_at_ms: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("allocation quantity must be positive")
        if not self.quantity.is_finite() or not self.fee.is_finite():
            raise ValueError("allocation decimals must be finite")
        if self.occurred_at_ms < 0:
            raise ValueError("allocation timestamp must not be negative")


@dataclass(frozen=True, slots=True)
class TradeEpisode:
    trade_episode_id: TradeEpisodeId
    position_key: PositionKey
    side: PositionSide
    environment: DiaryEnvironment
    opened_at_ms: int
    closed_at_ms: int | None
    opening_price: Price
    average_entry: Price
    open_quantity: Quantity
    realized_price_pnl: Decimal
    execution_fees: Decimal
    allocations: tuple[ExecutionAllocation, ...]

    def __post_init__(self) -> None:
        if self.side is PositionSide.FLAT:
            raise ValueError("trade episode side cannot be FLAT")
        if self.opened_at_ms < 0:
            raise ValueError("episode open timestamp must not be negative")
        if self.closed_at_ms is not None and self.closed_at_ms < self.opened_at_ms:
            raise ValueError("episode close timestamp precedes open")
        if self.open_quantity.value < 0:
            raise ValueError("episode open quantity must not be negative")
        if self.closed_at_ms is not None and self.open_quantity.value != 0:
            raise ValueError("closed episode must have zero open quantity")
        if not self.realized_price_pnl.is_finite() or not self.execution_fees.is_finite():
            raise ValueError("episode monetary values must be finite")
        if not self.allocations:
            raise ValueError("trade episode requires at least one allocation")

    @property
    def is_closed(self) -> bool:
        return self.closed_at_ms is not None


def position_key_for_execution(execution: Execution) -> PositionKey:
    return PositionKey(
        trading_account_id=execution.dedup_key.trading_account_id,
        category=Category(execution.dedup_key.category.value),
        symbol=execution.symbol,
        position_idx=0,
    )


def signed_quantity(side: OrderSide, quantity: Decimal) -> Decimal:
    return quantity if side is OrderSide.BUY else -quantity
