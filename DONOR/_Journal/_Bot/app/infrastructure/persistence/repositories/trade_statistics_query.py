"""SQLAlchemy bulk read adapter for Statistics Engine V1."""

from dataclasses import replace

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.application.ports import TradeStatisticsQuery
from app.application.errors import PersistenceIntegrityError
from app.application.statistics import DynamicFieldMetadata, StatisticsFilter, StatisticsTradeRecord
from app.core.statistics.enums import CustomFieldPhase
from app.core.statistics.resolution_context import CustomFieldResolutionContext
from app.core.trades.enums import TradeStatus
from app.core.trades.enums import TradePnLSource
from app.core.trades.execution_replay import validate_execution_replay

from ..mappers import (
    custom_field_definition_from_orm,
    custom_field_option_from_orm,
    custom_field_scope_from_orm,
    trade_custom_value_from_orm,
    trade_from_orm,
    execution_from_orm,
)
from ..models.custom_fields import CustomFieldDefinitionORM, CustomFieldOptionORM, CustomFieldScopeORM
from ..models.instrument import InstrumentORM
from ..models.trade import TradeORM
from ..models.execution import ExecutionORM
from ..models.trade_custom_value import TradeCustomValueORM
from ..models.history_import import TradeJournalStateORM
from ._common import require_session


class SqlAlchemyTradeStatisticsQuery(TradeStatisticsQuery):
    """Bulk-load only Trade snapshots and dynamic values; never writes."""

    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def count_current_open(self, *, account_id=None, instrument_id=None) -> int:
        """Count current INCLUDED OPEN positions without a period filter."""
        statement = select(func.count()).select_from(TradeORM).where(
            TradeORM.status == TradeStatus.OPEN.value,
            ~select(TradeJournalStateORM.trade_id).where(
                TradeJournalStateORM.trade_id == TradeORM.id,
                TradeJournalStateORM.state != "INCLUDED",
            ).exists(),
        )
        if account_id is not None:
            statement = statement.where(TradeORM.account_id == account_id.value)
        if instrument_id is not None:
            statement = statement.where(TradeORM.instrument_id == instrument_id.value)
        return int((await self._session.scalar(statement)) or 0)

    async def list_trades(self, filters: StatisticsFilter) -> tuple[StatisticsTradeRecord, ...]:
        if not isinstance(filters, StatisticsFilter):
            raise TypeError("filters must be StatisticsFilter")
        statement = (
            select(TradeORM, InstrumentORM)
            .outerjoin(InstrumentORM, InstrumentORM.id == TradeORM.instrument_id)
            .options(selectinload(TradeORM.expenses))
        )
        statement = statement.where(~select(TradeJournalStateORM.trade_id).where(
            TradeJournalStateORM.trade_id == TradeORM.id,
            TradeJournalStateORM.state != "INCLUDED",
        ).exists())
        if filters.account_id is not None:
            statement = statement.where(TradeORM.account_id == filters.account_id.value)
        if filters.instrument_id is not None:
            statement = statement.where(TradeORM.instrument_id == filters.instrument_id.value)
        if filters.direction is not None:
            statement = statement.where(TradeORM.direction == filters.direction.value)
        if filters.status is not None:
            statement = statement.where(TradeORM.status == filters.status.value)
        filter_time = (
            TradeORM.closed_at
            if filters.status is TradeStatus.CLOSED
            else func.coalesce(TradeORM.closed_at, TradeORM.opened_at)
        )
        if filters.from_at is not None:
            statement = statement.where(filter_time >= filters.from_at)
        if filters.to_at is not None:
            statement = statement.where(filter_time < filters.to_at)
        statement = statement.order_by(filter_time.asc(), TradeORM.id.asc())
        result = await self._session.execute(statement)
        records = []
        for trade_model, instrument_model in result.all():
            trade = trade_from_orm(trade_model)
            if trade.pnl_source is TradePnLSource.EXECUTION_REPLAY:
                execution_result = await self._session.execute(
                    select(ExecutionORM)
                    .where(ExecutionORM.trade_id == trade_model.id)
                    .order_by(ExecutionORM.executed_at.asc(), ExecutionORM.id.asc())
                )
                try:
                    validate_execution_replay(
                        trade,
                        tuple(execution_from_orm(item) for item in execution_result.scalars().all()),
                    )
                except (TypeError, ValueError) as error:
                    raise PersistenceIntegrityError("persisted Trade violates execution replay integrity") from error
            record = StatisticsTradeRecord.from_trade(trade)
            if instrument_model is not None:
                record = replace(
                    record,
                    instrument_label=instrument_model.symbol,
                    resolution_context=CustomFieldResolutionContext(
                        phase=(
                            CustomFieldPhase.POST_TRADE
                            if trade.status is TradeStatus.CLOSED
                            else CustomFieldPhase.OPEN
                        ),
                        exchange=instrument_model.exchange,
                        market=instrument_model.market,
                    ),
                    instrument_available=True,
                )
            else:
                record = replace(record, instrument_available=False)
            records.append(record)
        return tuple(records)

    async def get_dynamic_field(self, *, field_id=None, field_code=None):
        if field_id is None and field_code is None:
            raise ValueError("field_id or field_code is required")
        statement = select(CustomFieldDefinitionORM)
        if field_id is not None:
            statement = statement.where(CustomFieldDefinitionORM.id == field_id.value)
        else:
            statement = statement.where(CustomFieldDefinitionORM.code == field_code.strip().lower())
        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()
        if model is None:
            return None
        definition = custom_field_definition_from_orm(model)
        options_result = await self._session.execute(
            select(CustomFieldOptionORM)
            .where(CustomFieldOptionORM.field_id == definition.id.value)
            .order_by(CustomFieldOptionORM.sort_order.asc(), CustomFieldOptionORM.id.asc())
        )
        scopes_result = await self._session.execute(
            select(CustomFieldScopeORM)
            .where(CustomFieldScopeORM.field_id == definition.id.value)
            .order_by(CustomFieldScopeORM.id.asc())
        )
        return DynamicFieldMetadata(
            definition=definition,
            scopes=tuple(custom_field_scope_from_orm(item) for item in scopes_result.scalars().all()),
            options=tuple(custom_field_option_from_orm(item) for item in options_result.scalars().all()),
        )

    async def list_custom_values(self, trade_ids, field_id):
        if not trade_ids:
            return ()
        statement = (
            select(TradeCustomValueORM)
            .where(
                TradeCustomValueORM.trade_id.in_([trade_id.value for trade_id in trade_ids]),
                TradeCustomValueORM.field_id == field_id.value,
            )
            .order_by(TradeCustomValueORM.trade_id.asc(), TradeCustomValueORM.recorded_at.asc())
        )
        result = await self._session.execute(statement)
        return tuple(trade_custom_value_from_orm(model) for model in result.scalars().all())

    async def list_required_statistics_fields(self):
        """Bulk-load active dynamic fields that gate general statistics."""
        result = await self._session.execute(
            select(CustomFieldDefinitionORM)
            .where(
                CustomFieldDefinitionORM.status == "ACTIVE",
                CustomFieldDefinitionORM.required_for_statistics.is_(True),
            )
            .order_by(CustomFieldDefinitionORM.code.asc(), CustomFieldDefinitionORM.id.asc())
        )
        fields = []
        for model in result.scalars().all():
            definition = custom_field_definition_from_orm(model)
            options_result = await self._session.execute(
                select(CustomFieldOptionORM).where(CustomFieldOptionORM.field_id == definition.id.value)
            )
            scopes_result = await self._session.execute(
                select(CustomFieldScopeORM).where(CustomFieldScopeORM.field_id == definition.id.value)
            )
            fields.append(DynamicFieldMetadata(
                definition=definition,
                scopes=tuple(custom_field_scope_from_orm(item) for item in scopes_result.scalars().all()),
                options=tuple(custom_field_option_from_orm(item) for item in options_result.scalars().all()),
            ))
        return tuple(fields)
