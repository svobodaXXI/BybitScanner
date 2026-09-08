"""Exchange-neutral market-data contracts used by application enrichment."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from enum import StrEnum

from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics.codes import CustomFieldCode
from app.core.statistics.ids import CustomFieldOptionId


MarketDataValue = str | Decimal | bool | CustomFieldOptionId


class MarketDataFetchStatus(StrEnum):
    """Outcome of the optional provider lookup for one enrichment operation."""

    NOT_REQUIRED = "NOT_REQUIRED"
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


def _as_utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("as_of must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    return value.astimezone(timezone.utc)


def normalize_market_data_timestamp(value: datetime) -> datetime:
    """Normalize a provider query timestamp and reject naive datetimes."""

    return _as_utc(value)


def _validate_value(value: object) -> None:
    if type(value) is str or type(value) is bool or isinstance(value, CustomFieldOptionId):
        return
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("market-data Decimal values must be finite")
        return
    raise TypeError("market-data values must be str, Decimal, bool, or CustomFieldOptionId")


@dataclass(frozen=True, slots=True)
class MarketDataContext:
    """Immutable, normalized snapshot returned by a MarketDataProvider.

    Keys are Dynamic Statistics machine-readable field codes. Numeric values are
    deliberately Decimal-only so exchange JSON floats cannot enter the
    Application/Core boundary.
    """

    instrument_id: InstrumentId
    as_of: datetime
    values: Mapping[str, MarketDataValue]

    def __post_init__(self) -> None:
        instrument_id = self.instrument_id
        if not isinstance(instrument_id, InstrumentId):
            instrument_id = InstrumentId(instrument_id)
            object.__setattr__(self, "instrument_id", instrument_id)
        object.__setattr__(self, "as_of", _as_utc(self.as_of))
        if not isinstance(self.values, Mapping):
            raise TypeError("values must be a mapping")
        normalized: dict[str, MarketDataValue] = {}
        for key, value in self.values.items():
            if not isinstance(key, str):
                raise TypeError("market-data keys must be strings")
            normalized_key = str(CustomFieldCode(key))
            if normalized_key in normalized:
                raise ValueError(f"duplicate market-data key: {normalized_key!r}")
            _validate_value(value)
            normalized[normalized_key] = value
        object.__setattr__(self, "values", MappingProxyType(dict(sorted(normalized.items()))))

    def get(self, key: str) -> MarketDataValue | None:
        """Return a value by normalized key, or None when it is not supplied."""

        if not isinstance(key, str):
            raise TypeError("market-data key must be a string")
        return self.values.get(str(CustomFieldCode(key)))

    def has(self, key: str) -> bool:
        if not isinstance(key, str):
            raise TypeError("market-data key must be a string")
        return str(CustomFieldCode(key)) in self.values
