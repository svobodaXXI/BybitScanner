"""Risk value object."""

from dataclasses import dataclass

from .money import Money


@dataclass(frozen=True, slots=True)
class Risk:
    """A non-negative monetary risk amount."""

    amount: Money

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money):
            raise TypeError("risk amount must be Money")
        if self.amount.amount < 0:
            raise ValueError("risk must not be negative")

