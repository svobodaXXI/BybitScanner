"""Trade Core V1 entity."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId

from .enums import TradeDirection, TradePnLSource, TradeStatus
from .trade_id import TradeId


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class Trade:
    """A manual single-entry/full-close trade."""

    trade_id: TradeId
    account_id: AccountId
    instrument_id: InstrumentId
    direction: TradeDirection
    status: TradeStatus
    opened_at: datetime
    closed_at: datetime | None
    entry_price: Price
    exit_price: Price | None
    quantity: Quantity
    stop_price: Price | None
    take_profit: Price | None = field(default=None, kw_only=True)
    risk: Risk | None
    fees: Money
    expenses: tuple[Expense, ...] = ()
    gross_pnl: Money | None = None
    net_pnl: Money | None = None
    pnl_source: TradePnLSource = TradePnLSource.SNAPSHOT

    def __post_init__(self) -> None:
        if not isinstance(self.trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        if not isinstance(self.account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        if not isinstance(self.instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId")
        if not isinstance(self.direction, TradeDirection):
            raise TypeError("direction must be TradeDirection")
        if self.status not in (TradeStatus.OPEN, TradeStatus.CLOSED):
            raise ValueError("Phase 1 Trade supports only OPEN and CLOSED statuses")
        if not isinstance(self.entry_price, Price):
            raise TypeError("entry_price must be Price")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be Quantity")
        if self.quantity.value <= 0:
            raise ValueError("trade quantity must be greater than zero")
        if self.stop_price is not None and not isinstance(self.stop_price, Price):
            raise TypeError("stop_price must be Price or None")
        if self.take_profit is not None and not isinstance(self.take_profit, Price):
            raise TypeError("take_profit must be Price or None")
        if self.risk is not None and not isinstance(self.risk, Risk):
            raise TypeError("risk must be Risk or None")
        if not isinstance(self.fees, Money):
            raise TypeError("fees must be Money")
        if self.fees.amount < 0:
            raise ValueError("fees must not be negative")
        if not isinstance(self.pnl_source, TradePnLSource):
            try:
                object.__setattr__(self, "pnl_source", TradePnLSource(self.pnl_source))
            except (TypeError, ValueError) as error:
                raise ValueError("pnl_source must be SNAPSHOT or EXECUTION_REPLAY") from error

        opened_at = _as_utc(self.opened_at, "opened_at")
        closed_at = None if self.closed_at is None else _as_utc(self.closed_at, "closed_at")
        if closed_at is not None and closed_at < opened_at:
            raise ValueError("closed_at must be greater than or equal to opened_at")
        object.__setattr__(self, "opened_at", opened_at)
        object.__setattr__(self, "closed_at", closed_at)

        expenses = tuple(self.expenses)
        if any(not isinstance(expense, Expense) for expense in expenses):
            raise TypeError("expenses must contain only Expense values")
        object.__setattr__(self, "expenses", expenses)

        currency = self.fees.currency
        if self.risk is not None and self.risk.amount.currency != currency:
            raise ValueError("risk currency must match trade currency")
        for expense in expenses:
            if expense.amount.currency != currency:
                raise ValueError("expense currency must match trade currency")

        if self.status is TradeStatus.OPEN:
            if any(
                value is not None
                for value in (self.closed_at, self.exit_price, self.gross_pnl, self.net_pnl)
            ):
                raise ValueError("an OPEN trade cannot contain close data")
            return

        if self.closed_at is None:
            raise ValueError("a CLOSED trade requires closed_at")
        # Historical rows may be CLOSED while one or more close facts are
        # missing. They remain visible and are classified by readiness; a
        # normal close command still supplies all facts below.
        if self.exit_price is not None and not isinstance(self.exit_price, Price):
            raise TypeError("exit_price must be Price or None")
        for pnl, name in ((self.gross_pnl, "gross_pnl"), (self.net_pnl, "net_pnl")):
            if pnl is not None and not isinstance(pnl, Money):
                raise TypeError(f"{name} must be Money or None")
            if pnl is not None and pnl.currency != currency:
                raise ValueError("PnL currency must match trade currency")

        if self.exit_price is not None and self.gross_pnl is not None and self.net_pnl is not None:
            self._validate_pnl_finiteness_and_net()
            if self.pnl_source is TradePnLSource.SNAPSHOT:
                expected_gross, expected_net = self._calculate_pnl(self.exit_price)
                if self.gross_pnl != expected_gross or self.net_pnl != expected_net:
                    raise ValueError("closed trade PnL does not match trade facts")
        elif self.gross_pnl is not None or self.net_pnl is not None:
            self._validate_pnl_finiteness_and_net()

    @classmethod
    def open(
        cls,
        account_id: AccountId,
        instrument_id: InstrumentId,
        direction: TradeDirection,
        entry_price: Price,
        quantity: Quantity,
        opened_at: datetime,
        currency: str,
        *,
        trade_id: TradeId | None = None,
        stop_price: Price | None = None,
        take_profit: Price | None = None,
        risk: Risk | None = None,
        fees: Money | None = None,
        expenses: Iterable[Expense] = (),
        pnl_source: TradePnLSource = TradePnLSource.SNAPSHOT,
    ) -> "Trade":
        """Create an OPEN trade with no close data or realized PnL."""
        if trade_id is None:
            trade_id = TradeId.generate()
        if fees is None:
            fees = Money(0, currency)
        return cls(
            trade_id=trade_id,
            account_id=account_id,
            instrument_id=instrument_id,
            direction=direction,
            status=TradeStatus.OPEN,
            opened_at=opened_at,
            closed_at=None,
            entry_price=entry_price,
            exit_price=None,
            quantity=quantity,
            stop_price=stop_price,
            take_profit=take_profit,
            risk=risk,
            fees=fees,
            expenses=tuple(expenses),
            gross_pnl=None,
            net_pnl=None,
            pnl_source=pnl_source,
        )

    def set_stop_price(self, stop_price: Price | None) -> "Trade":
        if stop_price is not None and not isinstance(stop_price, Price):
            raise TypeError("stop_price must be Price or None")
        self.stop_price = stop_price
        return self

    def set_take_profit(self, take_profit: Price | None) -> "Trade":
        if take_profit is not None and not isinstance(take_profit, Price):
            raise TypeError("take_profit must be Price or None")
        self.take_profit = take_profit
        return self

    def add_fee(self, fee: Money) -> "Trade":
        """Add a non-negative fee before the trade is closed."""
        self._ensure_open_for_update()
        if not isinstance(fee, Money):
            raise TypeError("fee must be Money")
        if fee.amount < 0:
            raise ValueError("fees must not be negative")
        if fee.currency != self.fees.currency:
            raise ValueError("fee currency must match trade currency")
        self.fees = self.fees + fee
        return self

    def add_expense(self, expense: Expense) -> "Trade":
        """Add a signed expense adjustment before the trade is closed."""
        self._ensure_open_for_update()
        if not isinstance(expense, Expense):
            raise TypeError("expense must be Expense")
        if expense.amount.currency != self.fees.currency:
            raise ValueError("expense currency must match trade currency")
        self.expenses = (*self.expenses, expense)
        return self

    def close(self, exit_price: Price, closed_at: datetime) -> "Trade":
        """Close the trade once and calculate gross and net PnL."""
        self._ensure_open_for_update()
        if not isinstance(exit_price, Price):
            raise TypeError("exit_price must be Price")
        closed_at = _as_utc(closed_at, "closed_at")
        if closed_at < self.opened_at:
            raise ValueError("closed_at must be greater than or equal to opened_at")

        gross_pnl, net_pnl = self._calculate_pnl(exit_price)
        self.exit_price = exit_price
        self.closed_at = closed_at
        self.gross_pnl = gross_pnl
        self.net_pnl = net_pnl
        self.status = TradeStatus.CLOSED
        return self

    def close_from_aggregation(
        self,
        exit_price: Price,
        closed_at: datetime,
        gross_pnl: Money,
    ) -> "Trade":
        """Close using gross PnL already calculated by TradeAggregationService."""
        self._ensure_open_for_update()
        if not isinstance(exit_price, Price):
            raise TypeError("exit_price must be Price")
        if not isinstance(gross_pnl, Money) or gross_pnl.currency != self.fees.currency:
            raise ValueError("aggregated gross PnL currency must match trade currency")
        closed_at = _as_utc(closed_at, "closed_at")
        if closed_at < self.opened_at:
            raise ValueError("closed_at must be greater than or equal to opened_at")
        self.exit_price = exit_price
        self.closed_at = closed_at
        self.gross_pnl = gross_pnl
        total_expenses = Money(0, self.fees.currency)
        for expense in self.expenses:
            total_expenses += expense.amount
        self.net_pnl = gross_pnl - self.fees + total_expenses
        self.status = TradeStatus.CLOSED
        return self

    def _ensure_open_for_update(self) -> None:
        if self.status is not TradeStatus.OPEN:
            raise ValueError("trade must be OPEN for this operation")

    def _validate_pnl_finiteness_and_net(self) -> None:
        """Validate the invariant common to snapshot and replay-backed PnL."""
        if self.gross_pnl is None or self.net_pnl is None:
            raise ValueError("gross_pnl and net_pnl must be provided together")
        if self.gross_pnl.currency != self.fees.currency or self.net_pnl.currency != self.fees.currency:
            raise ValueError("PnL currency must match trade currency")
        if not self.gross_pnl.amount.is_finite() or not self.net_pnl.amount.is_finite():
            raise ValueError("PnL values must be finite")
        total_expenses = Money(0, self.fees.currency)
        for expense in self.expenses:
            total_expenses += expense.amount
        if self.net_pnl != self.gross_pnl - self.fees + total_expenses:
            raise ValueError("persisted net PnL does not match gross, fees, and expenses")

    def _calculate_pnl(self, exit_price: Price) -> tuple[Money, Money]:
        if self.direction is TradeDirection.LONG:
            gross_amount = (exit_price - self.entry_price) * self.quantity.value
        elif self.direction is TradeDirection.SHORT:
            gross_amount = (self.entry_price - exit_price) * self.quantity.value
        else:
            raise ValueError("Phase 1 PnL supports LONG and SHORT only")

        gross_pnl = Money(gross_amount, self.fees.currency)
        total_expenses = Money(0, self.fees.currency)
        for expense in self.expenses:
            total_expenses += expense.amount
        net_pnl = gross_pnl - self.fees + total_expenses
        return gross_pnl, net_pnl
