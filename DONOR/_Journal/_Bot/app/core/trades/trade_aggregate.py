"""Execution-reconstruction state for one logical journal trade."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity

from .enums import TradeDirection, TradeStatus
from .execution import Execution
from .trade_id import TradeId


@dataclass(slots=True)
class TradeAggregate:
    """Mutable reconstruction state, distinct from the Phase 1 ``Trade`` record."""

    trade_id: TradeId
    account_id: object
    instrument_id: object
    direction: TradeDirection
    status: TradeStatus
    open_quantity: Quantity
    average_entry: Price
    realized_quantity: Quantity
    realized_gross_pnl: Money
    total_fees: Money
    expenses: tuple[Expense, ...]
    net_realized_pnl: Money
    execution_count: int
    applied_execution_ids: tuple[object, ...]
    executions: tuple[Execution, ...]
    opened_at: object
    closed_at: object | None
    _entry_notional: Decimal = field(repr=False, compare=False)

    @property
    def open_qty(self) -> Quantity:
        """Short alias for inspection and manual acceptance flows."""
        return self.open_quantity

    @property
    def avg_entry(self) -> Price:
        """Short alias for the weighted average entry price."""
        return self.average_entry

    @property
    def realized_pnl(self) -> Money:
        """Gross realized PnL, retained as an explicit alias."""
        return self.realized_gross_pnl

    @property
    def fees(self) -> Money:
        return self.total_fees

    @classmethod
    def open_from_execution(cls, execution: Execution) -> "TradeAggregate":
        """Create a new aggregate from its first execution."""
        direction = (
            TradeDirection.LONG
            if execution.side.value == "BUY"
            else TradeDirection.SHORT
        )
        trade_id = execution.trade_id or TradeId.generate()
        zero = Money(0, execution.fee.currency)
        aggregate = cls(
            trade_id=trade_id,
            account_id=execution.account_id,
            instrument_id=execution.instrument_id,
            direction=direction,
            status=TradeStatus.OPEN,
            open_quantity=execution.quantity,
            average_entry=execution.price,
            realized_quantity=Quantity(0),
            realized_gross_pnl=zero,
            total_fees=execution.fee,
            expenses=(),
            net_realized_pnl=zero - execution.fee,
            execution_count=0,
            applied_execution_ids=(),
            executions=(),
            opened_at=execution.executed_at,
            closed_at=None,
            _entry_notional=execution.price.value * execution.quantity.value,
        )
        aggregate._record_execution(execution)
        return aggregate

    def apply(self, execution: Execution) -> None:
        """Apply one non-duplicate execution to this aggregate."""
        if execution.account_id != self.account_id:
            raise ValueError("execution account does not match aggregate")
        if execution.instrument_id != self.instrument_id:
            raise ValueError("execution instrument does not match aggregate")
        if execution.trade_id is not None and execution.trade_id != self.trade_id:
            raise ValueError("execution is linked to a different trade")
        if execution.fee.currency != self.total_fees.currency:
            raise ValueError("execution fee currency must match aggregate currency")

        if self.status is TradeStatus.CLOSED:
            raise ValueError("cannot apply execution to a CLOSED aggregate")

        opening_side = execution.side.value == "BUY" if self.direction is TradeDirection.LONG else execution.side.value == "SELL"
        if opening_side:
            old_quantity = self.open_quantity.value
            new_quantity = old_quantity + execution.quantity.value
            self._entry_notional += execution.price.value * execution.quantity.value
            self.open_quantity = Quantity(new_quantity)
            self.average_entry = Price(self._entry_notional / new_quantity)
        else:
            if execution.quantity.value > self.open_quantity.value:
                raise ValueError("execution quantity exceeds open quantity")
            close_quantity = execution.quantity.value
            if self.direction is TradeDirection.LONG:
                gross_amount = (execution.price.value - self.average_entry.value) * close_quantity
            else:
                gross_amount = (self.average_entry.value - execution.price.value) * close_quantity
            self.realized_quantity = Quantity(self.realized_quantity.value + close_quantity)
            self.realized_gross_pnl = Money(
                self.realized_gross_pnl.amount + gross_amount,
                self.total_fees.currency,
            )
            remaining = self.open_quantity.value - close_quantity
            self.open_quantity = Quantity(remaining)
            self._entry_notional = self.average_entry.value * remaining
            if remaining == 0:
                self.status = TradeStatus.CLOSED
                self.closed_at = execution.executed_at

        self.total_fees = self.total_fees + execution.fee
        self._recalculate_net()
        self._record_execution(execution)

    def add_expense(self, expense: Expense) -> None:
        """Add a signed expense while preserving the Phase 1 convention."""
        if not isinstance(expense, Expense):
            raise TypeError("expense must be Expense")
        if expense.amount.currency != self.total_fees.currency:
            raise ValueError("expense currency must match aggregate currency")
        self.expenses = (*self.expenses, expense)
        self._recalculate_net()

    def _record_execution(self, execution: Execution) -> None:
        linked = execution if execution.trade_id == self.trade_id else execution.linked_to(self.trade_id)
        self.executions = (*self.executions, linked)
        self.applied_execution_ids = (*self.applied_execution_ids, linked.execution_id)
        self.execution_count += 1

    def _recalculate_net(self) -> None:
        total_expenses = Money(0, self.total_fees.currency)
        for expense in self.expenses:
            total_expenses += expense.amount
        self.net_realized_pnl = self.realized_gross_pnl - self.total_fees + total_expenses
