"""Percentage value object."""

from dataclasses import dataclass
from decimal import Decimal

from ._decimal import to_decimal


@dataclass(frozen=True, slots=True)
class Percentage:
    """A non-negative percentage stored in percentage points."""

    value: Decimal

    def __post_init__(self) -> None:
        value = to_decimal(self.value)
        if value < 0:
            raise ValueError("percentage must not be negative")
        object.__setattr__(self, "value", value)

    def to_ratio(self) -> Decimal:
        """Return the percentage as a ratio, e.g. 25% becomes 0.25."""
        return self.value / Decimal("100")

    @classmethod
    def from_ratio(cls, ratio: object) -> "Percentage":
        """Create a percentage from a ratio, e.g. 0.25 becomes 25%."""
        return cls(to_decimal(ratio) * Decimal("100"))

