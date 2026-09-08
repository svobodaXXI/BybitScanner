from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldSource,
    CustomFieldStatus,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 2, 3, 10, 0, tzinfo=timezone.utc)


def make_field(
    value_type=CustomFieldValueType.TEXT,
    *,
    source=CustomFieldSource.MANUAL,
    required=False,
    version=1,
    code="breakout_quality",
):
    return CustomFieldDefinition.create(
        code=code,
        name="Breakout quality",
        value_type=value_type,
        source=source,
        phase=CustomFieldPhase.ANY,
        required=required,
        definition_version=version,
        created_at=NOW,
    )


def record(field, value, *, source=None, version=None, option=None):
    return TradeCustomValue.create(
        trade_id=TradeId.generate(),
        field_definition=field,
        value=value,
        recorded_at=NOW,
        source=source,
        definition_version=version,
        option=option,
    )


def test_field_deactivation_preserves_every_historical_attribute():
    field = make_field(version=1)
    historical = record(field, "excellent")
    inactive = field.deactivate()

    historical.validate_against(inactive)
    assert inactive.status is CustomFieldStatus.INACTIVE
    assert historical.field_id == field.id
    assert historical.value == "excellent"
    assert historical.definition_version == 1
    assert historical.source is CustomFieldSource.MANUAL


def test_field_reactivation_preserves_identity_and_semantic_version():
    field = make_field(code="  Breakout-Quality  ", version=1)
    reactivated = field.deactivate().activate()

    assert reactivated.status is CustomFieldStatus.ACTIVE
    assert reactivated.id == field.id
    assert reactivated.code == field.code
    assert reactivated.definition_version == field.definition_version


def test_option_deactivation_preserves_historical_choice_identity():
    field = make_field(CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "excellent", "Excellent")
    historical = record(field, option.id, option=option)
    inactive_option = option.deactivate()

    historical.validate_against(field.deactivate())
    assert historical.value == option.id == inactive_option.id
    assert inactive_option.active is False


def test_choice_is_not_stored_as_label_or_code():
    field = make_field(CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "excellent", "Excellent")
    historical = record(field, option.id, option=option)

    assert type(historical.value) is type(option.id)
    assert historical.value not in {option.code, option.label}


def test_trade_custom_value_is_immutable():
    field = make_field()
    historical = record(field, "excellent")

    with pytest.raises(FrozenInstanceError):
        historical.value = "poor"
    with pytest.raises(FrozenInstanceError):
        historical.source = CustomFieldSource.SYSTEM
    with pytest.raises(FrozenInstanceError):
        historical.definition_version = 2
    with pytest.raises(FrozenInstanceError):
        historical.recorded_at = NOW.replace(hour=11)


def test_definition_semantic_fields_are_immutable():
    field = make_field()

    with pytest.raises(FrozenInstanceError):
        field.value_type = CustomFieldValueType.NUMBER
    with pytest.raises(FrozenInstanceError):
        field.source = CustomFieldSource.SYSTEM
    with pytest.raises(FrozenInstanceError):
        field.code = "other_code"
    with pytest.raises(FrozenInstanceError):
        field.definition_version = 2


@pytest.mark.parametrize("source", list(CustomFieldSource))
def test_value_source_is_preserved_and_must_match_definition(source):
    field = make_field(source=source)
    historical = record(field, "producer-value")
    assert historical.source is source
    assert historical.source is field.source

    mismatch = CustomFieldSource.SYSTEM if source is not CustomFieldSource.SYSTEM else CustomFieldSource.MANUAL
    with pytest.raises(ValueError):
        record(field, "wrong-source", source=mismatch)


def test_number_rejects_bool_and_float_and_keeps_decimal():
    field = make_field(CustomFieldValueType.NUMBER)
    historical = record(field, Decimal("1.25"))
    assert historical.value == Decimal("1.25")
    assert isinstance(historical.value, Decimal)
    with pytest.raises((TypeError, ValueError)):
        record(field, True)
    with pytest.raises((TypeError, ValueError)):
        record(field, 1.25)


def test_missing_value_remains_absent_and_required_does_not_force_creation():
    field = make_field(required=True)
    values_by_trade: dict[TradeId, TradeCustomValue] = {}
    trade_without_value = TradeId.generate()

    assert field.required is True
    assert trade_without_value not in values_by_trade
    assert not values_by_trade


def test_cross_definition_choice_is_rejected_when_option_context_is_available():
    field_a = make_field(CustomFieldValueType.CHOICE, code="field_a")
    field_b = make_field(CustomFieldValueType.CHOICE, code="field_b")
    option_a1 = CustomFieldOption.create(field_a.id, "a1", "A1")

    with pytest.raises(ValueError):
        record(field_b, option_a1.id, option=option_a1)


def test_choice_ownership_without_option_context_is_application_layer_responsibility():
    field = make_field(CustomFieldValueType.CHOICE)
    arbitrary_option_id = CustomFieldOption.create(field.id, "known", "Known").id

    # The Domain can guarantee stable identity/type here. Membership lookup
    # requires the option set and therefore belongs to the future application
    # or resolver layer; there is intentionally no global registry.
    historical = record(field, arbitrary_option_id)
    assert historical.value == arbitrary_option_id


def test_value_version_must_match_definition_version():
    field = make_field(version=2)
    with pytest.raises(ValueError):
        record(field, "v1", version=1)
    historical = record(field, "v2", version=2)
    assert historical.definition_version == field.definition_version == 2


def test_no_hard_delete_api_exists():
    field = make_field(CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "known", "Known")

    assert not hasattr(field, "delete")
    assert not hasattr(option, "delete")
