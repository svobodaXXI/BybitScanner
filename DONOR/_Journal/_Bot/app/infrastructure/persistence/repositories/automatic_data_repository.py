"""SQLAlchemy adapters for generic automatic data."""

from datetime import datetime, timezone

from sqlalchemy import select

from app.application.ports.repositories import AutomaticFactorObservationRepository, AutomaticFactorSettingsRepository
from app.core.accounts.account_id import AccountId
from app.infrastructure.persistence.models.automatic_data import AutomaticFactorObservationORM, AutomaticFactorSettingORM
from app.infrastructure.persistence.mappers import automatic_observation_from_orm, automatic_observation_to_orm

from ._common import require_session


class SqlAlchemyAutomaticFactorObservationRepository(AutomaticFactorObservationRepository):
    def __init__(self, session): self._session = require_session(session)

    async def save(self, observation):
        existing = await self._session.scalar(select(AutomaticFactorObservationORM).where(
            AutomaticFactorObservationORM.trade_id == observation.trade_id.value,
            AutomaticFactorObservationORM.factor_id == observation.factor_id,
            AutomaticFactorObservationORM.definition_version == observation.definition_version,
            AutomaticFactorObservationORM.calculation_version == observation.calculation_version,
            AutomaticFactorObservationORM.capture_semantics == observation.capture_semantics,
        ))
        if existing is not None:
            # A missing source observation may be repaired by a later import;
            # valid historical data is immutable for its versioned identity.
            if existing.value_decimal is None and existing.value_integer is None and existing.value_boolean is None and existing.value_text is None and observation.value is not None:
                replacement = automatic_observation_to_orm(observation)
                for name in (
                    "value_type", "value_decimal", "value_integer", "value_boolean", "value_text",
                    "unit", "currency", "source_kind", "provider_key", "captured_at", "source_timestamp",
                    "quality_status", "availability_status", "provenance",
                ):
                    setattr(existing, name, getattr(replacement, name))
                await self._session.flush()
            return
        self._session.add(automatic_observation_to_orm(observation))
        await self._session.flush()

    async def list_for_trade(self, trade_id):
        result = await self._session.scalars(select(AutomaticFactorObservationORM).where(AutomaticFactorObservationORM.trade_id == trade_id.value))
        return tuple(automatic_observation_from_orm(item) for item in result)

    async def list(self, factor_id, trade_ids=()):
        statement = select(AutomaticFactorObservationORM).where(AutomaticFactorObservationORM.factor_id == factor_id)
        ids = tuple(trade_ids)
        if ids:
            statement = statement.where(AutomaticFactorObservationORM.trade_id.in_([item.value for item in ids]))
        result = await self._session.scalars(statement)
        return tuple(automatic_observation_from_orm(item) for item in result)


class SqlAlchemyAutomaticFactorSettingsRepository(AutomaticFactorSettingsRepository):
    def __init__(self, session): self._session = require_session(session)

    async def list(self, account_id):
        if not isinstance(account_id, AccountId): raise TypeError("account_id must be AccountId")
        result = await self._session.scalars(select(AutomaticFactorSettingORM).where(AutomaticFactorSettingORM.account_id == account_id.value))
        return {item.factor_id: item.enabled for item in result}

    async def set_enabled(self, account_id, factor_id, enabled):
        if not isinstance(account_id, AccountId): raise TypeError("account_id must be AccountId")
        if not isinstance(factor_id, str) or not factor_id.strip(): raise ValueError("factor_id must be non-empty")
        existing = await self._session.scalar(select(AutomaticFactorSettingORM).where(AutomaticFactorSettingORM.account_id == account_id.value, AutomaticFactorSettingORM.factor_id == factor_id))
        if existing is None:
            self._session.add(AutomaticFactorSettingORM(account_id=account_id.value, factor_id=factor_id, enabled=bool(enabled), updated_at=datetime.now(timezone.utc)))
        else:
            existing.enabled = bool(enabled)
            existing.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
