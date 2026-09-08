"""SQLAlchemy repositories for history settings and Journal inclusion state."""

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.application.ports.repositories import ExchangeImportSettingsRepository, TradeJournalStateRepository
from app.core.accounts.account_id import AccountId
from app.core.imports import ExchangeImportSettings, JournalTradeState, JournalTradeStateRecord
from app.core.trades.trade_id import TradeId

from ..mappers import import_settings_from_orm, import_settings_to_orm, journal_state_from_orm, journal_state_to_orm
from ..models.history_import import ExchangeImportSettingsORM, TradeJournalStateORM
from ._common import require_session


class SqlAlchemyExchangeImportSettingsRepository(ExchangeImportSettingsRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def get(self, *, account_id: AccountId, exchange: str):
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        model = await self._session.scalar(select(ExchangeImportSettingsORM).where(
            ExchangeImportSettingsORM.account_id == account_id.value,
            ExchangeImportSettingsORM.exchange == exchange.strip().upper(),
        ))
        return None if model is None else import_settings_from_orm(model)

    async def save(self, settings: ExchangeImportSettings) -> None:
        if not isinstance(settings, ExchangeImportSettings):
            raise TypeError("settings must be ExchangeImportSettings")
        existing = await self._session.scalar(select(ExchangeImportSettingsORM).where(
            ExchangeImportSettingsORM.account_id == settings.account_id.value,
            ExchangeImportSettingsORM.exchange == settings.exchange,
        ))
        candidate = import_settings_to_orm(settings)
        if existing is None:
            self._session.add(candidate)
        else:
            for name in ("history_available_from", "tracking_start_at", "initial_import_mode", "initial_import_completed_at", "last_sync_at", "updated_at"):
                setattr(existing, name, getattr(candidate, name))
        await self._session.flush()


class SqlAlchemyTradeJournalStateRepository(TradeJournalStateRepository):
    def __init__(self, session) -> None:
        self._session = require_session(session)

    async def get(self, trade_id: TradeId):
        if not isinstance(trade_id, TradeId):
            raise TypeError("trade_id must be TradeId")
        model = await self._session.scalar(select(TradeJournalStateORM).where(TradeJournalStateORM.trade_id == trade_id.value))
        return None if model is None else journal_state_from_orm(model)

    async def save(self, state: JournalTradeStateRecord) -> None:
        if not isinstance(state, JournalTradeStateRecord):
            raise TypeError("state must be JournalTradeStateRecord")
        existing = await self._session.scalar(select(TradeJournalStateORM).where(TradeJournalStateORM.trade_id == state.trade_id.value))
        candidate = journal_state_to_orm(state)
        if existing is None:
            self._session.add(candidate)
        else:
            for name in ("account_id", "state", "reason", "excluded_at", "updated_at"):
                setattr(existing, name, getattr(candidate, name))
        await self._session.flush()

    async def list(self, *, account_id: AccountId, state: JournalTradeState | None = None, limit: int = 100, offset: int = 0):
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        if limit < 1 or offset < 0:
            raise ValueError("invalid pagination")
        statement = select(TradeJournalStateORM).where(TradeJournalStateORM.account_id == account_id.value)
        if state is not None:
            state = JournalTradeState(state)
            statement = statement.where(TradeJournalStateORM.state == state.value)
        result = await self._session.execute(statement.order_by(TradeJournalStateORM.updated_at.desc(), TradeJournalStateORM.trade_id.desc()).offset(offset).limit(limit))
        return tuple(journal_state_from_orm(model) for model in result.scalars().all())

    async def count(self, *, account_id: AccountId, state: JournalTradeState | None = None) -> int:
        if not isinstance(account_id, AccountId):
            raise TypeError("account_id must be AccountId")
        statement = select(func.count()).select_from(TradeJournalStateORM).where(
            TradeJournalStateORM.account_id == account_id.value
        )
        if state is not None:
            statement = statement.where(TradeJournalStateORM.state == JournalTradeState(state).value)
        return int((await self._session.scalar(statement)) or 0)
