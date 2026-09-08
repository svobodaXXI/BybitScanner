"""SQLAlchemy async adapter for append-only historical custom values."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.application.errors import DuplicateTradeCustomValueError, PersistenceIntegrityError
from app.application.ports.repositories import TradeCustomValueRepository
from app.core.statistics.ids import CustomFieldDefinitionId
from app.core.statistics.trade_custom_value import TradeCustomValue
from app.core.trades.trade_id import TradeId

from ..mappers import trade_custom_value_from_orm, trade_custom_value_to_orm
from ..models.trade_custom_value import TradeCustomValueORM
from ._common import is_named_constraint, require_session


class SqlAlchemyTradeCustomValueRepository(TradeCustomValueRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def add(self, value: TradeCustomValue) -> None:
        if not isinstance(value, TradeCustomValue):
            raise TypeError("value must be TradeCustomValue")
        existing = await self.get_for_field(
            trade_id=value.trade_id,
            field_id=value.field_id,
            definition_version=value.definition_version,
        )
        if existing is not None:
            raise DuplicateTradeCustomValueError("trade/field/definition-version value already exists")
        try:
            self._session.add(trade_custom_value_to_orm(value))
            await self._session.flush()
        except IntegrityError as error:
            if is_named_constraint(error, "uq_trade_custom_values_trade_field_version"):
                raise DuplicateTradeCustomValueError("trade/field/definition-version value already exists") from error
            raise PersistenceIntegrityError("TradeCustomValue could not be persisted") from error

    async def upsert(self, value: TradeCustomValue) -> None:
        if not isinstance(value, TradeCustomValue):
            raise TypeError("value must be TradeCustomValue")
        existing = await self.get_for_field(
            trade_id=value.trade_id,
            field_id=value.field_id,
            definition_version=value.definition_version,
        )
        if existing is None:
            await self.add(value)
            return
        model = await self._session.get(TradeCustomValueORM, existing.id.value)
        if model is None:
            await self.add(value)
            return
        candidate = trade_custom_value_to_orm(value)
        model.source = candidate.source
        model.value_type = candidate.value_type
        model.text_value = candidate.text_value
        model.number_value = candidate.number_value
        model.bool_value = candidate.bool_value
        model.option_id = candidate.option_id
        model.recorded_at = candidate.recorded_at
        await self._session.flush()

    async def list_by_trade(self, trade_id: TradeId) -> tuple[TradeCustomValue, ...]:
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        result = await self._session.execute(
            select(TradeCustomValueORM)
            .where(TradeCustomValueORM.trade_id == trade_id.value)
            .order_by(
                TradeCustomValueORM.recorded_at.asc(),
                TradeCustomValueORM.field_id.asc(),
                TradeCustomValueORM.definition_version.asc(),
            )
        )
        return tuple(trade_custom_value_from_orm(model) for model in result.scalars().all())

    async def get_for_field(
        self,
        *,
        trade_id: TradeId,
        field_id: CustomFieldDefinitionId,
        definition_version: int,
    ) -> TradeCustomValue | None:
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        if not isinstance(field_id, CustomFieldDefinitionId):
            raise TypeError("field_id must be CustomFieldDefinitionId")
        if type(definition_version) is not int or definition_version < 1:
            raise ValueError("definition_version must be an integer >= 1")
        result = await self._session.execute(
            select(TradeCustomValueORM).where(
                TradeCustomValueORM.trade_id == trade_id.value,
                TradeCustomValueORM.field_id == field_id.value,
                TradeCustomValueORM.definition_version == definition_version,
            )
        )
        model = result.scalar_one_or_none()
        return None if model is None else trade_custom_value_from_orm(model)
