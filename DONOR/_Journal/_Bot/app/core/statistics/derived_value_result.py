"""Explicit result contract for derived-value calculation."""

from dataclasses import dataclass
from enum import StrEnum


class DerivedValueStatus(StrEnum):
    CALCULATED = "CALCULATED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class DerivedValueResult:
    status: DerivedValueStatus
    value: object | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, DerivedValueStatus):
            raise TypeError("status must be DerivedValueStatus")
        if self.status is DerivedValueStatus.CALCULATED and self.value is None:
            raise ValueError("CALCULATED result requires a value")
        if self.status is not DerivedValueStatus.CALCULATED and self.value is not None:
            raise ValueError("only CALCULATED result may contain a value")

    @classmethod
    def calculated(cls, value: object) -> "DerivedValueResult":
        return cls(DerivedValueStatus.CALCULATED, value=value)

    @classmethod
    def not_available(cls, reason: str) -> "DerivedValueResult":
        return cls(DerivedValueStatus.NOT_AVAILABLE, reason=reason)

    @classmethod
    def unsupported(cls, reason: str) -> "DerivedValueResult":
        return cls(DerivedValueStatus.UNSUPPORTED, reason=reason)
