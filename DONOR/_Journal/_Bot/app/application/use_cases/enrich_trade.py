"""EnrichTrade application use case."""

from app.application.dtos import EnrichTradeCommand, EnrichTradeResult
from app.application.ports.repositories import CustomFieldRepository, TradeCustomValueRepository, TradeRepository
from app.application.statistics import TradeEnrichmentService
from app.application.use_cases._common import (
    default_resolution_context,
    derived_context_from_trade,
    recorded_at_or_now,
    require_trade,
    view,
)


class EnrichTrade:
    def __init__(
        self,
        trade_repository: TradeRepository,
        custom_field_repository: CustomFieldRepository,
        trade_custom_value_repository: TradeCustomValueRepository,
        enrichment_service: TradeEnrichmentService | None = None,
    ) -> None:
        self._trades = trade_repository
        self._fields = custom_field_repository
        self._values = trade_custom_value_repository
        self._service = enrichment_service or TradeEnrichmentService()

    async def execute(self, command: EnrichTradeCommand) -> EnrichTradeResult:
        if not isinstance(command, EnrichTradeCommand):
            raise TypeError("command must be EnrichTradeCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        definitions = await self._fields.list_definitions(include_inactive=False)
        scopes = await self._fields.list_scopes()
        existing_values = await self._values.list_by_trade(trade.trade_id)
        enrichment = self._service.enrich(
            definitions,
            scopes,
            existing_values,
            command.resolution_context or default_resolution_context(trade),
            command.derived_context or derived_context_from_trade(trade),
            trade_id=trade.trade_id,
            recorded_at=recorded_at_or_now(command.recorded_at),
        )
        for generated_value in enrichment.generated_values:
            await self._values.add(generated_value)
        return EnrichTradeResult(view(trade), enrichment, enrichment.generated_values)
