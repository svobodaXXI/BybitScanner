import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application import (
    HistoricalExecutionBackfill,
    HistoricalExecutionBackfillCommand,
    PreviewHistoricalExecutionImport,
)
from app.application.errors import UnsafeHistoricalBoundaryError
from app.application.use_cases.process_execution_and_update_trade import (
    ProcessExecutionAndUpdateTradeResult,
    TradeAction,
)
from app.application.use_cases.process_execution_fact import ExecutionProcessingStatus
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import Instrument, InstrumentId
from app.core.trades.execution_side import ExecutionSide
from app.core.trades.execution_fact import ExecutionFact
from app.core.trades.execution_id import ExecutionId
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 9, 5, 5, tzinfo=timezone.utc)


def make_fact(external_id: str, symbol_id: InstrumentId, at: datetime) -> ExecutionFact:
    return ExecutionFact(
        exchange="BYBIT",
        account_id=AccountId.generate(),
        instrument_id=symbol_id,
        side=ExecutionSide.BUY,
        quantity=Quantity("0.01"),
        price=Price("100"),
        fee=Money(Decimal("0.01"), "USDT"),
        executed_at=at,
        external_execution_id=external_id,
    )


class SourceFake:
    def __init__(self, facts):
        self.facts = tuple(facts)
        self.calls = []

    async def fetch_historical_executions(self, *, start_at, end_at=None):
        self.calls.append((start_at, end_at))
        return self.facts


class ProcessorFake:
    def __init__(self):
        self.facts = []

    async def execute(self, fact):
        self.facts.append(fact)
        status = ExecutionProcessingStatus.ALREADY_PROCESSED if fact.external_execution_id == "replay" else ExecutionProcessingStatus.PROCESSED
        action = TradeAction.NONE if status is ExecutionProcessingStatus.ALREADY_PROCESSED else TradeAction.CLOSED
        return ProcessExecutionAndUpdateTradeResult(status, ExecutionId.generate(), TradeId.generate(), action)


class InstrumentsFake:
    def __init__(self, *items):
        self.items = {item.instrument_id: item for item in items}
        self.calls = []

    async def get_by_id(self, instrument_id):
        self.calls.append(instrument_id)
        return self.items.get(instrument_id)


def test_backfill_requires_explicit_mid_position_boundary_acknowledgement():
    instrument_id = InstrumentId.generate()
    source = SourceFake((make_fact("one", instrument_id, NOW),))
    with pytest.raises(UnsafeHistoricalBoundaryError):
        asyncio.run(HistoricalExecutionBackfill(source, ProcessorFake()).execute(
            HistoricalExecutionBackfillCommand(NOW, NOW)
        ))
    assert source.calls == []


def test_backfill_sorts_facts_and_returns_idempotency_and_trade_counters():
    instrument_id = InstrumentId.generate()
    source = SourceFake((
        make_fact("closed", instrument_id, NOW.replace(hour=7)),
        make_fact("replay", instrument_id, NOW.replace(hour=6)),
    ))
    processor = ProcessorFake()
    summary = asyncio.run(HistoricalExecutionBackfill(source, processor).execute(
        HistoricalExecutionBackfillCommand(NOW, allow_unsafe_boundary=True)
    ))
    assert [item.external_execution_id for item in processor.facts] == ["replay", "closed"]
    assert summary.fetched == 2
    assert summary.processed == 1
    assert summary.already_processed == 1
    assert summary.trades_closed == 1
    assert summary.errors == 0


def test_backfill_error_details_redact_authentication_data():
    instrument_id = InstrumentId.generate()
    source = SourceFake((make_fact("secret-bearing-fact", instrument_id, NOW),))

    class FailingProcessor:
        async def execute(self, fact):
            raise RuntimeError("api_secret=do-not-print Authorization: Bearer do-not-print")

    summary = asyncio.run(HistoricalExecutionBackfill(source, FailingProcessor()).execute(
        HistoricalExecutionBackfillCommand(NOW, allow_unsafe_boundary=True)
    ))

    assert summary.errors == 1
    assert "do-not-print" not in summary.error_messages[0]
    assert "redacted" in summary.error_messages[0]


def test_preview_reports_symbols_counts_time_range_and_sanitized_sample_without_writes():
    first_id = InstrumentId.generate()
    second_id = InstrumentId.generate()
    account = AccountId.generate()
    first = make_fact("first", first_id, NOW)
    second = ExecutionFact(
        "BYBIT", account, second_id, ExecutionSide.SELL, Quantity("2"), Price("101"),
        Money("0.02", "USDT"), NOW.replace(hour=6), external_execution_id="second",
    )
    source = SourceFake((second, first))
    instruments = InstrumentsFake(
        Instrument(first_id, "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR"),
        Instrument(second_id, "ZECUSDT", "Zcash", "BYBIT", "LINEAR"),
    )
    preview = asyncio.run(PreviewHistoricalExecutionImport(source, instruments).execute(
        start_at=NOW, end_at=NOW.replace(hour=8), sample_limit=1
    ))
    assert preview.execution_count == 2
    assert preview.symbol_count == 2
    assert preview.first_executed_at == NOW
    assert preview.last_executed_at == NOW.replace(hour=6)
    assert preview.counts_by_symbol == (("BTCUSDT", 1), ("ZECUSDT", 1))
    assert len(preview.sample) == 1
    assert preview.sample[0].external_execution_id == "first"
    assert not hasattr(preview.sample[0], "api_secret")
