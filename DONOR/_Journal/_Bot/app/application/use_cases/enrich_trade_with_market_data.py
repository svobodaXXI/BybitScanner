"""Request-driven MARKET_DATA + DERIVED trade enrichment."""

from dataclasses import dataclass
from datetime import datetime

from app.application.dtos import EnrichTradeWithMarketDataCommand, TradeView
from app.application.errors import (
    MarketDataMappingError,
    MarketDataPayloadError,
    MarketDataUnavailableError,
)
from app.application.market_data import (
    MarketDataContext,
    MarketDataFetchStatus,
    normalize_market_data_timestamp,
)
from app.application.ports.market_data_provider import MarketDataProvider
from app.application.ports.unit_of_work import UnitOfWork
from app.application.statistics import TradeEnrichmentService
from app.application.use_cases._common import (
    default_resolution_context,
    derived_context_from_trade,
    recorded_at_or_now,
    require_trade,
    view,
)
from app.core.statistics.enums import CustomFieldSource
from app.core.trades.enums import TradeStatus
from app.core.trades.trade_id import TradeId
from app.application.statistics.trade_enrichment_result import TradeEnrichmentResult
from app.core.statistics.trade_custom_value import TradeCustomValue


@dataclass(frozen=True, slots=True)
class EnrichTradeWithMarketDataResult:
    trade: TradeView
    enrichment: TradeEnrichmentResult
    persisted_values: tuple[TradeCustomValue, ...]
    market_data_status: MarketDataFetchStatus
    market_data_as_of: datetime | None = None

    @property
    def trade_id(self) -> TradeId:
        return self.trade.trade_id

    @property
    def generated_values(self):
        return self.enrichment.generated_values

    @property
    def unavailable_auto_fields(self):
        return self.enrichment.unavailable_auto_fields

    @property
    def unsupported_auto_fields(self):
        return self.enrichment.unsupported_auto_fields


class EnrichTradeWithMarketData:
    """Populate missing automatic fields in one application transaction."""

    def __init__(
        self,
        uow_factory,
        market_data_provider: MarketDataProvider,
        enrichment_service: TradeEnrichmentService | None = None,
    ) -> None:
        if not isinstance(market_data_provider, MarketDataProvider):
            raise TypeError("market_data_provider must implement MarketDataProvider")
        self._uow_factory = uow_factory
        self._provider = market_data_provider
        self._service = enrichment_service or TradeEnrichmentService()

    async def execute(self, command: EnrichTradeWithMarketDataCommand) -> EnrichTradeWithMarketDataResult:
        if not isinstance(command, EnrichTradeWithMarketDataCommand):
            raise TypeError("command must be EnrichTradeWithMarketDataCommand")
        async with self._uow_factory() as uow:
            trade = require_trade(await uow.trades.get_by_id(command.trade_id), command.trade_id)
            definitions = await uow.custom_fields.list_definitions(include_inactive=False)
            scopes = await uow.custom_fields.list_scopes()
            existing_values = await uow.custom_values.list_by_trade(trade.trade_id)
            resolution_context = command.resolution_context or default_resolution_context(trade)
            resolved_fields = self._service.resolver.resolve(definitions, scopes, resolution_context)
            existing_keys = {
                (value.field_id, value.definition_version)
                for value in existing_values
            }
            required_keys = tuple(
                sorted(
                    str(field.code)
                    for field in resolved_fields
                    if field.source is CustomFieldSource.MARKET_DATA
                    and (field.id, field.definition_version) not in existing_keys
                )
            )

            market_data_context: MarketDataContext | None = None
            market_data_status = MarketDataFetchStatus.NOT_REQUIRED
            market_data_as_of = None
            if required_keys:
                at = normalize_market_data_timestamp(command.at or _default_market_data_time(trade))
                try:
                    market_data_context = await self._provider.get_trade_context(
                        trade.instrument_id,
                        at,
                        required_keys=required_keys,
                    )
                    if not isinstance(market_data_context, MarketDataContext):
                        raise MarketDataPayloadError("provider must return MarketDataContext")
                    if market_data_context.instrument_id != trade.instrument_id:
                        raise MarketDataMappingError("provider context instrument does not match the Trade")
                    market_data_status = MarketDataFetchStatus.AVAILABLE
                    market_data_as_of = market_data_context.as_of
                except MarketDataUnavailableError:
                    market_data_status = MarketDataFetchStatus.UNAVAILABLE
                except (MarketDataMappingError, MarketDataPayloadError):
                    raise
                except Exception:
                    # Provider implementations must translate their SDK errors;
                    # this boundary prevents accidental leakage of raw exceptions.
                    market_data_status = MarketDataFetchStatus.UNAVAILABLE

            enrichment = self._service.enrich(
                definitions,
                scopes,
                existing_values,
                resolution_context,
                command.derived_context or derived_context_from_trade(trade),
                trade_id=trade.trade_id,
                recorded_at=recorded_at_or_now(command.recorded_at),
                market_data_context=market_data_context,
            )
            for generated_value in enrichment.generated_values:
                await uow.custom_values.add(generated_value)
            await uow.commit()
            return EnrichTradeWithMarketDataResult(
                trade=view(trade),
                enrichment=enrichment,
                persisted_values=enrichment.generated_values,
                market_data_status=market_data_status,
                market_data_as_of=market_data_as_of,
            )


def _default_market_data_time(trade):
    """Use the trade snapshot time, never an implicit wall-clock lookup."""

    if trade.status is TradeStatus.CLOSED:
        return trade.closed_at
    return trade.opened_at
