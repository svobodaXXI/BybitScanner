"""Pure application orchestration for resolving and enriching trade statistics."""

from collections.abc import Iterable
from datetime import datetime
from dataclasses import dataclass

from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.custom_field_resolver import CustomFieldResolver
from app.core.statistics.custom_field_scope import CustomFieldScope
from app.core.statistics.derived_value_context import DerivedValueContext
from app.core.statistics.derived_value_result import DerivedValueStatus
from app.core.statistics.derived_value_service import DerivedValueService
from app.core.statistics.enums import CustomFieldSource
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.trade_id import TradeId
from app.application.market_data import MarketDataContext

from .trade_enrichment_result import EnrichmentFieldIssue, TradeEnrichmentResult, TradeEnrichmentStatus


@dataclass(frozen=True, slots=True)
class TradeEnrichmentService:
    """Stateless bridge between resolution, derived calculation, and current values."""

    resolver: CustomFieldResolver = CustomFieldResolver()
    derived_value_service: DerivedValueService = DerivedValueService()

    def enrich(
        self,
        definitions: Iterable[CustomFieldDefinition],
        scopes: Iterable[CustomFieldScope],
        existing_values: Iterable[TradeCustomValue],
        resolution_context,
        derived_context: DerivedValueContext,
        *,
        trade_id: TradeId | None = None,
        recorded_at: datetime | None = None,
        market_data_context: MarketDataContext | None = None,
    ) -> TradeEnrichmentResult:
        resolved_fields = self.resolver.resolve(definitions, scopes, resolution_context)
        values = tuple(existing_values)
        if any(not isinstance(value, TradeCustomValue) for value in values):
            raise TypeError("existing_values must contain only TradeCustomValue values")
        current_trade_id = self._resolve_trade_id(values, trade_id)
        self._validate_duplicate_values(values)
        self._validate_trade_ids(values, current_trade_id)

        current_values: dict[tuple[TradeId, object, int], TradeCustomValue] = {}
        for value in values:
            field = next(
                (
                    candidate
                    for candidate in resolved_fields
                    if candidate.id == value.field_id and candidate.definition_version == value.definition_version
                ),
                None,
            )
            if field is None:
                continue
            value.validate_against(field)
            current_values[(value.trade_id, value.field_id, value.definition_version)] = value

        generated_values: list[TradeCustomValue] = []
        missing_required: list[CustomFieldDefinition] = []
        missing_optional: list[CustomFieldDefinition] = []
        unavailable: list[EnrichmentFieldIssue] = []
        unsupported: list[EnrichmentFieldIssue] = []

        for field in resolved_fields:
            key = (current_trade_id, field.id, field.definition_version)
            if key in current_values:
                continue  # Existing value always wins; no automatic overwrite.
            if field.source is CustomFieldSource.MANUAL:
                (missing_required if (field.required or field.required_for_statistics) else missing_optional).append(field)
                continue
            if field.source is CustomFieldSource.DERIVED:
                calculation = self.derived_value_service.calculate(field, derived_context)
                if calculation.status is DerivedValueStatus.CALCULATED:
                    if current_trade_id is None:
                        raise ValueError("trade_id is required when generating a TradeCustomValue")
                    if recorded_at is None:
                        raise ValueError("recorded_at is required when generating a TradeCustomValue")
                    generated_values.append(
                        TradeCustomValue.create(
                            trade_id=current_trade_id,
                            field_definition=field,
                            value=calculation.value,
                            recorded_at=recorded_at,
                            source=CustomFieldSource.DERIVED,
                        )
                    )
                elif calculation.status is DerivedValueStatus.NOT_AVAILABLE:
                    unavailable.append(EnrichmentFieldIssue(field, calculation.reason or "value unavailable"))
                else:
                    unsupported.append(EnrichmentFieldIssue(field, calculation.reason or "value unsupported"))
                continue
            if field.source is CustomFieldSource.MARKET_DATA:
                market_value = None if market_data_context is None else market_data_context.get(str(field.code))
                if market_value is None:
                    unavailable.append(
                        EnrichmentFieldIssue(field, "market-data value is unavailable")
                    )
                    continue
                if current_trade_id is None:
                    raise ValueError("trade_id is required when generating a TradeCustomValue")
                if recorded_at is None:
                    raise ValueError("recorded_at is required when generating a TradeCustomValue")
                try:
                    generated_values.append(
                        TradeCustomValue.create(
                            trade_id=current_trade_id,
                            field_definition=field,
                            value=market_value,
                            recorded_at=recorded_at,
                            source=CustomFieldSource.MARKET_DATA,
                        )
                    )
                except (TypeError, ValueError) as error:
                    unsupported.append(EnrichmentFieldIssue(field, str(error)))
                continue
            unavailable.append(
                EnrichmentFieldIssue(
                    field,
                    f"no V1 provider for source {field.source.value}",
                )
            )

        manual_fields = tuple(
            field for field in resolved_fields if field.source is CustomFieldSource.MANUAL
        )
        if not manual_fields:
            status = TradeEnrichmentStatus.NOT_REQUIRED
        elif missing_required:
            status = TradeEnrichmentStatus.PENDING
        else:
            status = TradeEnrichmentStatus.COMPLETE

        relevant_existing = tuple(
            current_values[(current_trade_id, field.id, field.definition_version)]
            for field in resolved_fields
            if (current_trade_id, field.id, field.definition_version) in current_values
        )
        return TradeEnrichmentResult(
            resolved_fields=resolved_fields,
            existing_values=relevant_existing,
            generated_values=tuple(generated_values),
            missing_manual_required=tuple(missing_required),
            missing_manual_optional=tuple(missing_optional),
            unavailable_auto_fields=tuple(unavailable),
            unsupported_auto_fields=tuple(unsupported),
            status=status,
        )

    @staticmethod
    def _resolve_trade_id(values: tuple[TradeCustomValue, ...], trade_id: TradeId | None) -> TradeId | None:
        if trade_id is not None and not isinstance(trade_id, TradeId):
            trade_id = TradeId(trade_id)
        if not values:
            return trade_id
        value_trade_ids = {value.trade_id for value in values}
        if len(value_trade_ids) > 1:
            raise ValueError("existing_values contain multiple trade IDs")
        inferred = next(iter(value_trade_ids))
        if trade_id is not None and trade_id != inferred:
            raise ValueError("trade_id does not match existing_values")
        return inferred

    @staticmethod
    def _validate_duplicate_values(values: tuple[TradeCustomValue, ...]) -> None:
        seen: set[tuple[TradeId, object, int]] = set()
        for value in values:
            key = (value.trade_id, value.field_id, value.definition_version)
            if key in seen:
                raise ValueError("duplicate current TradeCustomValue for trade, field, and definition version")
            seen.add(key)

    @staticmethod
    def _validate_trade_ids(values: tuple[TradeCustomValue, ...], trade_id: TradeId | None) -> None:
        if trade_id is not None and any(value.trade_id != trade_id for value in values):
            raise ValueError("existing_values contain a different trade ID")
