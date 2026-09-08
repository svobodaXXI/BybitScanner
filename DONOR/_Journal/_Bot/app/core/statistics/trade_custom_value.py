"""Historical typed value assigned to a trade custom field."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.core.trades.trade_id import TradeId

from .custom_field_definition import CustomFieldDefinition, _as_utc
from .custom_field_option import CustomFieldOption
from .enums import CustomFieldSource, CustomFieldStatus, CustomFieldValueType
from .ids import CustomFieldDefinitionId, CustomFieldOptionId, TradeCustomValueId


@dataclass(frozen=True, slots=True)
class TradeCustomValue:
    """A value keeps its field identity and definition version for history."""

    id: TradeCustomValueId
    trade_id: TradeId
    field_id: CustomFieldDefinitionId
    value: str | Decimal | bool | CustomFieldOptionId
    recorded_at: datetime
    source: CustomFieldSource
    definition_version: int
    _value_type: CustomFieldValueType | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.id, TradeCustomValueId):
            object.__setattr__(self, "id", TradeCustomValueId(self.id))
        if not isinstance(self.trade_id, TradeId):
            object.__setattr__(self, "trade_id", TradeId(self.trade_id))
        if not isinstance(self.field_id, CustomFieldDefinitionId):
            object.__setattr__(self, "field_id", CustomFieldDefinitionId(self.field_id))
        if not isinstance(self.source, CustomFieldSource):
            if isinstance(self.source, str):
                object.__setattr__(self, "source", CustomFieldSource(self.source))
            else:
                raise TypeError("source must be CustomFieldSource")
        if type(self.definition_version) is not int or self.definition_version < 1:
            raise ValueError("definition_version must be an integer >= 1")
        object.__setattr__(self, "recorded_at", _as_utc(self.recorded_at, "recorded_at"))
        self._validate_supported_value(self.value)
        if self._value_type is not None:
            self._validate_value_for_type(self.value, self._value_type)

    @classmethod
    def create(
        cls,
        trade_id: TradeId | CustomFieldDefinition,
        field_definition: CustomFieldDefinition | TradeId | None = None,
        value: object = None,
        recorded_at: datetime | None = None,
        *,
        field: CustomFieldDefinition | None = None,
        source: CustomFieldSource | None = None,
        definition_version: int | None = None,
        option: CustomFieldOption | None = None,
        value_id: TradeCustomValueId | None = None,
    ) -> "TradeCustomValue":
        # Also tolerate the natural (definition, trade_id, value, ...) ordering.
        if isinstance(trade_id, CustomFieldDefinition):
            trade_id, field_definition = field_definition, trade_id
        if field is not None:
            if field_definition is not None and field_definition is not field:
                raise TypeError("pass either field_definition or field, not both")
            field_definition = field
        if not isinstance(field_definition, CustomFieldDefinition):
            raise TypeError("field_definition must be CustomFieldDefinition")
        if not isinstance(trade_id, TradeId):
            trade_id = TradeId(trade_id)
        if field_definition.status is CustomFieldStatus.INACTIVE:
            raise ValueError("cannot create a new value for an inactive field")
        actual_source = field_definition.source if source is None else source
        if not isinstance(actual_source, CustomFieldSource):
            if isinstance(actual_source, str):
                actual_source = CustomFieldSource(actual_source)
            else:
                raise TypeError("source must be CustomFieldSource")
        if actual_source is not field_definition.source:
            raise ValueError("value source must match field definition source")
        actual_version = field_definition.definition_version if definition_version is None else definition_version
        if type(actual_version) is not int or actual_version < 1:
            raise ValueError("definition_version must be an integer >= 1")
        if actual_version != field_definition.definition_version:
            raise ValueError("value definition_version must match field definition")
        cls._validate_value_for_type(value, field_definition.value_type)
        if field_definition.value_type is CustomFieldValueType.CHOICE and option is not None:
            if option.field_id != field_definition.id or option.id != value:
                raise ValueError("choice option does not belong to the field or value identity")
            if not option.active:
                raise ValueError("inactive choice option cannot be used for a new value")
        return cls(
            id=value_id or TradeCustomValueId.generate(),
            trade_id=trade_id,
            field_id=field_definition.id,
            value=value,
            recorded_at=recorded_at or datetime.now(timezone.utc),
            source=actual_source,
            definition_version=actual_version,
            _value_type=field_definition.value_type,
        )

    from_definition = create

    @staticmethod
    def _validate_supported_value(value: object) -> None:
        if type(value) is str or type(value) is bool or isinstance(value, CustomFieldOptionId):
            return
        if isinstance(value, Decimal):
            if not value.is_finite():
                raise ValueError("NUMBER value must be finite")
            return
        raise TypeError("value must be str, Decimal, bool, or CustomFieldOptionId")

    @staticmethod
    def _validate_value_for_type(value: object, value_type: CustomFieldValueType) -> None:
        if value_type is CustomFieldValueType.TEXT:
            if type(value) is not str:
                raise TypeError("TEXT value must be str")
        elif value_type is CustomFieldValueType.NUMBER:
            if not isinstance(value, Decimal) or not value.is_finite():
                raise TypeError("NUMBER value must be a finite Decimal")
        elif value_type is CustomFieldValueType.YES_NO:
            if type(value) is not bool:
                raise TypeError("YES_NO value must be bool")
        elif value_type is CustomFieldValueType.CHOICE:
            if not isinstance(value, CustomFieldOptionId):
                raise TypeError("CHOICE value must be CustomFieldOptionId, not a label or code")

    def validate_against(self, field_definition: CustomFieldDefinition) -> None:
        """Validate type compatibility without invalidating historical inactive data."""
        if self.field_id != field_definition.id:
            raise ValueError("value belongs to a different custom field")
        if self.source is not field_definition.source:
            raise ValueError("value source does not match field definition source")
        self._validate_value_for_type(self.value, field_definition.value_type)
