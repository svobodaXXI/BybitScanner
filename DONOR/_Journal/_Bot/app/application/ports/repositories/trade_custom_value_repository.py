"""Repository port for historical/current TradeCustomValue records."""

from typing import Protocol, runtime_checkable

from app.core.statistics.ids import CustomFieldDefinitionId
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.trade_id import TradeId


@runtime_checkable
class TradeCustomValueRepository(Protocol):
    """Async historical-value contract; infrastructure enforces uniqueness later."""

    async def add(self, value: TradeCustomValue) -> None:
        """Append a value; duplicate trade/field/version must be rejected by infrastructure."""
        ...

    async def upsert(self, value: TradeCustomValue) -> None:
        """Replace the current value for a trade/field/version without duplicating it."""
        ...

    async def list_by_trade(self, trade_id: TradeId) -> tuple[TradeCustomValue, ...]:
        """Return values ordered by field ID, then recorded_at."""
        ...

    async def get_for_field(
        self,
        *,
        trade_id: TradeId,
        field_id: CustomFieldDefinitionId,
        definition_version: int,
    ) -> TradeCustomValue | None:
        """Return the one value for a trade, field, and semantic version."""
        ...
