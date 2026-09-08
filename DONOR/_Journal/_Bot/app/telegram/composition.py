"""Composition boundary: one session/transaction per application operation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from typing import Any
import logging

from app.application import (
    AddExpense,
    BootstrapStatisticalFields,
    GetAttentionCenter,
    UpdateCustomFieldStatisticsRequirement,
    AddFee,
    AddManualCustomValue,
    CloseManualTrade,
    UpdateTradeProtection,
    CreateManualTrade,
    EnrichTrade,
    GetTradeDetails,
    ListAllTrades,
    ListOpenTrades,
    SearchInstruments,
    SearchInstrumentsCommand,
    TradeView,
    DiscoverSupportedBybitHistory,
    HistoricalImportSelection,
    ImportHistoricalBybit,
    PreviewHistoricalImport,
    ExcludeImportedTrade,
    RestoreExcludedTrade,
    PreviewBulkExcludeOldIncomplete,
    ApplyBulkExclusion,
    PreviewTrackingStartChange,
    ApplyTrackingStartChange,
    IncrementalBybitSync,
)
from app.application.dtos import MiniAppTradePage, MiniAppTradeRow
from app.application.statistics import (
    DynamicFieldCoverageRequest,
    GroupedPerformanceRequest,
    StatisticsEngine,
    StatisticsFilter,
    DEFAULT_STATISTICS_METRIC_REGISTRY,
    StatisticsLayout,
    metric_value,
)
from app.application.statistics.metric_registry import HomeMetricPeriod
from app.core.accounts.account_id import AccountId
from app.core.imports import BybitHistorySnapshot, ExchangeImportSettings, HistoricalImportMode
from app.core.automatic_data import DEFAULT_AUTOMATIC_FACTOR_REGISTRY
from app.core.statistics import CustomFieldDefinition, CustomFieldOption
from app.core.statistics.enums import CustomFieldPhase, CustomFieldSource, CustomFieldStatus, CustomFieldValueType
from app.core.statistics.ids import CustomFieldDefinitionId
from app.application.dtos import (
    AddExpenseCommand,
    AddFeeCommand,
    AddManualCustomValueCommand,
    CloseManualTradeCommand,
    CreateManualTradeCommand,
    EnrichTradeCommand,
    GetTradeDetailsCommand,
    UpdateTradeProtectionCommand,
    ListAllTradesCommand,
    ListOpenTradesCommand,
    InstrumentView,
)
from app.application.ports.repositories import (
    AccountRepository,
    CustomFieldRepository,
    TradeCustomValueRepository,
    TradeRepository,
)
from app.infrastructure.persistence.database import create_async_engine, create_session_factory
from app.infrastructure.persistence.repositories import (
    SqlAlchemyAccountRepository,
    SqlAlchemyCustomFieldRepository,
    SqlAlchemyTradeCustomValueRepository,
    SqlAlchemyExecutionRepository,
    SqlAlchemyTradeRepository,
    SqlAlchemyInstrumentRepository,
    SqlAlchemyTradeStatisticsQuery,
    SqlAlchemyReminderSettingsRepository,
    SqlAlchemyAutomaticFactorSettingsRepository,
    SqlAlchemyStatisticsLayoutRepository,
    SqlAlchemyExchangeImportSettingsRepository,
    SqlAlchemyTradeJournalStateRepository,
    SqlAlchemyAutomaticFactorObservationRepository,
)
from app.infrastructure.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.exchanges.bybit.config import BybitSettings
from app.infrastructure.exchanges.bybit.execution_source import BybitExecutionSource
from app.application.automatic_market_data import AutomaticTradeDataCapture
from app.application.use_cases.process_execution_and_update_trade import ProcessExecutionAndUpdateTrade
from app.application.errors import HistoricalPreviewError

logger = logging.getLogger(__name__)


def _safe_preview_detail(error: Exception) -> str:
    detail = " ".join(str(error).split())
    return detail[:500] if detail else type(error).__name__


class JournalApplication:
    """Explicit application facade; it never retains an AsyncSession."""

    def __init__(self, session_factory, default_account_id=None, bybit_settings=None, entry_timezone=None) -> None:
        self._session_factory = session_factory
        self.default_account_id = default_account_id
        self._bybit_settings = bybit_settings
        self._entry_timezone = entry_timezone
        self._bybit_snapshots: dict[AccountId, BybitHistorySnapshot] = {}
        self._bybit_snapshot_ttl_seconds = 8 * 60

    async def _transaction(self, operation: Callable[[Any], Awaitable[Any]]) -> Any:
        async with self._session_factory() as session:
            async with session.begin():
                return await operation(session)

    async def _read(self, operation: Callable[[Any], Awaitable[Any]]) -> Any:
        """Run a read without committing a write transaction."""
        async with self._session_factory() as session:
            return await operation(session)

    @staticmethod
    def _trade_repositories(session) -> tuple[TradeRepository, AccountRepository]:
        return SqlAlchemyTradeRepository(session), SqlAlchemyAccountRepository(session)

    async def create_manual_trade(self, command: CreateManualTradeCommand):
        async def operation(session):
            trades, accounts = self._trade_repositories(session)
            return await CreateManualTrade(
                accounts, trades, SqlAlchemyAutomaticFactorObservationRepository(session),
                automatic_capture=AutomaticTradeDataCapture(entry_timezone=self._entry_timezone),
            ).execute(command)
        return await self._transaction(operation)

    async def close_manual_trade(self, command: CloseManualTradeCommand):
        async def operation(session):
            return await CloseManualTrade(
                SqlAlchemyTradeRepository(session), SqlAlchemyAutomaticFactorObservationRepository(session),
                automatic_capture=AutomaticTradeDataCapture(entry_timezone=self._entry_timezone),
            ).execute(command)
        return await self._transaction(operation)

    async def update_trade_protection(self, command: UpdateTradeProtectionCommand):
        async def operation(session):
            return await UpdateTradeProtection(SqlAlchemyTradeRepository(session)).execute(command)
        return await self._transaction(operation)

    async def add_fee(self, command: AddFeeCommand):
        async def operation(session):
            return await AddFee(SqlAlchemyTradeRepository(session)).execute(command)
        return await self._transaction(operation)

    async def add_expense(self, command: AddExpenseCommand):
        async def operation(session):
            return await AddExpense(SqlAlchemyTradeRepository(session)).execute(command)
        return await self._transaction(operation)

    async def add_manual_custom_value(self, command: AddManualCustomValueCommand):
        async def operation(session):
            return await AddManualCustomValue(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
            ).execute(command)
        return await self._transaction(operation)

    async def upsert_manual_custom_value(self, command: AddManualCustomValueCommand):
        async def operation(session):
            return await AddManualCustomValue(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
                allow_update=True,
            ).execute(command)
        return await self._transaction(operation)

    async def enrich_trade(self, command: EnrichTradeCommand):
        async def operation(session):
            return await EnrichTrade(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
            ).execute(command)
        return await self._transaction(operation)

    async def list_open_trades(self, command: ListOpenTradesCommand | None = None):
        async def operation(session):
            return await ListOpenTrades(SqlAlchemyTradeRepository(session)).execute(command)
        return await self._transaction(operation)

    async def list_all_trades(self, command: ListAllTradesCommand | None = None):
        async def operation(session):
            return await ListAllTrades(SqlAlchemyTradeRepository(session)).execute(command)
        return await self._transaction(operation)

    async def get_trade_details(self, command: GetTradeDetailsCommand):
        async def operation(session):
            return await GetTradeDetails(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
                SqlAlchemyInstrumentRepository(session),
                SqlAlchemyExecutionRepository(session),
                SqlAlchemyTradeJournalStateRepository(session),
                SqlAlchemyAutomaticFactorObservationRepository(session),
            ).execute(command)
        return await self._transaction(operation)

    async def search_instruments(self, command: SearchInstrumentsCommand):
        async def operation(session):
            result = await SearchInstruments(SqlAlchemyInstrumentRepository(session)).execute(command)
            return tuple(InstrumentView.from_instrument(item) for item in result.instruments)
        return await self._transaction(operation)

    async def get_instrument(self, instrument_id):
        async def operation(session):
            instrument = await SqlAlchemyInstrumentRepository(session).get_by_id(instrument_id)
            return None if instrument is None else InstrumentView.from_instrument(instrument)
        return await self._transaction(operation)

    async def list_active_accounts(self):
        async def operation(session):
            return await SqlAlchemyAccountRepository(session).list_active()
        return await self._read(operation)

    async def get_custom_field(self, field_id):
        async def operation(session):
            return await SqlAlchemyCustomFieldRepository(session).get_definition(field_id)
        return await self._transaction(operation)

    async def list_custom_field_options(self, field_id, *, include_inactive: bool = False):
        async def operation(session):
            return await SqlAlchemyCustomFieldRepository(session).list_options(field_id, include_inactive=include_inactive)
        return await self._transaction(operation)

    async def list_custom_fields(self):
        """Telegram-facing read model for the configured custom-field catalog."""
        return await self._read(
            lambda session: SqlAlchemyCustomFieldRepository(session).list_definitions(include_inactive=True)
        )

    async def bootstrap_statistical_fields(self):
        async def operation(session):
            return await BootstrapStatisticalFields(SqlAlchemyCustomFieldRepository(session)).execute()
        return await self._transaction(operation)

    async def create_custom_field(self, *, code: str, name: str, value_type: CustomFieldValueType):
        definition = CustomFieldDefinition.create(
            code,
            name,
            value_type,
            CustomFieldSource.MANUAL,
            phase=CustomFieldPhase.POST_TRADE,
        )
        async def operation(session):
            await SqlAlchemyCustomFieldRepository(session).save_definition(definition)
            return definition
        return await self._transaction(operation)

    async def set_custom_field_active(self, field_id, active: bool):
        field_id = field_id if isinstance(field_id, CustomFieldDefinitionId) else CustomFieldDefinitionId(field_id)
        async def operation(session):
            repository = SqlAlchemyCustomFieldRepository(session)
            definition = await repository.get_definition(field_id)
            if definition is None:
                raise ValueError("custom field was not found")
            updated = replace(definition, status=CustomFieldStatus.ACTIVE if active else CustomFieldStatus.INACTIVE)
            await repository.save_definition(updated)
            return updated
        return await self._transaction(operation)

    async def save_custom_field_option(self, option: CustomFieldOption):
        async def operation(session):
            await SqlAlchemyCustomFieldRepository(session).save_option(option)
            return option
        return await self._transaction(operation)

    async def miniapp_dashboard(self, filters: StatisticsFilter):
        async def operation(session):
            return await StatisticsEngine(SqlAlchemyTradeStatisticsQuery(session)).get_performance_summary(filters)
        return await self._read(operation)

    async def statistics_summary(self, filters: StatisticsFilter):
        """Telegram-facing statistics entry point kept independent of Mini App naming."""
        return await self.miniapp_dashboard(filters)

    async def miniapp_statistics_groups(self, request: GroupedPerformanceRequest):
        async def operation(session):
            return await StatisticsEngine(SqlAlchemyTradeStatisticsQuery(session)).get_grouped_performance(request)
        return await self._read(operation)

    async def miniapp_dynamic_field_coverage(self, request: DynamicFieldCoverageRequest):
        async def operation(session):
            return await StatisticsEngine(SqlAlchemyTradeStatisticsQuery(session)).get_dynamic_field_coverage(request)
        return await self._read(operation)

    async def miniapp_metric_coverage(self, metric: str, filters: StatisticsFilter):
        async def operation(session):
            return await StatisticsEngine(SqlAlchemyTradeStatisticsQuery(session)).get_metric_coverage(metric, filters)
        return await self._read(operation)

    async def miniapp_list_trades(self, filters: StatisticsFilter, *, limit: int, offset: int) -> MiniAppTradePage:
        if not isinstance(filters, StatisticsFilter):
            raise TypeError("filters must be StatisticsFilter")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer between 1 and 100")
        if type(offset) is not int or offset < 0:
            raise ValueError("offset must be an integer >= 0")

        async def operation(session):
            trades = await SqlAlchemyTradeRepository(session).list_all(
                account_id=filters.account_id,
                instrument_id=filters.instrument_id,
                limit=limit + 1,
                offset=offset,
                direction=filters.direction,
                status=filters.status,
                from_at=filters.from_at,
                to_at=filters.to_at,
            )
            has_more = len(trades) > limit
            page = trades[:limit]
            instruments = await SqlAlchemyInstrumentRepository(session).get_by_ids(
                tuple(trade.instrument_id for trade in page)
            )
            by_id = {item.instrument_id: item for item in instruments}
            return MiniAppTradePage(
                items=tuple(
                    MiniAppTradeRow(
                        TradeView.from_trade(trade),
                        None if trade.instrument_id not in by_id else InstrumentView.from_instrument(by_id[trade.instrument_id]),
                    )
                    for trade in page
                ),
                limit=limit,
                offset=offset,
                has_more=has_more,
            )
        return await self._read(operation)

    async def miniapp_trade_details(self, command: GetTradeDetailsCommand):
        async def operation(session):
            return await GetTradeDetails(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
                SqlAlchemyInstrumentRepository(session),
                SqlAlchemyExecutionRepository(session),
                SqlAlchemyTradeJournalStateRepository(session),
                SqlAlchemyAutomaticFactorObservationRepository(session),
            ).execute(command)
        return await self._read(operation)

    async def miniapp_dynamic_fields(self):
        async def operation(session):
            return await SqlAlchemyCustomFieldRepository(session).list_definitions(include_inactive=True)
        return await self._read(operation)

    async def miniapp_attention(self, *, account_id=None, instrument_id=None):
        account = None if account_id is None else self._account_id(account_id)

        async def operation(session):
            return await GetAttentionCenter(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
                SqlAlchemyInstrumentRepository(session),
            ).execute(account_id=account, instrument_id=instrument_id)
        return await self._read(operation)

    async def attention(self, *, account_id=None, instrument_id=None):
        """Telegram-facing Attention Center entry point."""
        return await self.miniapp_attention(account_id=account_id, instrument_id=instrument_id)

    async def incomplete_attention_count(self, *, account_id=None) -> int:
        """Count only CLOSED trades still incomplete for the reminder digest."""
        result = await self.attention(account_id=account_id)
        return result.summary.incomplete_count

    async def set_custom_field_required_for_statistics(self, field_id, required_for_statistics: bool):
        async def operation(session):
            return await UpdateCustomFieldStatisticsRequirement(
                SqlAlchemyCustomFieldRepository(session)
            ).execute(field_id, required_for_statistics)
        return await self._transaction(operation)

    async def get_reminder_settings(self, account_id):
        async def operation(session):
            return await SqlAlchemyReminderSettingsRepository(session).get(account_id)
        return await self._read(operation)

    async def save_reminder_settings(self, settings):
        async def operation(session):
            return await SqlAlchemyReminderSettingsRepository(session).save(settings)
        return await self._transaction(operation)

    async def get_exchange_import_settings(self, account_id=None, exchange="BYBIT"):
        account = self._account_id(account_id)
        return await self._read(lambda session: SqlAlchemyExchangeImportSettingsRepository(session).get(account_id=account, exchange=exchange))

    async def sync_bybit_incremental(self, *, overlap_seconds=60, now=None):
        """Fetch and apply only the durable incremental Bybit boundary."""
        account = self._account_id()
        async def operation(session):
            bybit_settings = replace(self._bybit_settings_or_env(), account_id=account)
            source = BybitExecutionSource(bybit_settings, SqlAlchemyInstrumentRepository(session))
            processor = ProcessExecutionAndUpdateTrade(
                lambda: SqlAlchemyUnitOfWork(self._session_factory),
                automatic_data_provider=source.market_data_provider,
                entry_timezone=self._entry_timezone,
            )
            return await IncrementalBybitSync(
                source, processor, SqlAlchemyExchangeImportSettingsRepository(session),
                account_id=account, overlap_seconds=overlap_seconds,
            ).execute(now=now)
        return await self._transaction(operation)

    def _bybit_settings_or_env(self):
        if self._bybit_settings is not None:
            return self._bybit_settings
        return BybitSettings.from_env()

    @property
    def bybit_history_lookback_start(self):
        return self._bybit_settings_or_env().history_lookback_start

    async def discover_bybit_history(self, *, lookback_start, lookback_end=None, force_refresh=False, progress_callback=None):
        account = self._account_id()
        async def operation(session):
            source = BybitExecutionSource(replace(self._bybit_settings_or_env(), account_id=account), SqlAlchemyInstrumentRepository(session))
            return await DiscoverSupportedBybitHistory(
                source, SqlAlchemyExchangeImportSettingsRepository(session)
            ).execute(lookback_start=lookback_start, lookback_end=lookback_end,
                      force_refresh=force_refresh, progress_callback=progress_callback)
        return await self._transaction(operation)

    async def preview_bybit_import(self, selection: HistoricalImportSelection, *, progress_callback=None):
        if not isinstance(selection, HistoricalImportSelection):
            raise TypeError("selection must be HistoricalImportSelection")
        async def operation(session):
            source = BybitExecutionSource(replace(self._bybit_settings_or_env(), account_id=self._account_id()), SqlAlchemyInstrumentRepository(session))
            facts = None
            if selection.selected_start < selection.selected_end:
                facts = await self._bybit_history_facts(source, selection, progress_callback=progress_callback)
            return await PreviewHistoricalImport(
                source,
                SqlAlchemyExecutionRepository(session),
                SqlAlchemyInstrumentRepository(session),
            ).execute(selection, facts=facts, progress_callback=progress_callback)
        return await self._read(operation)

    async def _bybit_history_facts(self, source, selection, *, progress_callback=None):
        """Load a short-lived raw snapshot and normalize it through Bybit's adapter."""
        account = self._account_id()
        now = datetime.now(timezone.utc)
        snapshot = self._bybit_snapshots.get(account)
        fresh = snapshot is not None and now - snapshot.created_at <= timedelta(seconds=self._bybit_snapshot_ttl_seconds)
        requested_from = selection.supported_history_from
        requested_to = selection.selected_end
        raw_rows = list(snapshot.raw_executions) if fresh else []
        coverage_from = snapshot.fetched_from if fresh else requested_from
        coverage_to = snapshot.fetched_to if fresh else requested_to
        ranges = []
        if not fresh:
            ranges.append((requested_from, requested_to))
        else:
            if requested_from < snapshot.fetched_from:
                ranges.append((requested_from, snapshot.fetched_from - timedelta(milliseconds=1)))
                coverage_from = requested_from
            if requested_to > snapshot.fetched_to:
                ranges.append((snapshot.fetched_to + timedelta(milliseconds=1), requested_to))
                coverage_to = requested_to
        for range_start, range_end in ranges:
            if range_start >= range_end:
                continue
            kwargs = {"start_at": range_start, "end_at": range_end}
            if progress_callback is not None:
                kwargs["progress_callback"] = progress_callback
            try:
                try:
                    chunk = await source.fetch_raw_historical_executions(**kwargs)
                except TypeError as error:
                    if progress_callback is None or "progress_callback" not in str(error):
                        raise
                    chunk = await source.fetch_raw_historical_executions(start_at=range_start, end_at=range_end)
            except Exception as error:
                logger.exception(
                    "Historical preview failed stage=FETCH_RAW account_id=%s selected_start=%s selected_end=%s "
                    "history_available_from=%s raw_execution_count=%s normalized_execution_count=%s "
                    "symbol_count=%s snapshot_used=%s exception_type=%s exception_message=%s",
                    account, selection.selected_start, selection.selected_end,
                    selection.supported_history_from, len(raw_rows), None,
                    len({row.get("symbol") for row in raw_rows if isinstance(row, dict) and isinstance(row.get("symbol"), str)}),
                    fresh, type(error).__name__, _safe_preview_detail(error),
                )
                raise HistoricalPreviewError("FETCH_RAW", "HISTORICAL_FETCH", _safe_preview_detail(error)) from error
            raw_rows.extend(chunk)
        if coverage_from > requested_from or coverage_to < requested_to:
            detail = (
                "raw history snapshot coverage is incomplete: "
                f"fetched_from={coverage_from.isoformat()} fetched_to={coverage_to.isoformat()}"
            )
            logger.error(
                "Historical preview failed stage=FETCH_RAW account_id=%s selected_start=%s "
                "selected_end=%s history_available_from=%s snapshot_used=%s detail=%s",
                account, selection.selected_start, selection.selected_end,
                selection.supported_history_from, fresh, detail,
            )
            raise HistoricalPreviewError("FETCH_RAW", "HISTORICAL_FETCH", detail)
        if ranges or not fresh:
            unique = {}
            for row in raw_rows:
                key = (str(row.get("execTime")), str(row.get("execId", "")))
                unique[key] = row
            raw_rows = sorted(unique.values(), key=lambda row: (str(row.get("execTime", "")), str(row.get("execId", ""))))
            fetched_from = min([requested_from, *(item[0] for item in ranges)])
            fetched_to = max([requested_to, *(item[1] for item in ranges)])
            if fetched_from < fetched_to:
                self._bybit_snapshots[account] = BybitHistorySnapshot(
                    account, fetched_from, fetched_to, now, tuple(raw_rows)
                )
        try:
            return await source.normalize_raw_historical_executions(raw_rows)
        except Exception as error:
            logger.exception(
                "Historical preview failed stage=NORMALIZE account_id=%s selected_start=%s selected_end=%s "
                "history_available_from=%s raw_execution_count=%s normalized_execution_count=%s "
                "symbol_count=%s snapshot_used=%s exception_type=%s exception_message=%s",
                account, selection.selected_start, selection.selected_end,
                selection.supported_history_from, len(raw_rows), None,
                len({row.get("symbol") for row in raw_rows if isinstance(row, dict) and isinstance(row.get("symbol"), str)}),
                fresh, type(error).__name__, _safe_preview_detail(error),
            )
            raise HistoricalPreviewError("NORMALIZE", "HISTORICAL_NORMALIZATION", _safe_preview_detail(error)) from error

    async def import_bybit_plan(self, plan, *, confirm_token):
        async def operation(session):
            source = BybitExecutionSource(
                replace(self._bybit_settings_or_env(), account_id=self._account_id()),
                SqlAlchemyInstrumentRepository(session),
            )
            processor = ProcessExecutionAndUpdateTrade(
                lambda: SqlAlchemyUnitOfWork(self._session_factory),
                automatic_data_provider=source.market_data_provider,
                entry_timezone=self._entry_timezone,
            )
            result = await ImportHistoricalBybit(
                processor, SqlAlchemyTradeJournalStateRepository(session)
            ).execute(plan, confirm_token=confirm_token)
            if not result.errors and plan.executions:
                account = plan.executions[0].account_id
                repository = SqlAlchemyExchangeImportSettingsRepository(session)
                current = await repository.get(account_id=account, exchange="BYBIT")
                if current is None:
                    current = ExchangeImportSettings(
                        account_id=account,
                        exchange="BYBIT",
                        history_available_from=plan.supported_history_from,
                        tracking_start_at=plan.selected_start,
                        initial_import_mode=plan.mode,
                        initial_import_completed_at=datetime.now(timezone.utc),
                        last_sync_at=datetime.now(timezone.utc),
                    )
                else:
                    current = replace(
                        current,
                        history_available_from=current.history_available_from or plan.supported_history_from,
                        tracking_start_at=plan.selected_start,
                        initial_import_completed_at=current.initial_import_completed_at or datetime.now(timezone.utc),
                        last_sync_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                await repository.save(current)
            await session.flush()
            return result
        return await self._transaction(operation)

    async def start_bybit_tracking(self, tracking_start_at):
        """Persist NEW_ONLY setup after explicit Telegram confirmation."""
        account = self._account_id()
        async def operation(session):
            repository = SqlAlchemyExchangeImportSettingsRepository(session)
            current = await repository.get(account_id=account, exchange="BYBIT")
            if current is None:
                raise ValueError("Bybit history must be discovered before starting tracking")
            preview = PreviewTrackingStartChange().execute(current, tracking_start_at)
            updated = replace(
                current,
                tracking_start_at=preview.requested_start,
                initial_import_mode=HistoricalImportMode.NEW_ONLY,
                initial_import_completed_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            await repository.save(updated)
            return updated
        return await self._transaction(operation)

    async def list_excluded_trades(self, *, account_id=None, limit=50, offset=0):
        account = self._account_id(account_id)
        async def operation(session):
            states = await SqlAlchemyTradeJournalStateRepository(session).list(account_id=account, state="EXCLUDED_USER", limit=limit, offset=offset)
            trades = []
            repository = SqlAlchemyTradeRepository(session)
            for state in states:
                trade = await repository.get_by_id(state.trade_id)
                if trade is not None:
                    trades.append(trade)
            return tuple(trades)
        return await self._read(operation)

    async def count_excluded_trades(self, *, account_id=None):
        account = self._account_id(account_id)
        return await self._read(
            lambda session: SqlAlchemyTradeJournalStateRepository(session).count(
                account_id=account, state="EXCLUDED_USER"
            )
        )

    async def get_trade_journal_state(self, trade_id):
        return await self._read(lambda session: SqlAlchemyTradeJournalStateRepository(session).get(trade_id))

    async def exclude_trade(self, trade_id, *, reason="user excluded"):
        async def operation(session):
            return await ExcludeImportedTrade(
                SqlAlchemyTradeRepository(session),
                SqlAlchemyExecutionRepository(session),
                SqlAlchemyTradeJournalStateRepository(session),
                SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
            ).execute(trade_id, reason=reason)
        return await self._transaction(operation)

    async def restore_trade(self, trade_id):
        async def operation(session):
            return await RestoreExcludedTrade(
                SqlAlchemyTradeRepository(session), SqlAlchemyTradeJournalStateRepository(session)
            ).execute(trade_id)
        return await self._transaction(operation)

    async def preview_bulk_exclude_old_incomplete(self, *, older_than, account_id=None):
        account = self._account_id(account_id)
        async def operation(session):
            return await PreviewBulkExcludeOldIncomplete(
                SqlAlchemyTradeRepository(session), SqlAlchemyExecutionRepository(session),
                SqlAlchemyTradeJournalStateRepository(session), SqlAlchemyCustomFieldRepository(session),
                SqlAlchemyTradeCustomValueRepository(session),
            ).execute(account_id=account, older_than=older_than)
        return await self._read(operation)

    async def apply_bulk_exclusion(self, preview, *, confirm_token):
        async def operation(session):
            return await ApplyBulkExclusion(
                SqlAlchemyTradeRepository(session), SqlAlchemyTradeJournalStateRepository(session)
            ).execute(preview, confirm_token=confirm_token)
        return await self._transaction(operation)

    def _account_id(self, account_id=None):
        candidate = account_id or self.default_account_id
        if candidate is None:
            raise ValueError("account_id is required for user settings")
        return candidate if isinstance(candidate, AccountId) else AccountId(candidate)
    async def miniapp_statistics_metrics(self):
        return DEFAULT_STATISTICS_METRIC_REGISTRY.list()

    async def miniapp_statistics_layout(self, account_id=None):
        account = self._account_id(account_id)
        async def operation(session):
            layout = await SqlAlchemyStatisticsLayoutRepository(session).get(account)
            return (layout or StatisticsLayout()).normalized()
        return await self._read(operation)

    async def save_statistics_layout(self, account_id, layout):
        account = self._account_id(account_id)
        candidate = layout if isinstance(layout, StatisticsLayout) else StatisticsLayout(**layout)
        candidate = candidate.normalized()
        async def operation(session):
            await SqlAlchemyStatisticsLayoutRepository(session).save(account, candidate)
            return candidate
        return await self._transaction(operation)

    async def miniapp_statistics_overview(self, filters: StatisticsFilter, account_id=None):
        layout = await self.miniapp_statistics_layout(account_id)
        async def operation(session):
            engine = StatisticsEngine(SqlAlchemyTradeStatisticsQuery(session))
            summary = await engine.get_performance_summary(filters)
            series = await engine.get_cumulative_pnl(filters)
            coverage = {}
            for definition in DEFAULT_STATISTICS_METRIC_REGISTRY.list():
                if definition.coverage_metric:
                    coverage[definition.metric_id] = await engine.get_metric_coverage(definition.coverage_metric, filters)
            return {"summary": summary, "series": series, "layout": layout, "coverage": coverage}
        return await self._read(operation)

    async def miniapp_automatic_factors(self, account_id=None):
        account = self._account_id(account_id)
        async def operation(session):
            settings = await SqlAlchemyAutomaticFactorSettingsRepository(session).list(account)
            return tuple((definition, settings.get(definition.factor_id, True)) for definition in DEFAULT_AUTOMATIC_FACTOR_REGISTRY.list(active_only=True))
        return await self._read(operation)

    async def set_automatic_factor_enabled(self, account_id, factor_id, enabled):
        account = self._account_id(account_id)
        if DEFAULT_AUTOMATIC_FACTOR_REGISTRY.get(factor_id) is None:
            raise ValueError("unknown automatic factor")
        async def operation(session):
            await SqlAlchemyAutomaticFactorSettingsRepository(session).set_enabled(account, factor_id, enabled)
            return {"factor_id": factor_id, "enabled": bool(enabled)}
        return await self._transaction(operation)


def create_runtime(database_url: str, account_id=None, entry_timezone=None):
    engine = create_async_engine(database_url)
    session_factory = create_session_factory(engine)
    return engine, JournalApplication(session_factory, account_id, entry_timezone=entry_timezone)
