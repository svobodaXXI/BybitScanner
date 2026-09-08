"""Immutable UUID identifiers for dynamic statistics entities."""

from dataclasses import dataclass
from uuid import UUID, uuid4


def _uuid(value: UUID | str, type_name: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        try:
            return UUID(value)
        except ValueError as error:
            raise ValueError(f"invalid {type_name} UUID: {value!r}") from error
    raise TypeError(f"{type_name} value must be UUID or str")


@dataclass(frozen=True, slots=True)
class CustomFieldDefinitionId:
    value: UUID | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _uuid(self.value, type(self).__name__))

    @classmethod
    def generate(cls) -> "CustomFieldDefinitionId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "CustomFieldDefinitionId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class CustomFieldOptionId:
    value: UUID | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _uuid(self.value, type(self).__name__))

    @classmethod
    def generate(cls) -> "CustomFieldOptionId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "CustomFieldOptionId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TradeCustomValueId:
    value: UUID | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _uuid(self.value, type(self).__name__))

    @classmethod
    def generate(cls) -> "TradeCustomValueId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "TradeCustomValueId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)
