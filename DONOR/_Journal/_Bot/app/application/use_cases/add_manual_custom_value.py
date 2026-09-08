"""AddManualCustomValue application use case."""

from decimal import Decimal, InvalidOperation

from app.application.dtos import AddManualCustomValueCommand, AddManualCustomValueResult
from app.application.errors import (
    CustomFieldNotApplicableError,
    CustomFieldNotFoundError,
    CustomFieldNotManualError,
    DuplicateTradeCustomValueError,
    InvalidCustomFieldValueError,
)
from app.application.ports.repositories import CustomFieldRepository, TradeCustomValueRepository, TradeRepository
from app.application.use_cases._common import default_resolution_context, require_trade, recorded_at_or_now
from app.core.statistics.custom_field_option import CustomFieldOption
from app.core.statistics.custom_field_resolver import CustomFieldResolver
from app.core.statistics.enums import CustomFieldSource, CustomFieldValueType
from app.core.statistics.ids import CustomFieldOptionId
from app.core.statistics.trade_custom_value import TradeCustomValue


class AddManualCustomValue:
    def __init__(
        self,
        trade_repository: TradeRepository,
        custom_field_repository: CustomFieldRepository,
        trade_custom_value_repository: TradeCustomValueRepository,
        resolver: CustomFieldResolver | None = None,
        *,
        allow_update: bool = False,
    ) -> None:
        self._trades = trade_repository
        self._fields = custom_field_repository
        self._values = trade_custom_value_repository
        self._resolver = resolver or CustomFieldResolver()
        self._allow_update = allow_update

    async def execute(self, command: AddManualCustomValueCommand) -> AddManualCustomValueResult:
        if not isinstance(command, AddManualCustomValueCommand):
            raise TypeError("command must be AddManualCustomValueCommand")
        trade = require_trade(await self._trades.get_by_id(command.trade_id), command.trade_id)
        definition = await self._fields.get_definition(command.field_id)
        if definition is None:
            raise CustomFieldNotFoundError(f"custom field not found: {command.field_id}")

        context = command.resolution_context or default_resolution_context(trade)
        scopes = await self._fields.list_scopes(definition.id)
        resolved = self._resolver.resolve((definition,), scopes, context)
        if not resolved:
            raise CustomFieldNotApplicableError(f"custom field is not applicable: {definition.code}")
        if definition.source is not CustomFieldSource.MANUAL:
            raise CustomFieldNotManualError(f"custom field is not MANUAL: {definition.code}")

        existing = await self._values.get_for_field(
            trade_id=trade.trade_id,
            field_id=definition.id,
            definition_version=definition.definition_version,
        )
        if existing is not None and not self._allow_update:
            raise DuplicateTradeCustomValueError("trade/field/definition-version value already exists")

        value, option = await self._validated_value(definition, command.value)
        try:
            historical_value = TradeCustomValue.create(
                trade_id=trade.trade_id,
                field_definition=definition,
                value=value,
                recorded_at=recorded_at_or_now(command.recorded_at),
                source=CustomFieldSource.MANUAL,
                option=option,
                value_id=None if existing is None else existing.id,
            )
        except (TypeError, ValueError) as error:
            raise InvalidCustomFieldValueError(str(error)) from error
        if self._allow_update:
            await self._values.upsert(historical_value)
        else:
            await self._values.add(historical_value)
        return AddManualCustomValueResult(historical_value)

    async def _validated_value(self, definition, raw_value):
        value_type = definition.value_type
        if value_type is CustomFieldValueType.TEXT:
            if type(raw_value) is not str:
                raise InvalidCustomFieldValueError("TEXT value must be str")
            return raw_value, None
        if value_type is CustomFieldValueType.NUMBER:
            if isinstance(raw_value, float) or isinstance(raw_value, bool):
                raise InvalidCustomFieldValueError("NUMBER value must be Decimal, never float or bool")
            if isinstance(raw_value, Decimal):
                value = raw_value
            elif isinstance(raw_value, (int, str)):
                try:
                    value = Decimal(str(raw_value))
                except (InvalidOperation, ValueError) as error:
                    raise InvalidCustomFieldValueError("NUMBER value must be a finite Decimal") from error
            else:
                raise InvalidCustomFieldValueError("NUMBER value must be a finite Decimal")
            if not value.is_finite():
                raise InvalidCustomFieldValueError("NUMBER value must be finite")
            return value, None
        if value_type is CustomFieldValueType.YES_NO:
            if type(raw_value) is not bool:
                raise InvalidCustomFieldValueError("YES_NO value must be bool")
            return raw_value, None
        if value_type is CustomFieldValueType.CHOICE:
            options = await self._fields.list_options(definition.id, include_inactive=True)
            option = self._find_option(options, raw_value)
            if option is None:
                raise InvalidCustomFieldValueError("CHOICE option does not belong to the field")
            if not option.active:
                raise InvalidCustomFieldValueError("inactive CHOICE option cannot be used")
            return option.id, option
        raise InvalidCustomFieldValueError(f"unsupported custom field type: {value_type}")

    @staticmethod
    def _find_option(options: tuple[CustomFieldOption, ...], raw_value) -> CustomFieldOption | None:
        if isinstance(raw_value, CustomFieldOption):
            return next((item for item in options if item.id == raw_value.id and item.field_id == raw_value.field_id), None)
        if isinstance(raw_value, CustomFieldOptionId):
            return next((item for item in options if item.id == raw_value), None)
        if isinstance(raw_value, str):
            try:
                option_id = CustomFieldOptionId(raw_value)
            except (TypeError, ValueError):
                return next((item for item in options if item.code == raw_value), None)
            return next((item for item in options if item.id == option_id), None)
        return None
