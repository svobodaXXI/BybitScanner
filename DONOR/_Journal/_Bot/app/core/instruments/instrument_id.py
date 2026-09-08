"""Instrument identifier value object."""

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class InstrumentId:
    """Immutable UUID-based identifier for an instrument."""

    value: UUID | str

    def __post_init__(self) -> None:
        if isinstance(self.value, UUID):
            parsed = self.value
        elif isinstance(self.value, str):
            try:
                parsed = UUID(self.value)
            except ValueError as error:
                raise ValueError(f"invalid InstrumentId UUID: {self.value!r}") from error
        else:
            raise TypeError("InstrumentId value must be UUID or str")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def generate(cls) -> "InstrumentId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "InstrumentId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

