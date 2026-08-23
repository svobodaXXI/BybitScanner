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

    def __post_init__(self) -> None:
        if self.received_at_ms < 0:
            raise ValueError("received_at_ms must not be negative")
        if self.available_depth < 0:
            raise ValueError("available_depth must not be negative")
