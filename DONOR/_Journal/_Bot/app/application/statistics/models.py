"""Immutable input, filter, and result models for Statistics Engine V1."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.risk import Risk
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.custom_field_option import CustomFieldOption
from app.core.statistics.custom_field_scope import CustomFieldScope
from app.core.statistics.ids import CustomFieldDefinitionId
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


def _id(value, value_type, field_name):
    if isinstance(value, value_type):
        return value
    try:
        return value_type(value)
    except (TypeError, ValueError) as error:
        raise type(error)(f"{field_name} is invalid: {value!r}") from error


def _aware_utc(value: datetime | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _direction(value: TradeDirection | str | None) -> TradeDirection | None:
    if value is None or isinstance(value, TradeDirection):
        return value
    if isinstance(value, str):
        return TradeDirection(value)
    raise TypeError("direction must be TradeDirection, str, or None")


def _status(value: TradeStatus | str | None) -> TradeStatus | None:
    if value is None or isinstance(value, TradeStatus):
        return value
    if isinstance(value, str):
        return TradeStatus(value)
    raise TypeError("status must be TradeStatus, str, or None")


@dataclass(frozen=True, slots=True)
class StatisticsFilter:
    """Bounded, explicit filter; CLOSED is the safe performance default."""

    account_id: AccountId | None = None
    instrument_id: InstrumentId | None = None
    from_at: datetime | None = None
    to_at: datetime | None = None
    direction: TradeDirection | str | None = None
    status: TradeStatus | str | None = TradeStatus.CLOSED

    def __post_init__(self) -> None:
        if self.account_id is not None:
            object.__setattr__(self, "account_id", _id(self.account_id, AccountId, "account_id"))
        if self.instrument_id is not None:
            object.__setattr__(self, "instrument_id", _id(self.instrument_id, InstrumentId, "instrument_id"))
        object.__setattr__(self, "from_at", _aware_utc(self.from_at, "from_at"))
        object.__setattr__(self, "to_at", _aware_utc(self.to_at, "to_at"))
        object.__setattr__(self, "direction", _direction(self.direction))
        object.__setattr__(self, "status", _status(self.status))
        if self.from_at is not None and self.to_at is not None and self.from_at > self.to_at:
            raise ValueError("from_at must be less than or equal to to_at")


@dataclass(frozen=True, slots=True)
class StatisticsTradeRecord:
    """Only historical facts required by the read-only engine."""

    trade_id: TradeId
    account_id: AccountId
    instrument_id: InstrumentId | None
    direction: TradeDirection
    opened_at: datetime
    closed_at: datetime | None
    status: TradeStatus
    gross_pnl: Money | None
    net_pnl: Money | None
    fees: Money
    expenses: tuple[Expense, ...] = ()
    risk: Risk | None = None
    account_label: str | None = None
    instrument_label: str | None = None
    resolution_context: CustomFieldResolutionContext | None = None
    entry_price: Price | None = None
    exit_price: Price | None = None
    quantity: Quantity | None = None
    stop_price: Price | None = None
    instrument_available: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))
        object.__setattr__(self, "account_id", _id(self.account_id, AccountId, "account_id"))
        if self.instrument_id is not None:
            object.__setattr__(self, "instrument_id", _id(self.instrument_id, InstrumentId, "instrument_id"))
        if not isinstance(self.direction, TradeDirection):
            object.__setattr__(self, "direction", TradeDirection(self.direction))
        if not isinstance(self.status, TradeStatus):
            object.__setattr__(self, "status", TradeStatus(self.status))
        object.__setattr__(self, "opened_at", _aware_utc(self.opened_at, "opened_at"))
        object.__setattr__(self, "closed_at", _aware_utc(self.closed_at, "closed_at"))
        if self.closed_at is not None and self.closed_at < self.opened_at:
            raise ValueError("closed_at must be greater than or equal to opened_at")
        if not isinstance(self.fees, Money):
            raise TypeError("fees must be Money")
        if type(self.instrument_available) is not bool:
            raise TypeError("instrument_available must be bool")
        for value in (self.gross_pnl, self.net_pnl):
            if value is not None and not isinstance(value, Money):
                raise TypeError("gross_pnl and net_pnl must be Money or None")
        expenses = tuple(self.expenses)
        if any(not isinstance(item, Expense) for item in expenses):
            raise TypeError("expenses must contain Expense values")
        if any(item.amount.currency != self.fees.currency for item in expenses):
            raise ValueError("expense currency must match fees currency")
        object.__setattr__(self, "expenses", expenses)
        for value, name in ((self.entry_price, "entry_price"), (self.exit_price, "exit_price")):
            if value is not None and not isinstance(value, Price):
                raise TypeError(f"{name} must be Price or None")
        if self.quantity is not None and not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be Quantity or None")
        if self.stop_price is not None and not isinstance(self.stop_price, Price):
            raise TypeError("stop_price must be Price or None")

    @classmethod
    def from_trade(cls, trade: Trade) -> "StatisticsTradeRecord":
        if not isinstance(trade, Trade):
            raise TypeError("trade must be Trade")
        return cls(
            trade_id=trade.trade_id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            direction=trade.direction,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            status=trade.status,
            gross_pnl=trade.gross_pnl,
            net_pnl=trade.net_pnl,
            fees=trade.fees,
            expenses=trade.expenses,
            risk=trade.risk,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            stop_price=trade.stop_price,
        )

    @property
    def filter_time(self) -> datetime:
        return self.closed_at or self.opened_at


@dataclass(frozen=True, slots=True)
class DynamicFieldMetadata:
    definition: CustomFieldDefinition
    scopes: tuple[CustomFieldScope, ...] = ()
    options: tuple[CustomFieldOption, ...] = ()


class StatisticsGroupBy(StrEnum):
    ACCOUNT = "ACCOUNT"
    INSTRUMENT = "INSTRUMENT"
    DIRECTION = "DIRECTION"
    DYNAMIC_FIELD = "DYNAMIC_FIELD"


@dataclass(frozen=True, slots=True)
class GroupedPerformanceRequest:
    group_by: StatisticsGroupBy | str
    filters: StatisticsFilter = field(default_factory=StatisticsFilter)
    field_id: CustomFieldDefinitionId | str | None = None
    field_code: str | None = None
    min_sample_size: int = 0
    include_missing: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.group_by, StatisticsGroupBy):
            object.__setattr__(self, "group_by", StatisticsGroupBy(self.group_by))
        if not isinstance(self.filters, StatisticsFilter):
            raise TypeError("filters must be StatisticsFilter")
        if type(self.min_sample_size) is not int or self.min_sample_size < 0:
            raise ValueError("min_sample_size must be an integer >= 0")
        if self.field_code is not None and (not isinstance(self.field_code, str) or not self.field_code.strip()):
            raise ValueError("field_code must be a non-empty string when provided")
        if self.group_by is StatisticsGroupBy.DYNAMIC_FIELD and self.field_id is None and self.field_code is None:
            raise ValueError("dynamic grouping requires field_id or field_code")


@dataclass(frozen=True, slots=True)
class DynamicFieldCoverageRequest:
    filters: StatisticsFilter = field(default_factory=StatisticsFilter)
    field_id: CustomFieldDefinitionId | str | None = None
    field_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.filters, StatisticsFilter):
            raise TypeError("filters must be StatisticsFilter")
        if self.field_id is None and self.field_code is None:
            raise ValueError("coverage requires field_id or field_code")


@dataclass(frozen=True, slots=True)
class PerformanceSummary:
    sample_size: int
    trade_count: int
    win_count: int
    loss_count: int
    breakeven_count: int
    win_rate: Decimal | None
    gross_pnl: Decimal
    net_pnl: Decimal
    total_fees: Decimal
    total_expenses: Decimal
    average_net_pnl: Decimal | None
    average_win: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    expectancy: Decimal | None
    largest_win: Decimal | None
    largest_loss: Decimal | None
    median_net_pnl: Decimal | None
    currency: str | None
    ready_count: int = 0
    excluded_incomplete_count: int = 0
    open_count: int = 0

    @property
    def eligible_trade_count(self) -> int:
        return self.ready_count


@dataclass(frozen=True, slots=True)
class StatisticsGroup:
    key: str
    label: str
    summary: PerformanceSummary


@dataclass(frozen=True, slots=True)
class GroupedPerformanceResult:
    group_by: StatisticsGroupBy
    groups: tuple[StatisticsGroup, ...]
    eligible_trade_count: int
    known_value_count: int
    missing_value_count: int
    coverage_rate: Decimal | None
    ready_count: int = 0
    excluded_incomplete_count: int = 0
    open_count: int = 0


@dataclass(frozen=True, slots=True)
class DynamicFieldCoverage:
    field_id: CustomFieldDefinitionId
    field_code: str
    eligible_trade_count: int
    filled_count: int
    missing_count: int
    coverage_rate: Decimal | None


@dataclass(frozen=True, slots=True)
class MetricCoverage:
    metric: str
    eligible_trade_count: int
    calculated_count: int
    missing_count: int
    coverage_rate: Decimal | None


@dataclass(frozen=True, slots=True)
class CumulativePnLPoint:
    """One point of the eligible realized equity curve."""

    trade_id: TradeId
    at: datetime
    pnl: Decimal
    cumulative_pnl: Decimal
    currency: str
