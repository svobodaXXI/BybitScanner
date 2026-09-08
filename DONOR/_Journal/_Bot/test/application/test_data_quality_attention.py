import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.application.attention import GetAttentionCenter
from app.application.statistics import DynamicFieldMetadata, StatisticsEngine, StatisticsFilter, StatisticsTradeRecord
from app.core.accounts.account_id import AccountId
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.money import Money
from app.core.common.risk import Risk
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import CustomFieldDefinition, CustomFieldPhase, CustomFieldSource, CustomFieldValueType
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade


NOW = datetime(2026, 9, 4, 10, tzinfo=timezone.utc)


def make_trade(status="CLOSED"):
    trade = Trade.open(AccountId.generate(), InstrumentId.generate(), TradeDirection.LONG, Price(100), Quantity(1), NOW - timedelta(hours=2), "USDT")
    if status == "CLOSED":
        trade.close(Price(110), NOW - timedelta(hours=1))
    return trade


class StatsQuery:
    def __init__(self, records, metadata=()):
        self.records = tuple(records)
        self.metadata = tuple(metadata)

    async def list_trades(self, filters):
        return self.records

    async def list_required_statistics_fields(self):
        return self.metadata

    async def get_dynamic_field(self, *, field_id=None, field_code=None):
        return self.metadata[0] if self.metadata else None

    async def list_custom_values(self, trade_ids, field_id):
        return ()


def run(coro):
    return asyncio.run(coro)


def test_statistics_only_uses_closed_ready_and_exposes_counts():
    ready = StatisticsTradeRecord.from_trade(make_trade())
    open_record = StatisticsTradeRecord.from_trade(make_trade("OPEN"))
    incomplete = replace(StatisticsTradeRecord.from_trade(make_trade()), exit_price=None, net_pnl=None, gross_pnl=None)
    result = run(StatisticsEngine(StatsQuery([ready, incomplete, open_record])).get_performance_summary(StatisticsFilter(status=None)))
    assert result.trade_count == 1
    assert result.ready_count == 1
    assert result.excluded_incomplete_count == 1
    assert result.open_count == 1
    assert result.net_pnl == 10


def test_required_dynamic_field_is_applied_to_general_statistics():
    field = CustomFieldDefinition.create("setup", "Setup", CustomFieldValueType.TEXT, CustomFieldSource.MANUAL, CustomFieldPhase.POST_TRADE, required_for_statistics=True)
    record = StatisticsTradeRecord.from_trade(make_trade())
    metadata = DynamicFieldMetadata(field)
    result = run(StatisticsEngine(StatsQuery([record], [metadata])).get_performance_summary())
    assert result.trade_count == 0
    assert result.excluded_incomplete_count == 1


def test_missing_stop_excludes_only_realized_r_metric():
    trade = make_trade()
    record = StatisticsTradeRecord.from_trade(trade)
    summary = run(StatisticsEngine(StatsQuery([record])).get_performance_summary())
    coverage = run(StatisticsEngine(StatsQuery([record])).get_metric_coverage("REALIZED_R"))
    assert summary.trade_count == 1
    assert coverage.eligible_trade_count == 1
    assert coverage.calculated_count == 0
    assert coverage.missing_count == 1
    assert coverage.coverage_rate == 0


class TradeRepo:
    def __init__(self, trades): self.trades = tuple(trades)
    async def list_all(self, **kwargs): return self.trades


class FieldRepo:
    def __init__(self, fields): self.fields = tuple(fields)
    async def list_definitions(self, **kwargs): return self.fields


class ValueRepo:
    async def list_by_trade(self, trade_id): return ()


def test_attention_counts_one_trade_once_with_multiple_missing_reasons():
    incomplete = replace(make_trade(), exit_price=None, net_pnl=None, gross_pnl=None)
    result = run(GetAttentionCenter(TradeRepo([incomplete]), FieldRepo(()), ValueRepo()).execute())
    assert result.summary.total_attention == 1
    assert result.summary.incomplete_count == 1
    assert set(result.items[0].readiness.missing) == {"EXIT_PRICE", "NET_PNL"}
