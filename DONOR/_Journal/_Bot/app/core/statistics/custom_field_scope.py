"""Scope dimensions for a custom field, without resolution policy."""

from dataclasses import dataclass

from .codes import SetupCode, StrategyCode
from .ids import CustomFieldDefinitionId


def _dimension(value: str | None, field_name: str, *, uppercase: bool = True) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str or None")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty when provided")
    return normalized.upper() if uppercase else normalized


@dataclass(frozen=True, slots=True)
class CustomFieldScope:
    field_id: CustomFieldDefinitionId
    exchange: str | None = None
    market: str | None = None
    strategy_code: StrategyCode | str | None = None
    setup_code: SetupCode | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.field_id, CustomFieldDefinitionId):
            object.__setattr__(self, "field_id", CustomFieldDefinitionId(self.field_id))
        object.__setattr__(self, "exchange", _dimension(self.exchange, "exchange"))
        object.__setattr__(self, "market", _dimension(self.market, "market"))
        if isinstance(self.strategy_code, str):
            object.__setattr__(self, "strategy_code", StrategyCode(self.strategy_code))
        elif self.strategy_code is not None and not isinstance(self.strategy_code, StrategyCode):
            raise TypeError("strategy_code must be StrategyCode, str, or None")
        if isinstance(self.setup_code, str):
            object.__setattr__(self, "setup_code", SetupCode(self.setup_code))
        elif self.setup_code is not None and not isinstance(self.setup_code, SetupCode):
            raise TypeError("setup_code must be SetupCode, str, or None")

    @classmethod
    def create(
        cls,
        field_id: CustomFieldDefinitionId,
        exchange: str | None = None,
        market: str | None = None,
        strategy_code: StrategyCode | str | None = None,
        setup_code: SetupCode | str | None = None,
    ) -> "CustomFieldScope":
        return cls(field_id, exchange, market, strategy_code, setup_code)

    @classmethod
    def global_scope(cls, field_id: CustomFieldDefinitionId) -> "CustomFieldScope":
        return cls(field_id)

    @property
    def is_global(self) -> bool:
        return all(value is None for value in (self.exchange, self.market, self.strategy_code, self.setup_code))
