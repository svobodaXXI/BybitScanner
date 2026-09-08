import asyncio
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import logging

import pytest

from app.application.use_cases.discover_supported_bybit_history import DiscoverSupportedBybitHistory
from app.application.use_cases.historical_import_workflow import (
    HistoricalImportSelection,
    ImportHistoricalBybit,
    PreviewHistoricalImport,
)
from app.application.errors import HistoricalPreviewError
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.imports import HistoricalImportMode, HistoricalImportPlan, LogicalTradePreview
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.trade_id import TradeId
from app.core.imports import check_bybit_execution


def raw(external_id, at, *, fee_currency="USDT", fee_key=True):
    row = {
        "execId": external_id,
        "symbol": "ZECUSDT",
        "side": "Buy",
        "execQty": "0.01",
        "execPrice": "1000",
        "execFee": "0.01",
        "execTime": str(int(at.timestamp() * 1000)),
        "execType": "Trade",
    }
    if fee_key:
        row["feeCurrency"] = fee_currency
    return row


class RawSource:
    account_id = AccountId.generate()

    def __init__(self, rows):
        self.rows = rows

    async def fetch_raw_historical_executions(self, *, start_at, end_at):
        return tuple(self.rows)


def test_discovery_uses_last_incompatible_and_keeps_fee_currency_strict():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    source = RawSource([
        raw("legacy", base, fee_key=False),
        raw("old-modern", base + timedelta(days=1)),
        {**raw("malformed", base + timedelta(days=2)), "execQty": ""},
        raw("boundary", base + timedelta(days=3)),
    ])
    result = asyncio.run(DiscoverSupportedBybitHistory(source).execute(lookback_start=base, lookback_end=base + timedelta(days=4), persist=False))
    assert result.status == "SUPPORTED"
    assert result.history_available_from == base + timedelta(days=3)
    assert result.incompatible_count == 1
    assert result.incompatibilities[0].reason_incompatible == "missing execQty"


def test_canonical_compatibility_reports_exact_reasons_without_fee_inference():
    base = raw("x", datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert check_bybit_execution({key: value for key, value in base.items() if key != "feeCurrency"}).supported
    assert check_bybit_execution({**base, "feeCurrency": "BTC"}).supported
    assert check_bybit_execution({**base, "side": "Other"}).reason == "invalid side"


def test_inactive_historical_instrument_is_supported_by_adapter():
    from app.infrastructure.exchanges.bybit.execution_source import BybitExecutionSource
    from app.infrastructure.exchanges.bybit.config import BybitSettings
    from app.core.instruments import Instrument, InstrumentId
    from app.infrastructure.exchanges.bybit.errors import BybitPayloadError

    class Client:
        async def get(self, path, params):
            return {"retCode": 0, "result": {"list": [
                {**raw("inactive", datetime(2025, 1, 1, tzinfo=timezone.utc)), "symbol": "ZECUSDT"},
            ], "nextPageCursor": None}}

    inactive = Instrument(InstrumentId.generate(), "ZECUSDT", "ZEC", "BYBIT", "LINEAR", False)
    class Repo:
        async def get_by_exchange_symbol(self, exchange, symbol, *, active_only=True):
            return () if active_only else (inactive,)

    settings = BybitSettings(api_key="key", api_secret="secret", account_id=RawSource.account_id, max_retries=0)
    facts = asyncio.run(__import__("app.infrastructure.exchanges.bybit.execution_source", fromlist=["BybitExecutionSource"]).BybitExecutionSource(settings, Repo(), Client()).fetch_historical_executions(
        start_at=datetime(2025, 1, 1, tzinfo=timezone.utc), end_at=datetime(2025, 1, 2, tzinfo=timezone.utc)))
    assert len(facts) == 1


def test_absent_historical_instrument_gets_deterministic_inactive_identity():
    from app.infrastructure.exchanges.bybit.execution_source import BybitExecutionSource
    from app.infrastructure.exchanges.bybit.config import BybitSettings

    class Client:
        async def get(self, path, params):
            return {"retCode": 0, "result": {"list": [raw("absent", datetime(2025, 1, 1, tzinfo=timezone.utc))], "nextPageCursor": None}}

    class Repo:
        async def get_by_exchange_symbol(self, exchange, symbol, *, active_only=True):
            return ()

    settings = BybitSettings(api_key="key", api_secret="secret", account_id=RawSource.account_id, max_retries=0)
    source = BybitExecutionSource(settings, Repo(), Client())
    facts = asyncio.run(source.fetch_historical_executions(
        start_at=datetime(2025, 1, 1, tzinfo=timezone.utc), end_at=datetime(2025, 1, 2, tzinfo=timezone.utc)))
    assert len(facts) == 1
    assert source.historical_instrument_identities[0].symbol == "ZECUSDT"
    assert source.historical_instrument_identities[0].instrument_id == facts[0].instrument_id


class SettingsStore:
    def __init__(self, current):
        self.current = current
        self.saved = []

    async def get(self, **kwargs):
        return self.current

    async def save(self, value):
        self.saved.append(value)
        self.current = value


def test_force_refresh_replaces_stale_persisted_boundary():
    from app.core.imports import ExchangeImportSettings
    account = RawSource.account_id
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    stale = ExchangeImportSettings(account, "BYBIT", history_available_from=base + timedelta(days=99))
    store = SettingsStore(stale)
    result = asyncio.run(DiscoverSupportedBybitHistory(RawSource([raw("one", base + timedelta(days=1))]), store).execute(
        lookback_start=base, lookback_end=base + timedelta(days=2), force_refresh=True))
    assert result.history_available_from == base + timedelta(days=1)
    assert store.saved[-1].history_available_from == base + timedelta(days=1)


def test_bybit_history_snapshot_reuses_within_ttl_and_refetches_after_expiry():
    from dataclasses import replace
    from app.telegram.composition import JournalApplication
    from app.core.imports import BybitHistorySnapshot

    account = AccountId.generate()
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    class SnapshotSource:
        def __init__(self):
            self.calls = 0
        async def fetch_raw_historical_executions(self, *, start_at, end_at):
            self.calls += 1
            return (raw(f"row-{self.calls}", start_at),)
        async def normalize_raw_historical_executions(self, rows):
            return ()

    application = JournalApplication(None, default_account_id=account)
    source = SnapshotSource()
    selection = HistoricalImportSelection(HistoricalImportMode.CUSTOM, base, selected_start=base, selected_end=base + timedelta(days=1))
    asyncio.run(application._bybit_history_facts(source, selection))
    asyncio.run(application._bybit_history_facts(source, selection))
    assert source.calls == 1
    snapshot = application._bybit_snapshots[account]
    application._bybit_snapshots[account] = replace(snapshot, created_at=base)
    asyncio.run(application._bybit_history_facts(source, selection))
    assert source.calls == 2
    assert isinstance(application._bybit_snapshots[account], BybitHistorySnapshot)


def test_bybit_history_snapshot_extends_backward_before_preview_normalization():
    from app.telegram.composition import JournalApplication
    from app.core.imports import BybitHistorySnapshot

    account = AccountId.generate()
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)

    class SnapshotSource:
        def __init__(self):
            self.ranges = []

        async def fetch_raw_historical_executions(self, *, start_at, end_at):
            self.ranges.append((start_at, end_at))
            return ()

        async def normalize_raw_historical_executions(self, rows):
            return ()

    application = JournalApplication(None, default_account_id=account)
    source = SnapshotSource()
    application._bybit_snapshots[account] = BybitHistorySnapshot(
        account, base + timedelta(days=1), base + timedelta(days=2),
        datetime.now(timezone.utc), (),
    )
    selection = HistoricalImportSelection(
        HistoricalImportMode.CUSTOM, base,
        selected_start=base, selected_end=base + timedelta(days=2),
    )

    asyncio.run(application._bybit_history_facts(source, selection))

    assert source.ranges == [(base, base + timedelta(days=1) - timedelta(milliseconds=1))]
    snapshot = application._bybit_snapshots[account]
    assert snapshot.fetched_from == base
    assert snapshot.fetched_to == base + timedelta(days=2)


def test_discovery_all_modern_and_no_history():
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    result = asyncio.run(DiscoverSupportedBybitHistory(RawSource([raw("one", base)])).execute(lookback_start=base, lookback_end=base + timedelta(days=1), persist=False))
    assert result.history_available_from == base
    empty = asyncio.run(DiscoverSupportedBybitHistory(RawSource([])).execute(lookback_start=base, lookback_end=base + timedelta(days=1), persist=False))
    assert empty.status == "NO_HISTORY"


def fact(external_id, side, at, instrument_id):
    return ExecutionFact(
        exchange="BYBIT", account_id=RawSource.account_id, instrument_id=instrument_id,
        side=side, quantity=Quantity("0.01"), price=Price("1000"),
        fee=Money("0.01", "USDT"), executed_at=at, external_execution_id=external_id,
    )


def sized_fact(external_id, side, at, instrument_id, quantity):
    return replace(fact(external_id, side, at, instrument_id), quantity=Quantity(quantity))


class FactSource:
    def __init__(self, facts):
        self.facts = facts

    async def fetch_historical_executions(self, *, start_at, end_at):
        return self.facts


class EmptyExecutionRepository:
    async def get_by_external_id(self, **kwargs):
        return None


class Instruments:
    async def get_by_id(self, instrument_id):
        return type("Instrument", (), {"symbol": "ZECUSDT"})()


def test_preview_counts_logical_trades_not_fills_and_detects_boundary_crossing():
    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = (
        fact("open", ExecutionSide.BUY, base, instrument_id),
        fact("close", ExecutionSide.SELL, base + timedelta(days=2), instrument_id),
    )
    selection = HistoricalImportSelection(HistoricalImportMode.CUSTOM, base, base + timedelta(days=1), base + timedelta(days=3))
    preview, plan = asyncio.run(PreviewHistoricalImport(FactSource(facts), EmptyExecutionRepository(), Instruments()).execute(selection))
    assert preview.execution_count == 1
    assert preview.logical_trade_count == 1
    assert preview.boundary_crossing_trade_count == 1
    assert preview.would_import_trade_count == 0
    assert plan.execution_count == 0


@pytest.mark.parametrize("opening_side,closing_side", [
    (ExecutionSide.BUY, ExecutionSide.SELL),
    (ExecutionSide.SELL, ExecutionSide.BUY),
])
def test_preview_reconstructs_position_context_inside_long_or_short_without_false_reversal(opening_side, closing_side):
    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = (
        fact("pre-period", opening_side, base, instrument_id),
        fact("in-period-close", closing_side, base + timedelta(days=2), instrument_id),
    )
    selection = HistoricalImportSelection(
        HistoricalImportMode.CUSTOM, base,
        selected_start=base + timedelta(days=1), selected_end=base + timedelta(days=3),
    )
    preview, plan = asyncio.run(PreviewHistoricalImport(
        FactSource(facts), EmptyExecutionRepository(), Instruments()
    ).execute(selection))

    assert preview.execution_count == 1
    assert preview.logical_trade_count == 1
    assert preview.boundary_crossing_trade_count == 1
    assert preview.would_import_trade_count == 0
    assert plan.execution_count == 0


def test_historical_preview_adapter_handles_real_residual_reversal_without_changing_manual_core():
    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = (
        sized_fact("open-long", ExecutionSide.BUY, base, instrument_id, "1"),
        sized_fact("reverse", ExecutionSide.SELL, base + timedelta(days=2), instrument_id, "2"),
    )
    selection = HistoricalImportSelection(
        HistoricalImportMode.CUSTOM, base,
        selected_start=base, selected_end=base + timedelta(days=3),
    )
    preview, plan = asyncio.run(PreviewHistoricalImport(
        FactSource(facts), EmptyExecutionRepository(), Instruments()
    ).execute(selection))

    assert preview.execution_count == 2
    assert preview.logical_trade_count == 2
    assert preview.boundary_crossing_trade_count == 0
    assert plan.execution_count == 2
    assert {item.status for item in preview.logical_trades} == {"CLOSED", "OPEN"}
    assert preview.raw_exchange_execution_count == 2
    assert preview.reconstruction_leg_count == 3


def test_preview_failure_preserves_stage_and_real_traceback_without_secrets(caplog):
    class BrokenSource(FactSource):
        async def fetch_historical_executions(self, *, start_at, end_at):
            raise ValueError("api_secret=do-not-log")

    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    selection = HistoricalImportSelection(
        HistoricalImportMode.ALL_AVAILABLE, base, selected_end=base + timedelta(days=1)
    )
    with caplog.at_level(logging.ERROR):
        with pytest.raises(HistoricalPreviewError) as raised:
            asyncio.run(PreviewHistoricalImport(
                BrokenSource(()), EmptyExecutionRepository(), Instruments()
            ).execute(selection))

    assert raised.value.stage == "FETCH_RAW"
    assert raised.value.code == "HISTORICAL_FETCH"
    record = next(item for item in caplog.records if "Historical preview failed" in item.message)
    assert record.exc_info is not None
    assert "api_secret" not in record.message
    assert "do-not-log" not in record.message


@pytest.mark.parametrize("mode", [
    HistoricalImportMode.LAST_30_DAYS,
    HistoricalImportMode.ALL_AVAILABLE,
    HistoricalImportMode.CUSTOM,
])
def test_preview_modes_are_read_only(mode):
    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    facts = (
        fact("open", ExecutionSide.BUY, base, instrument_id),
        fact("close", ExecutionSide.SELL, base + timedelta(days=2), instrument_id),
    )

    class WriteTrackingExecutionRepository(EmptyExecutionRepository):
        writes = 0

        async def save(self, value):
            self.writes += 1

    repository = WriteTrackingExecutionRepository()
    selected_start = base + timedelta(days=1) if mode is HistoricalImportMode.CUSTOM else None
    selection = HistoricalImportSelection(
        mode, base, selected_start=selected_start,
        selected_end=base + timedelta(days=3),
    )
    asyncio.run(PreviewHistoricalImport(
        FactSource(facts), repository, Instruments()
    ).execute(selection))

    assert repository.writes == 0


def test_duplicate_normalized_external_execution_is_counted_once():
    instrument_id = InstrumentId.generate()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    duplicate = fact("same-exec", ExecutionSide.BUY, base, instrument_id)
    selection = HistoricalImportSelection(
        HistoricalImportMode.ALL_AVAILABLE, base, selected_end=base + timedelta(days=1)
    )
    preview, plan = asyncio.run(PreviewHistoricalImport(
        FactSource((duplicate, duplicate)), EmptyExecutionRepository(), Instruments()
    ).execute(selection))

    assert preview.execution_count == 1
    assert preview.raw_exchange_execution_count == 1
    assert preview.reconstruction_leg_count == 1
    assert plan.execution_count == 1


def test_selection_modes_obey_supported_boundary_and_new_only_is_now():
    base = datetime.now(timezone.utc) - timedelta(days=10)
    end = datetime.now(timezone.utc)
    assert HistoricalImportSelection(HistoricalImportMode.LAST_30_DAYS, base, selected_end=end).selected_start == base
    selection = HistoricalImportSelection(HistoricalImportMode.NEW_ONLY, base, selected_end=end)
    assert selection.selected_start == selection.selected_end
    with pytest.raises(ValueError):
        HistoricalImportSelection(HistoricalImportMode.CUSTOM, base, selected_start=base - timedelta(seconds=1), selected_end=end)


def test_import_result_reconciliation_does_not_double_count_baseline_lifecycle():
    instrument_id = InstrumentId.generate()
    account_id = RawSource.account_id
    at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    baseline_fact = fact("baseline", ExecutionSide.BUY, at, instrument_id)
    baseline_view = LogicalTradePreview(
        trade_id=TradeId.generate(), account_id=account_id, instrument_id=instrument_id,
        opened_at=at, closed_at=None, status="OPEN", execution_count=1,
        external_execution_ids=("baseline",), baseline=True,
    )
    plan = HistoricalImportPlan(
        selected_start=at, selected_end=at + timedelta(days=1), supported_history_from=at,
        executions=(baseline_fact,), logical_trades=(), boundary_crossing=(),
        baseline_open_trades=(baseline_view,), planned_journal_trade_count=1,
    )
    class BaselineProcessor:
        async def execute(self, fact, *, historical_instrument=None, allow_historical_reversal=False):
            from app.application.use_cases.process_execution_and_update_trade import ProcessExecutionAndUpdateTradeResult, TradeAction
            from app.application.use_cases.process_execution_fact import ExecutionProcessingStatus
            from app.core.trades.execution_id import ExecutionId
            return ProcessExecutionAndUpdateTradeResult(
                ExecutionProcessingStatus.PROCESSED, ExecutionId.generate(), TradeId.generate(), TradeAction.CREATED
            )

    result = asyncio.run(ImportHistoricalBybit(BaselineProcessor()).execute(plan, confirm_token=plan.token))

    assert result.planned_journal_trades == 1
    assert result.created == 0
    assert result.updated == 0
    assert result.baseline == 1
    assert result.skipped == 0
    assert result.planned_journal_trades == result.baseline + result.skipped + len(result.errors)
