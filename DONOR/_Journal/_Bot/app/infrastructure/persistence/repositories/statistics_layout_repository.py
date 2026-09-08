from datetime import datetime, timezone

from sqlalchemy import select

from app.application.ports.repositories import StatisticsLayoutRepository
from app.application.statistics.metric_registry import StatisticsLayout
from app.core.accounts.account_id import AccountId
from app.infrastructure.persistence.mappers.statistics_layout_mapper import statistics_layout_from_orm, statistics_layout_to_orm
from app.infrastructure.persistence.models.statistics_layout import StatisticsLayoutORM

from ._common import require_session


class SqlAlchemyStatisticsLayoutRepository(StatisticsLayoutRepository):
    def __init__(self, session): self._session = require_session(session)

    async def get(self, account_id):
        if not isinstance(account_id, AccountId): raise TypeError("account_id must be AccountId")
        item = await self._session.scalar(select(StatisticsLayoutORM).where(StatisticsLayoutORM.account_id == account_id.value))
        return None if item is None else statistics_layout_from_orm(item)

    async def save(self, account_id, layout):
        if not isinstance(account_id, AccountId): raise TypeError("account_id must be AccountId")
        if not isinstance(layout, StatisticsLayout): raise TypeError("layout must be StatisticsLayout")
        existing = await self._session.scalar(select(StatisticsLayoutORM).where(StatisticsLayoutORM.account_id == account_id.value))
        candidate = statistics_layout_to_orm(account_id, layout)
        if existing is None: self._session.add(candidate)
        else:
            existing.overview_metric_ids = candidate.overview_metric_ids
            existing.home_metric_ids = candidate.home_metric_ids
            existing.home_metric_period = candidate.home_metric_period
            existing.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
