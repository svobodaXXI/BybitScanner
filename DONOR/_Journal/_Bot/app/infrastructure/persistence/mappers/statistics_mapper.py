"""Mappers for Dynamic Statistics definitions, scopes, options, and values."""

from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldStatus,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.statistics.ids import CustomFieldDefinitionId, CustomFieldOptionId, TradeCustomValueId
from app.core.trades.trade_id import TradeId

from ..models.custom_fields import CustomFieldDefinitionORM, CustomFieldOptionORM, CustomFieldScopeORM
from ..models.trade_custom_value import TradeCustomValueORM


def custom_field_definition_to_orm(definition: CustomFieldDefinition) -> CustomFieldDefinitionORM:
    return CustomFieldDefinitionORM(
        id=definition.id.value,
        code=str(definition.code),
        name=definition.name,
        value_type=definition.value_type.value,
        source=definition.source.value,
        status=definition.status.value,
        phase=definition.phase.value,
        required=definition.required,
        required_for_statistics=definition.required_for_statistics,
        definition_version=definition.definition_version,
        created_at=definition.created_at,
    )


def custom_field_definition_from_orm(model: CustomFieldDefinitionORM) -> CustomFieldDefinition:
    return CustomFieldDefinition(
        id=CustomFieldDefinitionId(model.id),
        code=model.code,
        name=model.name,
        value_type=CustomFieldValueType(model.value_type),
        source=CustomFieldSource(model.source),
        status=CustomFieldStatus(model.status),
        phase=model.phase,
        required=model.required,
        required_for_statistics=model.required_for_statistics,
        definition_version=model.definition_version,
        created_at=model.created_at,
    )


def custom_field_option_to_orm(option: CustomFieldOption) -> CustomFieldOptionORM:
    return CustomFieldOptionORM(
        id=option.id.value,
        field_id=option.field_id.value,
        code=option.code,
        label=option.label,
        sort_order=option.sort_order,
        active=option.active,
    )


def custom_field_option_from_orm(model: CustomFieldOptionORM) -> CustomFieldOption:
    return CustomFieldOption(
        id=CustomFieldOptionId(model.id),
        field_id=CustomFieldDefinitionId(model.field_id),
        code=model.code,
        label=model.label,
        sort_order=model.sort_order,
        active=model.active,
    )


def custom_field_scope_to_orm(scope: CustomFieldScope) -> CustomFieldScopeORM:
    return CustomFieldScopeORM(
        field_id=scope.field_id.value,
        exchange=scope.exchange,
        market=scope.market,
        strategy_code=None if scope.strategy_code is None else str(scope.strategy_code),
        setup_code=None if scope.setup_code is None else str(scope.setup_code),
    )


def custom_field_scope_from_orm(model: CustomFieldScopeORM) -> CustomFieldScope:
    return CustomFieldScope(
        field_id=CustomFieldDefinitionId(model.field_id),
        exchange=model.exchange,
        market=model.market,
        strategy_code=model.strategy_code,
        setup_code=model.setup_code,
    )


def trade_custom_value_to_orm(
    value: TradeCustomValue,
    definition: CustomFieldDefinition | None = None,
) -> TradeCustomValueORM:
    if not isinstance(value, TradeCustomValue):
        raise TypeError("value must be TradeCustomValue")
    if definition is not None:
        if not isinstance(definition, CustomFieldDefinition):
            raise TypeError("definition must be CustomFieldDefinition or None")
        value.validate_against(definition)
        value_type = definition.value_type
    else:
        value_type = value._value_type
        if value_type is None:
            raise ValueError("TradeCustomValue requires its field definition for ORM mapping")
    kwargs = dict(
        id=value.id.value,
        trade_id=value.trade_id.value,
        field_id=value.field_id.value,
        definition_version=value.definition_version,
        source=value.source.value,
        value_type=value_type.value,
        recorded_at=value.recorded_at,
        text_value=None,
        number_value=None,
        bool_value=None,
        option_id=None,
    )
    if value_type is CustomFieldValueType.TEXT:
        kwargs["text_value"] = value.value
    elif value_type is CustomFieldValueType.NUMBER:
        kwargs["number_value"] = value.value
    elif value_type is CustomFieldValueType.YES_NO:
        kwargs["bool_value"] = value.value
    else:
        kwargs["option_id"] = value.value.value
    return TradeCustomValueORM(**kwargs)


def trade_custom_value_from_orm(model: TradeCustomValueORM) -> TradeCustomValue:
    value_type = CustomFieldValueType(model.value_type)
    if value_type is CustomFieldValueType.TEXT:
        value = model.text_value
    elif value_type is CustomFieldValueType.NUMBER:
        value = model.number_value
    elif value_type is CustomFieldValueType.YES_NO:
        value = model.bool_value
    else:
        value = None if model.option_id is None else CustomFieldOptionId(model.option_id)
    if value is None:
        raise ValueError("persisted TradeCustomValue has no typed value")
    return TradeCustomValue(
        id=TradeCustomValueId(model.id),
        trade_id=TradeId(model.trade_id),
        field_id=CustomFieldDefinitionId(model.field_id),
        value=value,
        recorded_at=model.recorded_at,
        source=CustomFieldSource(model.source),
        definition_version=model.definition_version,
    )
