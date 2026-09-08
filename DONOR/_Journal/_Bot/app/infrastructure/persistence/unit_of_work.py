"""SQLAlchemy transaction owner for multi-repository ingestion."""

from app.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyCustomFieldRepository,
    SqlAlchemyExecutionRepository,
    SqlAlchemyInstrumentRepository,
    SqlAlchemyTradeCustomValueRepository,
    SqlAlchemyTradeRepository,
    SqlAlchemyExchangeImportSettingsRepository,
    SqlAlchemyTradeJournalStateRepository,
    SqlAlchemyAutomaticFactorObservationRepository,
)


class SqlAlchemyUnitOfWork:
    """Own one AsyncSession and all repositories participating in one transaction."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory
        self._session = None
        self._committed = False
        self.trades = None
        self.executions = None
        self.accounts = None
        self.instruments = None
        self.custom_fields = None
        self.custom_values = None
        self.exchange_import_settings = None
        self.trade_journal_state = None
        self.automatic_data = None

    async def __aenter__(self):
        self._session = self._session_factory()
        await self._session.begin()
        self.trades = SqlAlchemyTradeRepository(self._session)
        self.executions = SqlAlchemyExecutionRepository(self._session)
        self.accounts = SqlAlchemyAccountRepository(self._session)
        self.instruments = SqlAlchemyInstrumentRepository(self._session)
        self.custom_fields = SqlAlchemyCustomFieldRepository(self._session)
        self.custom_values = SqlAlchemyTradeCustomValueRepository(self._session)
        # Keep the lightweight fake-session contract used by repository unit
        # tests and local harnesses.  Real AsyncSession instances always expose
        # execute/flush and therefore receive both new repositories.
        if hasattr(self._session, "execute") and hasattr(self._session, "flush"):
            self.exchange_import_settings = SqlAlchemyExchangeImportSettingsRepository(self._session)
            self.trade_journal_state = SqlAlchemyTradeJournalStateRepository(self._session)
            self.automatic_data = SqlAlchemyAutomaticFactorObservationRepository(self._session)
        self._committed = False
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        try:
            if exc_type is not None or not self._committed:
                await self.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        await self._session.commit()
        self._committed = True

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()
