import asyncio
from datetime import datetime, timedelta, timezone

from app.application.use_cases.incremental_bybit_sync import IncrementalBybitSync
from app.application.use_cases.process_execution_and_update_trade import (
    ProcessExecutionAndUpdateTradeResult,
    TradeAction,
)
from app.application.use_cases.process_execution_fact import ExecutionProcessingStatus
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.imports import ExchangeImportSettings
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import ExecutionSide
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade_id import TradeId


BASE = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def fact(external_id, executed_at, *, instrument_id=None):
    return ExecutionFact(
        "BYBIT", ACCOUNT, instrument_id or INSTRUMENT, ExecutionSide.BUY,
        Quantity("0.01"), Price("100"), Money("0.001", "USDT"), executed_at,
        external_execution_id=external_id, external_order_id="order-1", position_id="position-1",
    )


ACCOUNT = AccountId.generate()
INSTRUMENT = InstrumentId.generate()


class SettingsFake:
    def __init__(self, settings):
        self.settings = settings
        self.saved = []

    async def get(self, *, account_id, exchange):
        assert account_id == ACCOUNT
        assert exchange == "BYBIT"
        return self.settings

    async def save(self, settings):
        self.settings = settings
        self.saved.append(settings)


class SourceFake:
    def __init__(self, facts=()):
        self.facts = tuple(facts)
        self.calls = []

    async def fetch_executions(self, **kwargs):
        self.calls.append(kwargs)
        return self.facts


class ProcessorFake:
    def __init__(self, results=(), failures=()):
        self.results = iter(results)
        self.failures = set(failures)
        self.ids = []

    async def execute(self, current_fact):
        self.ids.append(current_fact.external_execution_id)
        if current_fact.external_execution_id in self.failures:
            raise RuntimeError("temporary processing failure")
        return next(self.results)


def result(status, action, trade_id):
    return ProcessExecutionAndUpdateTradeResult(
        status, ExecutionId.generate(), trade_id, action
    )


def settings(last_sync_at=BASE):
    return ExchangeImportSettings(
        ACCOUNT, "BYBIT", history_available_from=BASE - timedelta(days=10),
        tracking_start_at=BASE - timedelta(days=10), last_sync_at=last_sync_at,
    )


def test_no_new_executions_keeps_durable_cursor():
    repository = SettingsFake(settings())
    source = SourceFake()
    processor = ProcessorFake()
    summary = run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE + timedelta(seconds=20)))

    assert summary.fetched == summary.processed == summary.already_processed == 0
    assert summary.cursor == BASE
    assert repository.saved == []
    assert source.calls[0]["since"] == BASE - timedelta(seconds=60)


def test_new_closing_execution_updates_same_trade_and_advances_cursor():
    trade_id = TradeId.generate()
    closing = fact("close-1", BASE + timedelta(seconds=5))
    repository = SettingsFake(settings())
    source = SourceFake((closing,))
    processor = ProcessorFake((result(ExecutionProcessingStatus.PROCESSED, TradeAction.CLOSED, trade_id),))
    summary = run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE + timedelta(seconds=20)))

    assert summary.processed == 1
    assert summary.trades_closed == 1
    assert summary.errors == 0
    assert processor.ids == ["close-1"]
    assert repository.settings.last_sync_at == closing.executed_at
    assert summary.created_trade_ids == ()


def test_incremental_summary_exposes_only_new_logical_trade_ids():
    opened = fact("open-1", BASE + timedelta(seconds=5))
    new_trade_id = TradeId.generate()
    repository = SettingsFake(settings())
    source = SourceFake((opened,))
    processor = ProcessorFake((result(ExecutionProcessingStatus.PROCESSED, TradeAction.CREATED, new_trade_id),))

    summary = run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE + timedelta(seconds=20)))

    assert summary.created_trade_ids == (new_trade_id,)


def test_replayed_execution_does_not_expose_duplicate_notification_id():
    opened = fact("open-1", BASE + timedelta(seconds=5))
    new_trade_id = TradeId.generate()
    repository = SettingsFake(settings())
    source = SourceFake((opened,))
    processor = ProcessorFake((
        result(ExecutionProcessingStatus.PROCESSED, TradeAction.CREATED, new_trade_id),
        result(ExecutionProcessingStatus.ALREADY_PROCESSED, TradeAction.NONE, new_trade_id),
    ))
    service = IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT)

    first = run(service.execute(now=BASE + timedelta(seconds=20)))
    second = run(service.execute(now=BASE + timedelta(seconds=40)))

    assert first.created_trade_ids == (new_trade_id,)
    assert second.created_trade_ids == ()


def test_startup_replay_is_idempotent_with_overlap():
    closing = fact("same-fill", BASE + timedelta(seconds=5))
    repository = SettingsFake(settings())
    source = SourceFake((closing,))
    processor = ProcessorFake((
        result(ExecutionProcessingStatus.PROCESSED, TradeAction.CLOSED, TradeId.generate()),
        result(ExecutionProcessingStatus.ALREADY_PROCESSED, TradeAction.NONE, TradeId.generate()),
    ))
    service = IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT)

    first = run(service.execute(now=BASE + timedelta(seconds=20)))
    second = run(service.execute(now=BASE + timedelta(seconds=40)))

    assert first.processed == 1
    assert second.already_processed == 1
    assert len(processor.ids) == 2
    assert len(repository.saved) == 1


def test_failed_execution_does_not_advance_cursor_past_failure():
    first = fact("first", BASE + timedelta(seconds=1))
    failed = fact("failed", BASE + timedelta(seconds=2))
    later = fact("later", BASE + timedelta(seconds=3))
    repository = SettingsFake(settings())
    source = SourceFake((later, failed, first))
    processor = ProcessorFake(
        (result(ExecutionProcessingStatus.PROCESSED, TradeAction.UPDATED, TradeId.generate()),),
        failures={"failed"},
    )
    summary = run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE + timedelta(seconds=20)))

    assert processor.ids == ["first", "failed"]
    assert summary.processed == 1
    assert summary.errors == 1
    assert repository.settings.last_sync_at == first.executed_at


def test_same_timestamp_fills_are_processed_by_external_id_order():
    same_time = BASE + timedelta(seconds=5)
    first = fact("a-id", same_time)
    second = fact("b-id", same_time)
    repository = SettingsFake(settings())
    source = SourceFake((second, first))
    processor = ProcessorFake((
        result(ExecutionProcessingStatus.PROCESSED, TradeAction.UPDATED, TradeId.generate()),
        result(ExecutionProcessingStatus.PROCESSED, TradeAction.UPDATED, TradeId.generate()),
    ))
    run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE + timedelta(seconds=20)))

    assert processor.ids == ["a-id", "b-id"]


def test_missing_settings_disables_sync_without_fetching():
    repository = SettingsFake(None)
    source = SourceFake((fact("not-fetched", BASE + timedelta(seconds=1)),))
    processor = ProcessorFake()
    summary = run(IncrementalBybitSync(source, processor, repository, account_id=ACCOUNT).execute(now=BASE))

    assert summary == summary.__class__()
    assert source.calls == []
