"""Domain/ORM conversion for history-import state."""

from app.core.accounts.account_id import AccountId
from app.core.imports import ExchangeImportSettings, HistoricalImportMode, JournalTradeState, JournalTradeStateRecord
from app.core.trades.trade_id import TradeId

from ..models.history_import import ExchangeImportSettingsORM, TradeJournalStateORM


def import_settings_from_orm(model: ExchangeImportSettingsORM) -> ExchangeImportSettings:
    return ExchangeImportSettings(
        account_id=AccountId(model.account_id),
        exchange=model.exchange,
        history_available_from=model.history_available_from,
        tracking_start_at=model.tracking_start_at,
        initial_import_mode=HistoricalImportMode(model.initial_import_mode),
        initial_import_completed_at=model.initial_import_completed_at,
        last_sync_at=model.last_sync_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def import_settings_to_orm(settings: ExchangeImportSettings) -> ExchangeImportSettingsORM:
    return ExchangeImportSettingsORM(
        account_id=settings.account_id.value,
        exchange=settings.exchange,
        history_available_from=settings.history_available_from,
        tracking_start_at=settings.tracking_start_at,
        initial_import_mode=settings.initial_import_mode.value,
        initial_import_completed_at=settings.initial_import_completed_at,
        last_sync_at=settings.last_sync_at,
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


def journal_state_from_orm(model: TradeJournalStateORM) -> JournalTradeStateRecord:
    return JournalTradeStateRecord(
        trade_id=TradeId(model.trade_id),
        account_id=AccountId(model.account_id),
        state=JournalTradeState(model.state),
        reason=model.reason,
        excluded_at=model.excluded_at,
        updated_at=model.updated_at,
    )


def journal_state_to_orm(state: JournalTradeStateRecord) -> TradeJournalStateORM:
    return TradeJournalStateORM(
        trade_id=state.trade_id.value,
        account_id=state.account_id.value,
        state=state.state.value,
        reason=state.reason,
        excluded_at=state.excluded_at,
        updated_at=state.updated_at,
    )
