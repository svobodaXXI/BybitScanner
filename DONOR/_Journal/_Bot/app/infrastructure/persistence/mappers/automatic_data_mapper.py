"""Domain/ORM mapping for generic automatic observations."""

import json
from uuid import uuid4

from app.core.automatic_data import AutomaticFactorObservation
from app.infrastructure.persistence.models.automatic_data import AutomaticFactorObservationORM


def automatic_observation_to_orm(observation: AutomaticFactorObservation) -> AutomaticFactorObservationORM:
    values = {"value_decimal": None, "value_integer": None, "value_boolean": None, "value_text": None}
    column = {"DECIMAL": "value_decimal", "INTEGER": "value_integer", "BOOLEAN": "value_boolean", "TEXT": "value_text"}.get(observation.value_type)
    if column is None:
        raise ValueError(f"unsupported automatic value type: {observation.value_type}")
    values[column] = observation.value
    provenance = observation.provenance
    if provenance is not None and not isinstance(provenance, str):
        provenance = json.dumps(provenance, sort_keys=True, default=str)
    return AutomaticFactorObservationORM(
        id=uuid4(), trade_id=observation.trade_id.value, factor_id=observation.factor_id,
        definition_version=observation.definition_version, calculation_version=observation.calculation_version,
        value_type=observation.value_type, **values, unit=observation.unit, currency=observation.currency,
        source_kind=observation.source_kind, provider_key=observation.provider_key,
        capture_semantics=observation.capture_semantics, captured_at=observation.captured_at,
        source_timestamp=observation.source_timestamp, quality_status=observation.quality_status,
        availability_status=observation.availability_status, provenance=provenance,
    )


def automatic_observation_from_orm(model: AutomaticFactorObservationORM) -> AutomaticFactorObservation:
    values = {"DECIMAL": model.value_decimal, "INTEGER": model.value_integer, "BOOLEAN": model.value_boolean, "TEXT": model.value_text}
    provenance = model.provenance
    if isinstance(provenance, str):
        try: provenance = json.loads(provenance)
        except json.JSONDecodeError: pass
    return AutomaticFactorObservation(
        trade_id=model.trade_id, factor_id=model.factor_id, definition_version=model.definition_version,
        calculation_version=model.calculation_version, value_type=model.value_type, value=values.get(model.value_type),
        unit=model.unit, currency=model.currency, source_kind=model.source_kind, provider_key=model.provider_key,
        capture_semantics=model.capture_semantics, captured_at=model.captured_at,
        source_timestamp=model.source_timestamp, quality_status=model.quality_status,
        availability_status=model.availability_status, provenance=provenance,
    )
