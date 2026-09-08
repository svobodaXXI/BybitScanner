"""Account identifier value object."""

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class AccountId:
    """Immutable UUID-based identifier for an account."""

    value: UUID | str

    def __post_init__(self) -> None:
        if isinstance(self.value, UUID):
            parsed = self.value
        elif isinstance(self.value, str):
            try:
                parsed = UUID(self.value)
            except ValueError as error:
                raise ValueError(f"invalid AccountId UUID: {self.value!r}") from error
        else:
            raise TypeError("AccountId value must be UUID or str")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def generate(cls) -> "AccountId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "AccountId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)

