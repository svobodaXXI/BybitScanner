"""Typed context used to resolve relevant custom field definitions."""

from dataclasses import dataclass

from .codes import SetupCode, StrategyCode
from .custom_field_scope import _dimension
from .enums import CustomFieldPhase


def _phase(value: CustomFieldPhase | str) -> CustomFieldPhase:
    if isinstance(value, CustomFieldPhase):
        return value
    if isinstance(value, str):
        try:
            return CustomFieldPhase(value)
        except ValueError as error:
            raise ValueError(f"invalid phase: {value!r}") from error
    raise TypeError("phase must be CustomFieldPhase")


@dataclass(frozen=True, slots=True)
class CustomFieldResolutionContext:
    """Small immutable, normalized context; it is not a Trade or ORM object."""

    phase: CustomFieldPhase
    exchange: str | None = None
    market: str | None = None
    strategy_code: StrategyCode | str | None = None
    setup_code: SetupCode | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "phase", _phase(self.phase))
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
        phase: CustomFieldPhase,
        exchange: str | None = None,
        market: str | None = None,
        strategy_code: StrategyCode | str | None = None,
        setup_code: SetupCode | str | None = None,
    ) -> "CustomFieldResolutionContext":
        return cls(phase, exchange, market, strategy_code, setup_code)
