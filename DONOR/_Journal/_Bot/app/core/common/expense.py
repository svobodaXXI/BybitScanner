"""Expense value object."""

from dataclasses import dataclass

from .money import Money


@dataclass(frozen=True, slots=True)
class Expense:
    """A signed monetary adjustment that preserves its economic sign."""

    amount: Money

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Money):
            raise TypeError("expense amount must be Money")

