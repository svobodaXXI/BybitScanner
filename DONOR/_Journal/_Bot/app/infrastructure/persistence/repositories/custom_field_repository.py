"""SQLAlchemy async adapter for the Dynamic Statistics catalog."""

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

from app.application.errors import CustomFieldSemanticMutationError, PersistenceIntegrityError
from app.application.ports.repositories import CustomFieldRepository
from app.core.statistics import CustomFieldDefinition, CustomFieldOption, CustomFieldScope
from app.core.statistics.enums import CustomFieldPhase, CustomFieldStatus
from app.core.statistics.ids import CustomFieldDefinitionId

from ..mappers import (
    custom_field_definition_from_orm,
    custom_field_definition_to_orm,
    custom_field_option_from_orm,
    custom_field_option_to_orm,
    custom_field_scope_from_orm,
    custom_field_scope_to_orm,
)
from ..models.custom_fields import CustomFieldDefinitionORM, CustomFieldOptionORM, CustomFieldScopeORM
from ._common import require_session


class SqlAlchemyCustomFieldRepository(CustomFieldRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def get_definition(self, field_id: CustomFieldDefinitionId) -> CustomFieldDefinition | None:
        if not isinstance(field_id, CustomFieldDefinitionId):
            raise TypeError("field_id must be CustomFieldDefinitionId")
        result = await self._session.execute(select(CustomFieldDefinitionORM).where(CustomFieldDefinitionORM.id == field_id.value))
        model = result.scalar_one_or_none()
        return None if model is None else custom_field_definition_from_orm(model)

    async def list_definitions(self, *, include_inactive: bool = False) -> tuple[CustomFieldDefinition, ...]:
        statement = select(CustomFieldDefinitionORM)
        if not include_inactive:
            statement = statement.where(CustomFieldDefinitionORM.status == CustomFieldStatus.ACTIVE.value)
        result = await self._session.execute(statement.order_by(CustomFieldDefinitionORM.code.asc(), CustomFieldDefinitionORM.id.asc()))
        return tuple(custom_field_definition_from_orm(model) for model in result.scalars().all())

    async def list_options(self, field_id: CustomFieldDefinitionId, *, include_inactive: bool = False) -> tuple[CustomFieldOption, ...]:
        if not isinstance(field_id, CustomFieldDefinitionId):
            raise TypeError("field_id must be CustomFieldDefinitionId")
        statement = select(CustomFieldOptionORM).where(CustomFieldOptionORM.field_id == field_id.value)
        if not include_inactive:
            statement = statement.where(CustomFieldOptionORM.active.is_(True))
        result = await self._session.execute(statement.order_by(CustomFieldOptionORM.sort_order.asc(), CustomFieldOptionORM.code.asc(), CustomFieldOptionORM.id.asc()))
        return tuple(custom_field_option_from_orm(model) for model in result.scalars().all())

    async def list_scopes(self, field_id: CustomFieldDefinitionId | None = None) -> tuple[CustomFieldScope, ...]:
        statement = select(CustomFieldScopeORM)
        if field_id is not None:
            if not isinstance(field_id, CustomFieldDefinitionId):
                raise TypeError("field_id must be CustomFieldDefinitionId or None")
            statement = statement.where(CustomFieldScopeORM.field_id == field_id.value)
        result = await self._session.execute(
            statement.order_by(
                CustomFieldScopeORM.field_id.asc(), CustomFieldScopeORM.exchange.asc(),
                CustomFieldScopeORM.market.asc(), CustomFieldScopeORM.strategy_code.asc(),
                CustomFieldScopeORM.setup_code.asc(), CustomFieldScopeORM.id.asc(),
            )
        )
        return tuple(custom_field_scope_from_orm(model) for model in result.scalars().all())

    async def save_definition(self, definition: CustomFieldDefinition) -> None:
        if not isinstance(definition, CustomFieldDefinition):
            raise TypeError("definition must be CustomFieldDefinition")
        result = await self._session.execute(select(CustomFieldDefinitionORM).where(CustomFieldDefinitionORM.id == definition.id.value))
        existing = result.scalar_one_or_none()
        if existing is None:
            self._session.add(custom_field_definition_to_orm(definition))
            await self._session.flush()
            return
        semantic = (
            existing.code, existing.name, existing.value_type, existing.source,
            existing.phase, existing.required, existing.definition_version,
        )
        candidate = (
            str(definition.code), definition.name, definition.value_type.value, definition.source.value,
            definition.phase.value, definition.required, definition.definition_version,
        )
        if semantic != candidate:
            raise CustomFieldSemanticMutationError("custom field semantic definition is immutable")
        existing.status = definition.status.value
        existing.required_for_statistics = definition.required_for_statistics
        await self._session.flush()

    async def update_definition_phase(self, field_id: CustomFieldDefinitionId, phase: CustomFieldPhase) -> None:
        """Update only the phase for a controlled built-in compatibility fix.

        The normal save path keeps catalog semantics immutable.  Bootstrap uses
        this narrow operation only for the five built-in manual fields whose
        historical phase was incorrectly persisted as POST_TRADE.
        """
        if not isinstance(field_id, CustomFieldDefinitionId):
            raise TypeError("field_id must be CustomFieldDefinitionId")
        if not isinstance(phase, CustomFieldPhase):
            raise TypeError("phase must be CustomFieldPhase")
        result = await self._session.execute(
            select(CustomFieldDefinitionORM).where(CustomFieldDefinitionORM.id == field_id.value)
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            raise ValueError(f"custom field not found: {field_id}")
        existing.phase = phase.value
        await self._session.flush()

    async def save_option(self, option: CustomFieldOption) -> None:
        if not isinstance(option, CustomFieldOption):
            raise TypeError("option must be CustomFieldOption")
        result = await self._session.execute(select(CustomFieldOptionORM).where(CustomFieldOptionORM.id == option.id.value))
        existing = result.scalar_one_or_none()
        if existing is None:
            self._session.add(custom_field_option_to_orm(option))
            await self._session.flush()
            return
        if existing.field_id != option.field_id.value:
            raise CustomFieldSemanticMutationError("custom field option cannot be reassigned to another field")
        if existing.code != option.code:
            raise CustomFieldSemanticMutationError("custom field option code is immutable")
        existing.label = option.label
        existing.sort_order = option.sort_order
        existing.active = option.active
        await self._session.flush()

    async def save_scope(self, scope: CustomFieldScope) -> None:
        if not isinstance(scope, CustomFieldScope):
            raise TypeError("scope must be CustomFieldScope")
        filters = [
            CustomFieldScopeORM.field_id == scope.field_id.value,
            CustomFieldScopeORM.exchange.is_(None) if scope.exchange is None else CustomFieldScopeORM.exchange == scope.exchange,
            CustomFieldScopeORM.market.is_(None) if scope.market is None else CustomFieldScopeORM.market == scope.market,
            CustomFieldScopeORM.strategy_code.is_(None) if scope.strategy_code is None else CustomFieldScopeORM.strategy_code == str(scope.strategy_code),
            CustomFieldScopeORM.setup_code.is_(None) if scope.setup_code is None else CustomFieldScopeORM.setup_code == str(scope.setup_code),
        ]
        result = await self._session.execute(select(CustomFieldScopeORM).where(and_(*filters)))
        if result.scalar_one_or_none() is not None:
            return
        self._session.add(custom_field_scope_to_orm(scope))
        await self._session.flush()
