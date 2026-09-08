"""Small UI-neutral commands and results for manual journal workflows."""

from __future__ import annotations

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
from app.core.instruments.instrument import Instrument
from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.custom_field_option import CustomFieldOption
from app.core.statistics.derived_value_context import DerivedValueContext
from app.core.statistics.ids import CustomFieldDefinitionId, CustomFieldOptionId
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.enums import TradeDirection, TradeStatus
from app.core.trades.trade import Trade
from app.core.trades.readiness import TradeReadiness
from app.core.trades.trade_id import TradeId
from app.core.imports import JournalTradeState
from app.core.automatic_data import AutomaticFactorObservation

from .statistics.trade_enrichment_result import TradeEnrichmentResult


@dataclass(frozen=True, slots=True)
class InstrumentView:
    instrument_id: InstrumentId
    symbol: str
    name: str
    exchange: str | None
    market: str | None
    active: bool

    @classmethod
    def from_instrument(cls, instrument: Instrument) -> "InstrumentView":
        if not isinstance(instrument, Instrument):
            raise TypeError("instrument must be Instrument")
        return cls(instrument.instrument_id, instrument.symbol, instrument.name, instrument.exchange, instrument.market, instrument.active)

    @property
    def label(self) -> str:
        context = " / ".join(item for item in (self.exchange, self.market) if item)
        return f"{self.symbol} — {self.name}" + (f" ({context})" if context else "")


def _id(value, value_type, field_name):
    if isinstance(value, value_type):
        return value
    try:
        return value_type(value)
    except (TypeError, ValueError) as error:
        raise type(error)(f"{field_name} is invalid: {value!r}") from error


def _direction(value: TradeDirection | str) -> TradeDirection:
    if isinstance(value, TradeDirection):
        return value
    if isinstance(value, str):
        return TradeDirection(value)
    raise TypeError("direction must be TradeDirection or str")


@dataclass(frozen=True, slots=True)
class TradeView:
    """Read-only application projection of the current Trade aggregate."""

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
    risk: Risk | None
    fees: Money
    expenses: tuple[Expense, ...]
    gross_pnl: Money | None
    net_pnl: Money | None
    take_profit: Price | None = None

    @classmethod
    def from_trade(cls, trade: Trade) -> "TradeView":
        if not isinstance(trade, Trade):
            raise TypeError("trade must be Trade")
        return cls(
            trade_id=trade.trade_id,
            account_id=trade.account_id,
            instrument_id=trade.instrument_id,
            direction=trade.direction,
            status=trade.status,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            stop_price=trade.stop_price,
            risk=trade.risk,
            fees=trade.fees,
            expenses=trade.expenses,
            gross_pnl=trade.gross_pnl,
            net_pnl=trade.net_pnl,
            take_profit=trade.take_profit,
        )


@dataclass(frozen=True, slots=True)
class TradeResult:
    """Result returned by a command that changes or loads a Trade."""

    trade: TradeView

    @property
    def trade_id(self) -> TradeId:
        return self.trade.trade_id

    @property
    def status(self) -> TradeStatus:
        return self.trade.status

    @classmethod
    def from_trade(cls, trade: Trade) -> "TradeResult":
        return cls(TradeView.from_trade(trade))


@dataclass(frozen=True, slots=True)
class CreateManualTradeCommand:
    account_id: AccountId
    instrument_id: InstrumentId
    direction: TradeDirection | str
    entry_price: Price | Decimal | int | str
    quantity: Quantity | Decimal | int | str
    opened_at: datetime
    currency: str
    trade_id: TradeId | None = None
    stop_price: Price | None = None
    take_profit: Price | None = None
    risk: Risk | None = None
    fees: Money | None = None
    expenses: tuple[Expense, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_id", _id(self.account_id, AccountId, "account_id"))
        object.__setattr__(self, "instrument_id", _id(self.instrument_id, InstrumentId, "instrument_id"))
        object.__setattr__(self, "direction", _direction(self.direction))
        if not isinstance(self.entry_price, Price):
            object.__setattr__(self, "entry_price", Price(self.entry_price))
        if not isinstance(self.quantity, Quantity):
            object.__setattr__(self, "quantity", Quantity(self.quantity))
        if self.stop_price is not None and not isinstance(self.stop_price, Price):
            object.__setattr__(self, "stop_price", Price(self.stop_price))
        if self.take_profit is not None and not isinstance(self.take_profit, Price):
            object.__setattr__(self, "take_profit", Price(self.take_profit))
        if self.trade_id is not None:
            object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))
        object.__setattr__(self, "expenses", tuple(self.expenses))


@dataclass(frozen=True, slots=True)
class CloseManualTradeCommand:
    trade_id: TradeId
    exit_price: Price | Decimal | int | str
    closed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))


@dataclass(frozen=True, slots=True)
class UpdateTradeProtectionCommand:
    trade_id: TradeId
    stop_price: Price | Decimal | int | str | None = None
    take_profit: Price | Decimal | int | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))
        if self.stop_price is not None and not isinstance(self.stop_price, Price):
            object.__setattr__(self, "stop_price", Price(self.stop_price))
        if self.take_profit is not None and not isinstance(self.take_profit, Price):
            object.__setattr__(self, "take_profit", Price(self.take_profit))


@dataclass(frozen=True, slots=True)
class AddFeeCommand:
    trade_id: TradeId
    fee: Money

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))


@dataclass(frozen=True, slots=True)
class AddExpenseCommand:
    trade_id: TradeId
    expense: Expense | Money

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))
        if isinstance(self.expense, Money):
            object.__setattr__(self, "expense", Expense(self.expense))


@dataclass(frozen=True, slots=True)
class AddManualCustomValueCommand:
    trade_id: TradeId
    field_id: CustomFieldDefinitionId
    value: str | Decimal | bool | CustomFieldOptionId | CustomFieldOption
    resolution_context: CustomFieldResolutionContext | None = None
    recorded_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))
        object.__setattr__(self, "field_id", _id(self.field_id, CustomFieldDefinitionId, "field_id"))


@dataclass(frozen=True, slots=True)
class EnrichTradeCommand:
    trade_id: TradeId
    resolution_context: CustomFieldResolutionContext | None = None
    derived_context: DerivedValueContext | None = None
    recorded_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))


@dataclass(frozen=True, slots=True)
class EnrichTradeWithMarketDataCommand:
    trade_id: TradeId
    resolution_context: CustomFieldResolutionContext | None = None
    derived_context: DerivedValueContext | None = None
    recorded_at: datetime | None = None
    at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))


@dataclass(frozen=True, slots=True)
class ListOpenTradesCommand:
    account_id: AccountId | None = None
    instrument_id: InstrumentId | None = None

    def __post_init__(self) -> None:
        if self.account_id is not None:
            object.__setattr__(self, "account_id", _id(self.account_id, AccountId, "account_id"))
        if self.instrument_id is not None:
            object.__setattr__(self, "instrument_id", _id(self.instrument_id, InstrumentId, "instrument_id"))


@dataclass(frozen=True, slots=True)
class ListAllTradesCommand:
    account_id: AccountId | None = None
    instrument_id: InstrumentId | None = None
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if self.account_id is not None:
            object.__setattr__(self, "account_id", _id(self.account_id, AccountId, "account_id"))
        if self.instrument_id is not None:
            object.__setattr__(self, "instrument_id", _id(self.instrument_id, InstrumentId, "instrument_id"))
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        if type(self.offset) is not int or self.offset < 0:
            raise ValueError("offset must be an integer >= 0")


@dataclass(frozen=True, slots=True)
class GetTradeDetailsCommand:
    trade_id: TradeId

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_id", _id(self.trade_id, TradeId, "trade_id"))


@dataclass(frozen=True, slots=True)
class ListOpenTradesResult:
    trades: tuple[TradeView, ...]


@dataclass(frozen=True, slots=True)
class ListAllTradesResult:
    trades: tuple[TradeView, ...]


@dataclass(frozen=True, slots=True)
class AddManualCustomValueResult:
    value: TradeCustomValue

    @property
    def trade_id(self) -> TradeId:
        return self.value.trade_id


@dataclass(frozen=True, slots=True)
class EnrichTradeResult:
    trade: TradeView
    enrichment: TradeEnrichmentResult
    persisted_values: tuple[TradeCustomValue, ...]

    @property
    def resolved_fields(self):
        return self.enrichment.resolved_fields

    @property
    def existing_values(self):
        return self.enrichment.existing_values

    @property
    def generated_values(self):
        return self.enrichment.generated_values

    @property
    def missing_manual_required(self):
        return self.enrichment.missing_manual_required

    @property
    def missing_manual_optional(self):
        return self.enrichment.missing_manual_optional

    @property
    def unavailable_auto_fields(self):
        return self.enrichment.unavailable_auto_fields

    @property
    def unsupported_auto_fields(self):
        return self.enrichment.unsupported_auto_fields

    @property
    def status(self):
        return self.enrichment.status


@dataclass(frozen=True, slots=True)
class CustomValueView:
    value: TradeCustomValue
    definition: CustomFieldDefinition | None
    option: CustomFieldOption | None = None


@dataclass(frozen=True, slots=True)
class GetTradeDetailsResult:
    trade: TradeView
    custom_values: tuple[CustomValueView, ...]
    instrument: InstrumentView | None = None
    readiness: TradeReadiness | None = None
    field_definitions: tuple[CustomFieldDefinition, ...] = ()
    has_exchange_executions: bool = False
    journal_state: JournalTradeState | None = None
    automatic_observations: tuple[AutomaticFactorObservation, ...] = ()

    @property
    def fees(self) -> Money:
        return self.trade.fees

    @property
    def expenses(self) -> tuple[Expense, ...]:
        return self.trade.expenses

    @property
    def gross_pnl(self) -> Money | None:
        return self.trade.gross_pnl

    @property
    def net_pnl(self) -> Money | None:
        return self.trade.net_pnl


@dataclass(frozen=True, slots=True)
class MiniAppTradeRow:
    trade: TradeView
    instrument: InstrumentView | None


@dataclass(frozen=True, slots=True)
class MiniAppTradePage:
    items: tuple[MiniAppTradeRow, ...]
    limit: int
    offset: int
    has_more: bool
