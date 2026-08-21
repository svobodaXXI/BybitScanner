"""Deterministic value objects for the Manual Trading Terminal domain."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


def _non_empty(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _decimal(value: Decimal, field_name: str, *, positive: bool) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    if positive and value <= 0:
        raise ValueError(f"{field_name} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _finite_decimal(value: Decimal, field_name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return value


@dataclass(frozen=True, slots=True, order=True)
class TradingAccountId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "account id"))


@dataclass(frozen=True, slots=True, order=True)
class CommandId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "command id"))


@dataclass(frozen=True, slots=True, order=True)
class OrderId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "order id"))


@dataclass(frozen=True, slots=True, order=True)
class ExecutionId:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _non_empty(self.value, "execution id"))


@dataclass(frozen=True, slots=True, order=True)
class Symbol:
    value: str

    def __post_init__(self) -> None:
        value = _non_empty(self.value, "symbol").upper()
        object.__setattr__(self, "value", value)


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal

    def __post_init__(self) -> None:
        _decimal(self.value, "price", positive=True)


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        _decimal(self.value, "quantity", positive=False)


@dataclass(frozen=True, slots=True)
class Notional:
    value: Decimal

    def __post_init__(self) -> None:
        _decimal(self.value, "notional", positive=False)


class Category(str, Enum):
    LINEAR = "linear"


class OrderSide(str, Enum):
    BUY = "Buy"
    SELL = "Sell"


class PositionSide(str, Enum):
    FLAT = "Flat"
    LONG = "Long"
    SHORT = "Short"


class Origin(str, Enum):
    TERMINAL_MANUAL = "terminal_manual"
    EXTERNAL = "external"
    ROBOT = "robot"


class Controller(str, Enum):
    MANUAL = "manual"
    EXTERNAL = "external"
    NONE = "none"
    ROBOT = "robot"


@dataclass(frozen=True, slots=True)
class PositionKey:
    trading_account_id: TradingAccountId
    category: Category
    symbol: Symbol
    position_idx: int

    def __post_init__(self) -> None:
        if self.category is not Category.LINEAR:
            raise ValueError("Manual v1 supports the linear category only")
        if self.position_idx != 0:
            raise ValueError("Manual v1 requires One-Way position_idx=0")


@dataclass(frozen=True, slots=True)
class ExecutionDedupKey:
    trading_account_id: TradingAccountId
    category: Category
    exec_id: ExecutionId


@dataclass(frozen=True, slots=True)
class TradingCommand:
    command_id: CommandId
    trading_account_id: TradingAccountId
    symbol: Symbol
    side: OrderSide
    origin: Origin
    controller: Controller


@dataclass(frozen=True, slots=True)
class ExchangeOrder:
    order_id: OrderId
    command_id: CommandId | None
    position_key: PositionKey
    side: OrderSide
    quantity: Quantity
    remaining_quantity: Quantity
    origin: Origin
    controller: Controller

    def __post_init__(self) -> None:
        if self.remaining_quantity.value > self.quantity.value:
            raise ValueError("remaining quantity cannot exceed order quantity")


@dataclass(frozen=True, slots=True)
class Execution:
    """Immutable economic fill evidence."""

    dedup_key: ExecutionDedupKey
    order_id: OrderId
    symbol: Symbol
    side: OrderSide
    price: Price
    quantity: Quantity
    fee: Decimal
    exchange_timestamp_ms: int

    def __post_init__(self) -> None:
        _finite_decimal(self.fee, "fee")
        if self.quantity.value <= 0:
            raise ValueError("execution quantity must be positive")
        if self.exchange_timestamp_ms < 0:
            raise ValueError("exchange timestamp must not be negative")
