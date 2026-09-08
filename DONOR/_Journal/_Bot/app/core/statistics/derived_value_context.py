"""Small immutable factual context for derived-value calculations."""

from dataclasses import dataclass
from datetime import datetime, time, tzinfo
from decimal import Decimal, InvalidOperation

from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk


def _as_aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    # Preserve the supplied timezone. DerivedValueService uses it when no
    # explicit business/display timezone is configured.
    return value


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, Price):
        return value.value
    if isinstance(value, Quantity):
        return value.value
    if isinstance(value, Risk):
        return value.amount.amount
    if isinstance(value, Money):
        return value.amount
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(f"{field_name} must not be bool or float")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as error:
            raise ValueError(f"invalid {field_name}: {value!r}") from error
    else:
        raise TypeError(f"{field_name} must be Decimal-compatible")
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result


def _time(value: time | str, field_name: str) -> time:
    if isinstance(value, time):
        if value.tzinfo is not None:
            raise ValueError(f"{field_name} must be a timezone-naive local time")
        return value
    if isinstance(value, str):
        try:
            parsed = time.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"invalid {field_name}: {value!r}") from error
        if parsed.tzinfo is not None:
            raise ValueError(f"{field_name} must be a timezone-naive local time")
        return parsed
    raise TypeError(f"{field_name} must be time or HH:MM string")


@dataclass(frozen=True, slots=True)
class TradingSessionRule:
    """One half-open local-time session interval: [start_time, end_time)."""

    code: str
    start_time: time | str
    end_time: time | str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("session code must not be empty")
        object.__setattr__(self, "code", self.code.strip().upper())
        object.__setattr__(self, "start_time", _time(self.start_time, "start_time"))
        object.__setattr__(self, "end_time", _time(self.end_time, "end_time"))
        if self.start_time == self.end_time:
            raise ValueError("session start_time and end_time must differ")

    @property
    def crosses_midnight(self) -> bool:
        return self.start_time > self.end_time

    def matches(self, local_time: time) -> bool:
        if self.crosses_midnight:
            return local_time >= self.start_time or local_time < self.end_time
        return self.start_time <= local_time < self.end_time


@dataclass(frozen=True, slots=True)
class DerivedValueContext:
    """Explicit facts used by DerivedValueService; no Telegram/ORM objects."""

    opened_at: datetime
    entry_price: Price | Decimal | int | str
    quantity: Quantity | Decimal | int | str
    closed_at: datetime | None = None
    exit_price: Price | Decimal | int | str | None = None
    stop_price: Price | Decimal | int | str | None = None
    risk: Risk | Money | Decimal | int | str | None = None
    gross_pnl: Money | Decimal | int | str | None = None
    net_pnl: Money | Decimal | int | str | None = None
    currency: str | None = None
    timezone: tzinfo | None = None
    session_rules: tuple[TradingSessionRule, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "opened_at", _as_aware(self.opened_at, "opened_at"))
        if self.closed_at is not None:
            closed_at = _as_aware(self.closed_at, "closed_at")
            if closed_at < self.opened_at:
                raise ValueError("closed_at must be greater than or equal to opened_at")
            object.__setattr__(self, "closed_at", closed_at)
        _decimal(self.entry_price, "entry_price")
        _decimal(self.quantity, "quantity")
        for name in ("stop_price", "risk", "gross_pnl", "net_pnl"):
            value = getattr(self, name)
            if value is not None:
                _decimal(value, name)
        if self.currency is not None:
            if not isinstance(self.currency, str) or not self.currency.strip():
                raise ValueError("currency must be a non-empty string when provided")
            object.__setattr__(self, "currency", self.currency.strip().upper())
        if self.timezone is not None and not isinstance(self.timezone, tzinfo):
            raise TypeError("timezone must be a tzinfo or None")
        rules = tuple(self.session_rules)
        if any(not isinstance(rule, TradingSessionRule) for rule in rules):
            raise TypeError("session_rules must contain only TradingSessionRule values")
        object.__setattr__(self, "session_rules", rules)

    @property
    def entry_price_decimal(self) -> Decimal:
        return _decimal(self.entry_price, "entry_price")

    @property
    def quantity_decimal(self) -> Decimal:
        return _decimal(self.quantity, "quantity")

    def decimal(self, name: str) -> Decimal | None:
        value = getattr(self, name)
        return None if value is None else _decimal(value, name)
