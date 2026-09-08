"""Quantity value object."""

from dataclasses import dataclass
from decimal import Decimal

from ._decimal import to_decimal


@dataclass(frozen=True, slots=True)
class Quantity:
    """A finite, non-negative quantity of an instrument or contract."""

    value: Decimal

    def __post_init__(self) -> None:
        value = to_decimal(self.value)
        if value < 0:
            raise ValueError("quantity must not be negative")
        object.__setattr__(self, "value", value)

    def __add__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        return Quantity(self.value + other.value)

    def __sub__(self, other: object) -> "Quantity":
        if not isinstance(other, Quantity):
            return NotImplemented
        result = self.value - other.value
        if result < 0:
            raise ValueError("quantity subtraction must not produce a negative value")
        return Quantity(result)

    def __mul__(self, multiplier: object) -> "Quantity":
        if isinstance(multiplier, Quantity):
            return NotImplemented
        return Quantity(self.value * to_decimal(multiplier))

    def __rmul__(self, multiplier: object) -> "Quantity":
        return self.__mul__(multiplier)

    def __truediv__(self, divisor: object) -> "Quantity":
        if isinstance(divisor, Quantity):
            return NotImplemented
        return Quantity(self.value / to_decimal(divisor))

