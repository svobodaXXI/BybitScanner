"""Generic, append-only-friendly automatic factor observations."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum

from app.core.trades.trade_id import TradeId
from .definition import AutomaticFactorSourceKind, CaptureSemantics


class AutomaticFactorAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    MISSING_SOURCE_DATA = "MISSING_SOURCE_DATA"
    ERROR = "ERROR"


class AutomaticFactorQuality(StrEnum):
    VALID = "VALID"
    MISSING = "MISSING"
    STALE = "STALE"
    PARTIAL = "PARTIAL"
    ESTIMATED = "ESTIMATED"
    ERROR = "ERROR"


class AutomaticObservationValueType(StrEnum):
    DECIMAL = "DECIMAL"
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


def _utc(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


class AutomaticFactorObservation:
    """A typed observation; absent values stay absent and are never coerced to zero."""

    __slots__ = ("trade_id", "factor_id", "definition_version", "calculation_version", "value_type", "value", "unit", "currency", "source_kind", "provider_key", "capture_semantics", "captured_at", "source_timestamp", "quality_status", "availability_status", "provenance")

    def __init__(self, *, trade_id, factor_id, definition_version=1, calculation_version="1", value_type=AutomaticObservationValueType.DECIMAL, value=None, unit=None, currency=None, source_kind, provider_key=None, capture_semantics, captured_at, source_timestamp=None, quality_status=AutomaticFactorQuality.VALID, availability_status=AutomaticFactorAvailability.AVAILABLE, provenance=None):
        self.trade_id = trade_id if isinstance(trade_id, TradeId) else TradeId(trade_id)
        if not isinstance(factor_id, str) or not factor_id.strip():
            raise ValueError("factor_id must be a non-empty string")
        self.factor_id = factor_id
        self.definition_version = int(definition_version)
        self.calculation_version = str(calculation_version)
        self.value_type = AutomaticObservationValueType(value_type)
        if value is not None:
            valid = {
                AutomaticObservationValueType.DECIMAL: isinstance(value, (Decimal, int, float)) and not isinstance(value, bool),
                AutomaticObservationValueType.INTEGER: isinstance(value, int) and not isinstance(value, bool),
                AutomaticObservationValueType.BOOLEAN: isinstance(value, bool),
                AutomaticObservationValueType.TEXT: isinstance(value, str),
            }[self.value_type]
            if not valid: raise TypeError(f"value does not match {self.value_type.value}")
        self.value = value
        self.unit = unit
        self.currency = currency.upper() if isinstance(currency, str) else currency
        self.source_kind = AutomaticFactorSourceKind(source_kind)
        self.provider_key = provider_key
        self.capture_semantics = CaptureSemantics(capture_semantics)
        self.captured_at = _utc(captured_at, "captured_at")
        self.source_timestamp = _utc(source_timestamp, "source_timestamp")
        self.quality_status = AutomaticFactorQuality(quality_status)
        self.availability_status = AutomaticFactorAvailability(availability_status)
        self.provenance = provenance

    def __repr__(self) -> str:
        return f"AutomaticFactorObservation(trade_id={self.trade_id!s}, factor_id={self.factor_id!r}, value={self.value!r})"
