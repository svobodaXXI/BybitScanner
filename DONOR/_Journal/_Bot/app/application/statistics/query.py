"""Read-only bulk query port for Statistics Engine V1."""

from typing import Protocol, runtime_checkable

from app.core.statistics.ids import CustomFieldDefinitionId
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.trade_id import TradeId

from .models import DynamicFieldMetadata, StatisticsFilter, StatisticsTradeRecord


@runtime_checkable
class TradeStatisticsQuery(Protocol):
    async def list_trades(self, filters: StatisticsFilter) -> tuple[StatisticsTradeRecord, ...]:
        """Return only the historical Trade facts needed by the engine."""
        ...

    async def get_dynamic_field(
        self,
        *,
        field_id: CustomFieldDefinitionId | None = None,
        field_code: str | None = None,
    ) -> DynamicFieldMetadata | None:
        """Resolve one current field identity plus its scopes/options."""
        ...

    async def list_custom_values(
        self,
        trade_ids: tuple[TradeId, ...],
        field_id: CustomFieldDefinitionId,
    ) -> tuple[TradeCustomValue, ...]:
        """Bulk-load historical values for a field; never one query per trade."""
        ...
