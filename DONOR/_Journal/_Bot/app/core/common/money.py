"""Money value object."""

from dataclasses import dataclass
from decimal import Decimal

from ._decimal import to_decimal


@dataclass(frozen=True, slots=True)
class Money:
    """A monetary amount associated with a normalized currency code."""

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        amount = to_decimal(self.amount)
        if not isinstance(self.currency, str):
            raise TypeError("currency must be a string")

        currency = self.currency.strip().upper()
        if not currency:
            raise ValueError("currency must not be empty")

        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)

    def _ensure_same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise ValueError("money currencies must match")

    def __add__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        self._ensure_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, multiplier: object) -> "Money":
        if isinstance(multiplier, Money):
            return NotImplemented
        return Money(self.amount * to_decimal(multiplier), self.currency)

    def __rmul__(self, multiplier: object) -> "Money":
        return self.__mul__(multiplier)

    def __truediv__(self, divisor: object) -> "Money":
        if isinstance(divisor, Money):
            return NotImplemented
        return Money(self.amount / to_decimal(divisor), self.currency)

