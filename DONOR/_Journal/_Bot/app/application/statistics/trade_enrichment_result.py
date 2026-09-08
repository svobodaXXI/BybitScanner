"""Explicit result contract for trade enrichment orchestration."""

from dataclasses import dataclass
from enum import StrEnum

from app.core.statistics.custom_field_definition import CustomFieldDefinition
from app.core.statistics.enums import CustomFieldSource
from app.core.statistics.trade_custom_value import TradeCustomValue


class TradeEnrichmentStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class EnrichmentFieldIssue:
    """A resolved automatic field that cannot be populated in the current V1."""

    field: CustomFieldDefinition
    reason: str

    @property
    def source(self) -> CustomFieldSource:
        return self.field.source

    @property
    def code(self) -> str:
        return str(self.field.code)


@dataclass(frozen=True, slots=True)
class TradeEnrichmentResult:
    resolved_fields: tuple[CustomFieldDefinition, ...]
    existing_values: tuple[TradeCustomValue, ...]
    generated_values: tuple[TradeCustomValue, ...]
    missing_manual_required: tuple[CustomFieldDefinition, ...]
    missing_manual_optional: tuple[CustomFieldDefinition, ...]
    unavailable_auto_fields: tuple[EnrichmentFieldIssue, ...]
    unsupported_auto_fields: tuple[EnrichmentFieldIssue, ...]
    status: TradeEnrichmentStatus

    @property
    def all_values(self) -> tuple[TradeCustomValue, ...]:
        """Current values in deterministic field order; generated values are appended by field order."""
        return self.existing_values + self.generated_values
