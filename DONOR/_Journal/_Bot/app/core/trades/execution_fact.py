"""Transport-neutral factual input for an execution fill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId

from .execution_side import ExecutionSide


def _as_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _normalize_exchange(exchange: str) -> str:
    if not isinstance(exchange, str):
        raise TypeError("exchange must be a string")
    normalized = exchange.strip().upper()
    if not normalized:
        raise ValueError("exchange must not be empty")
    return normalized


def _validate_external_id(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True, slots=True)
class ExecutionFact:
    """A factual observation entering the application/domain boundary."""

    exchange: str
    account_id: AccountId
    instrument_id: InstrumentId
    side: ExecutionSide
    quantity: Quantity
    price: Price
    fee: Money
    executed_at: datetime
    external_execution_id: str | None = None
    external_order_id: str | None = None
    position_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        if not isinstance(self.instrument_id, InstrumentId):
            raise TypeError("instrument_id must be InstrumentId")
        if not isinstance(self.side, ExecutionSide):
            raise TypeError("side must be ExecutionSide")
        if not isinstance(self.quantity, Quantity):
            raise TypeError("quantity must be Quantity")
        if self.quantity.value <= 0:
            raise ValueError("execution quantity must be greater than zero")
        if not isinstance(self.price, Price):
            raise TypeError("price must be Price")
        if not isinstance(self.fee, Money):
            raise TypeError("fee must be Money")
        if self.fee.amount < 0:
            raise ValueError("execution fee must not be negative")

        object.__setattr__(self, "exchange", _normalize_exchange(self.exchange))
        object.__setattr__(self, "executed_at", _as_utc(self.executed_at, "executed_at"))
        _validate_external_id(self.external_execution_id, "external_execution_id")
        _validate_external_id(self.external_order_id, "external_order_id")
        _validate_external_id(self.position_id, "position_id")
        for field_name in ("external_execution_id", "external_order_id", "position_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, value.strip())
