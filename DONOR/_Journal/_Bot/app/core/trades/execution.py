"""Execution domain entity."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone

from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId

from .execution_fact import ExecutionFact
from .execution_id import ExecutionId
from .execution_side import ExecutionSide
from .trade_id import TradeId


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


@dataclass(slots=True)
class Execution:
    """One factual fill, independent of any exchange SDK or Trade aggregate."""

    execution_id: ExecutionId
    account_id: AccountId
    instrument_id: InstrumentId
    side: ExecutionSide
    quantity: Quantity
    price: Price
    fee: Money
    executed_at: datetime
    exchange: str
    trade_id: TradeId | None = None
    external_execution_id: str | None = None
    external_order_id: str | None = None
    position_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.execution_id, ExecutionId):
            raise TypeError("execution_id must be ExecutionId")
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
        if self.trade_id is not None and not isinstance(self.trade_id, TradeId):
            raise TypeError("trade_id must be TradeId or None")

        object.__setattr__(self, "exchange", _normalize_exchange(self.exchange))
        object.__setattr__(self, "executed_at", _as_utc(self.executed_at, "executed_at"))
        _validate_external_id(self.external_execution_id, "external_execution_id")
        _validate_external_id(self.external_order_id, "external_order_id")
        _validate_external_id(self.position_id, "position_id")
        for field_name in ("external_execution_id", "external_order_id", "position_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, value.strip())

    @classmethod
    def from_fact(
        cls,
        fact: ExecutionFact,
        *,
        execution_id: ExecutionId | None = None,
        trade_id: TradeId | None = None,
    ) -> "Execution":
        """Create a journal execution from a transport-neutral factual input."""
        if not isinstance(fact, ExecutionFact):
            raise TypeError("fact must be ExecutionFact")
        if execution_id is None:
            execution_id = ExecutionId.generate()
        return cls(
            execution_id=execution_id,
            account_id=fact.account_id,
            instrument_id=fact.instrument_id,
            side=fact.side,
            quantity=fact.quantity,
            price=fact.price,
            fee=fact.fee,
            executed_at=fact.executed_at,
            exchange=fact.exchange,
            trade_id=trade_id,
            external_execution_id=fact.external_execution_id,
            external_order_id=fact.external_order_id,
            position_id=fact.position_id,
        )

    def linked_to(self, trade_id: TradeId) -> "Execution":
        """Return a controlled copy linked to a logical TradeId."""
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        return replace(self, trade_id=trade_id)
