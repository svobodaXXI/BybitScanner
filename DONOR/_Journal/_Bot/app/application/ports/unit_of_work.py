"""Application-facing transaction boundary."""

from typing import Protocol, runtime_checkable

from .repositories import (
    AccountRepository,
    CustomFieldRepository,
    ExecutionRepository,
    InstrumentRepository,
    TradeCustomValueRepository,
    TradeRepository,
    ExchangeImportSettingsRepository,
    TradeJournalStateRepository,
    AutomaticFactorObservationRepository,
)


@runtime_checkable
class UnitOfWork(Protocol):
    trades: TradeRepository
    executions: ExecutionRepository
    accounts: AccountRepository
    instruments: InstrumentRepository
    custom_fields: CustomFieldRepository
    custom_values: TradeCustomValueRepository
    exchange_import_settings: ExchangeImportSettingsRepository
    trade_journal_state: TradeJournalStateRepository
    automatic_data: AutomaticFactorObservationRepository

    async def __aenter__(self) -> "UnitOfWork":
        ...

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        ...

    async def commit(self) -> None:
        ...

    async def rollback(self) -> None:
        ...
