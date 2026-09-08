"""Internal journal owner identifier value object."""

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class OwnerId:
    """Immutable UUID-based identity used for server-side ownership scope."""

    value: UUID | str

    def __post_init__(self) -> None:
        if isinstance(self.value, UUID):
            parsed = self.value
        elif isinstance(self.value, str):
            try:
                parsed = UUID(self.value)
            except ValueError as error:
                raise ValueError(f"invalid OwnerId UUID: {self.value!r}") from error
        else:
            raise TypeError("OwnerId value must be UUID or str")
        object.__setattr__(self, "value", parsed)

    @classmethod
    def generate(cls) -> "OwnerId":
        return cls(uuid4())

    @classmethod
    def parse(cls, value: UUID | str) -> "OwnerId":
        return cls(value)

    def __str__(self) -> str:
        return str(self.value)


# Migration/backward-compatibility identity for the pre-owner single-user database.
# It is internal and deliberately unrelated to Telegram user ids or trading account ids.
LEGACY_SINGLE_OWNER_ID = OwnerId("00000000-0000-0000-0000-000000000001")
