"""Trade identifier value object."""

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class TradeId:
    """Immutable UUID-based identifier for a trade."""

    value: UUID | str

    def __post_init__(self) -> None:
        if isinstance(self.value, UUID):
            parsed = self.value
        elif isinstance(self.value, str):
            try:
                parsed = UUID(self.value)
            except ValueError as error:
                raise ValueError(f"invalid TradeId UUID: {self.value!r}") from error
        else:
            raise TypeError("TradeId value must be UUID or str")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def generate(cls) -> "TradeId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "TradeId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

