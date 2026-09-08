"""Provider/calculator ports; implementations belong to infrastructure."""

from typing import Protocol, runtime_checkable

from .definition import AutomaticFactorDefinition
from .observation import AutomaticFactorObservation


@runtime_checkable
class AutomaticFactorProvider(Protocol):
    async def fetch(self, definition: AutomaticFactorDefinition, *, trade_id, context=None) -> AutomaticFactorObservation:
        ...


@runtime_checkable
class AutomaticFactorCalculator(Protocol):
    async def calculate(self, definition: AutomaticFactorDefinition, *, trade_id, context=None) -> AutomaticFactorObservation:
        ...
