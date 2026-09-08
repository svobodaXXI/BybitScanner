"""Normalized, extensible machine-readable codes."""

from dataclasses import dataclass
import re


def _normalize(value: str, *, name: str, uppercase: bool) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    normalized = value.strip().replace("-", "_").replace(" ", "_")
    normalized = normalized.upper() if uppercase else normalized.lower()
    if not normalized:
        raise ValueError(f"{name} must not be empty")
    pattern = r"^[A-Z][A-Z0-9_]*$" if uppercase else r"^[a-z][a-z0-9_]*$"
    if re.fullmatch(pattern, normalized) is None:
        raise ValueError(f"{name} must be a machine-readable code: {value!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class CustomFieldCode:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize(self.value, name="CustomFieldCode", uppercase=False))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class StrategyCode:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize(self.value, name="StrategyCode", uppercase=True))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SetupCode:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _normalize(self.value, name="SetupCode", uppercase=True))

    def __str__(self) -> str:
        return self.value
