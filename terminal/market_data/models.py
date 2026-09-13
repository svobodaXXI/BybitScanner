"""Normalized backend market-data models shared by execution consumers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from terminal.domain.models import Price, Quantity, Symbol


class BookHealth(str, Enum):
    NOT_READY = "NOT_READY"
    SYNCING = "SYNCING"
    READY = "READY"
    STALE = "STALE"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class PriceLevel:
    price: Price
    quantity: Quantity

    def __post_init__(self) -> None:
        if self.quantity.value <= 0:
            raise ValueError("book level quantity must be positive")


@dataclass(frozen=True, slots=True)
class NormalizedOrderBook:
    symbol: Symbol
    bids: tuple[PriceLevel, ...]
    asks: tuple[PriceLevel, ...]
    health: BookHealth
    received_at_ms: int
    available_depth: int
    source_generation: int | None = None
    source_sequence: int | None = None
    source_update_id: int | None = None
    source_event_at_ms: int | None = None
    source_matching_engine_cts_ms: int | None = None

    def __post_init__(self) -> None:
        if self.received_at_ms < 0:
            raise ValueError("received_at_ms must not be negative")
        if self.available_depth < 0:
            raise ValueError("available_depth must not be negative")
        if self.source_generation is not None and self.source_generation < 0:
            raise ValueError("source_generation must not be negative")
        if self.source_sequence is not None and self.source_sequence < 0:
            raise ValueError("source_sequence must not be negative")
        if self.source_update_id is not None and self.source_update_id < 0:
            raise ValueError("source_update_id must not be negative")
        if self.source_event_at_ms is not None and self.source_event_at_ms < 0:
            raise ValueError("source_event_at_ms must not be negative")
        if (
            self.source_matching_engine_cts_ms is not None
            and self.source_matching_engine_cts_ms < 0
        ):
            raise ValueError("source_matching_engine_cts_ms must not be negative")
