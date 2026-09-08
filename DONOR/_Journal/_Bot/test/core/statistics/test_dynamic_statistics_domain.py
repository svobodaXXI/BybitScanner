from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldStatus,
    CustomFieldValueType,
    SetupCode,
    StrategyCode,
    TradeCustomValue,
)
from app.core.trades.trade_id import TradeId


UTC_NOW = datetime(2026, 1, 2, 12, 30, tzinfo=timezone.utc)


def definition(value_type=CustomFieldValueType.TEXT, **kwargs):
    return CustomFieldDefinition.create(
        code=kwargs.pop("code", "market_note"),
        name=kwargs.pop("name", "Market note"),
        value_type=value_type,
        source=kwargs.pop("source", CustomFieldSource.MANUAL),
        phase=kwargs.pop("phase", CustomFieldPhase.ANY),
        created_at=UTC_NOW,
        **kwargs,
    )


def test_definition_lifecycle_and_normalization():
    field = definition(code=" Market-Note ", required=True)
    assert field.code.value == "market_note"
    assert field.required is True
    assert field.status is CustomFieldStatus.ACTIVE
    assert field.created_at == UTC_NOW
    inactive = field.deactivate()
    assert inactive.status is CustomFieldStatus.INACTIVE
    assert inactive.id == field.id
    assert inactive.activate().status is CustomFieldStatus.ACTIVE


@pytest.mark.parametrize("kwargs", [{"code": " "}, {"name": " "}, {"definition_version": 0}])
def test_definition_rejects_invalid_data(kwargs):
    with pytest.raises((TypeError, ValueError)):
        definition(**kwargs)


def test_option_identity_is_stable_when_deactivated():
    field = definition(value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, " Breakout-Confirmed ", " Breakout confirmed ", 2)
    assert option.code == "breakout_confirmed"
    assert option.active is True
    inactive = option.deactivate()
    assert inactive.id == option.id
    assert inactive.active is False
    assert inactive.activate().active is True


@pytest.mark.parametrize("kwargs", [{"code": " "}, {"label": " "}, {"sort_order": -1}])
def test_option_rejects_invalid_data(kwargs):
    field = definition(value_type=CustomFieldValueType.CHOICE)
    with pytest.raises((TypeError, ValueError)):
        CustomFieldOption.create(field.id, kwargs.pop("code", "ok"), kwargs.pop("label", "OK"), **kwargs)


def test_scope_supports_all_dimensions_and_is_hashable():
    field = definition()
    global_scope = CustomFieldScope.global_scope(field.id)
    scoped = CustomFieldScope.create(field.id, "binance", "btc-usdt", "mean-reversion", "pullback")
    assert global_scope.is_global
    assert not scoped.is_global
    assert scoped.exchange == "BINANCE"
    assert scoped.market == "BTC-USDT"
    assert scoped.strategy_code == StrategyCode("MEAN_REVERSION")
    assert scoped.setup_code == SetupCode("PULLBACK")
    assert hash(scoped)


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (CustomFieldValueType.TEXT, "breakout"),
        (CustomFieldValueType.NUMBER, Decimal("1.25")),
        (CustomFieldValueType.YES_NO, True),
    ],
)
def test_trade_custom_value_is_typed_and_timestamped(value_type, value):
    field = definition(value_type=value_type)
    stored = TradeCustomValue.create(TradeId.generate(), field, value, UTC_NOW)
    assert stored.field_id == field.id
    assert stored.value == value
    assert stored.recorded_at == UTC_NOW
    assert stored.definition_version == field.definition_version
    assert stored.source is field.source


def test_choice_stores_option_id_not_label():
    field = definition(value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "breakout", "Breakout")
    stored = TradeCustomValue.create(TradeId.generate(), field, option.id, UTC_NOW, option=option)
    assert stored.value == option.id
    assert stored.value != option.label


@pytest.mark.parametrize(
    ("value_type", "value"),
    [
        (CustomFieldValueType.TEXT, Decimal("1")),
        (CustomFieldValueType.NUMBER, 1.25),
        (CustomFieldValueType.YES_NO, 1),
        (CustomFieldValueType.CHOICE, "breakout"),
    ],
)
def test_trade_custom_value_rejects_wrong_types(value_type, value):
    with pytest.raises((TypeError, ValueError)):
        TradeCustomValue.create(TradeId.generate(), definition(value_type=value_type), value, UTC_NOW)


def test_historical_value_survives_field_and_option_deactivation():
    field = definition(value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "breakout", "Breakout")
    stored = TradeCustomValue.create(TradeId.generate(), field, option.id, UTC_NOW, option=option)
    inactive_field = field.deactivate()
    inactive_option = option.deactivate()
    stored.validate_against(inactive_field)
    assert stored.field_id == inactive_field.id
    assert stored.value == inactive_option.id
    assert inactive_field.activate().id == field.id


def test_new_values_are_not_created_for_inactive_field_or_option():
    field = definition(value_type=CustomFieldValueType.CHOICE)
    option = CustomFieldOption.create(field.id, "breakout", "Breakout")
    with pytest.raises(ValueError):
        TradeCustomValue.create(TradeId.generate(), field.deactivate(), option.id, UTC_NOW, option=option)
    with pytest.raises(ValueError):
        TradeCustomValue.create(TradeId.generate(), field, option.id, UTC_NOW, option=option.deactivate())
