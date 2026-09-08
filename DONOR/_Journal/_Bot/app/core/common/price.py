"""Price value object."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ._decimal import to_decimal


@dataclass(frozen=True, slots=True)
class Price:
    """A finite, non-negative instrument price."""

    value: Decimal

    def __post_init__(self) -> None:
        value = to_decimal(self.value)
        if value < 0:
            raise ValueError("price must not be negative")
        object.__setattr__(self, "value", value)

    def __sub__(self, other: object) -> Decimal | "Price":
        if isinstance(other, Price):
            return self.value - other.value
        return Price(self.value - to_decimal(other))

    def __add__(self, other: object) -> "Price":
        if isinstance(other, Price):
            return NotImplemented
        return Price(self.value + to_decimal(other))

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.value < other.value

    def __le__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.value <= other.value

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.value > other.value

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, Price):
            return NotImplemented
        return self.value >= other.value
