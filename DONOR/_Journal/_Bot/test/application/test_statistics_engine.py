import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.statistics import (
    DynamicFieldCoverageRequest,
    DynamicFieldMetadata,
    GroupedPerformanceRequest,
    PerformanceSummary,
    StatisticsEngine,
    StatisticsFilter,
    StatisticsGroupBy,
    StatisticsTradeRecord,
)
from app.core.accounts.account_id import AccountId
from app.core.common.expense import Expense
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldOption,
    CustomFieldPhase,
    CustomFieldResolutionContext,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldStatus,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.statistics.ids import CustomFieldOptionId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade


UTC = timezone.utc
BASE = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def run(coroutine):
    return asyncio.run(coroutine)


class QueryFake:
    def __init__(self, records=(), metadata=None, values=()):
        self.records = tuple(records)
        self.metadata = metadata
        self.values = tuple(values)
        self.value_calls = []

    async def list_trades(self, filters):
        return self.records

    async def get_dynamic_field(self, *, field_id=None, field_code=None):
        if self.metadata is None:
            return None
        definition = self.metadata.definition
        if field_id is not None and field_id != definition.id:
            return None
        if field_code is not None and field_code.strip().lower() != str(definition.code):
            return None
        return self.metadata

    async def list_custom_values(self, trade_ids, field_id):
        self.value_calls.append((tuple(trade_ids), field_id))
        allowed = set(trade_ids)
        return tuple(value for value in self.values if value.trade_id in allowed and value.field_id == field_id)


def closed_record(
    net,
    *,
    gross=None,
    fees=0,
    expenses=(),
    account_id=None,
    instrument_id=None,
    direction=TradeDirection.LONG,
    closed_at=BASE,
    context=None,
):
    trade = Trade.open(
        account_id=account_id or AccountId.generate(),
        instrument_id=instrument_id or InstrumentId.generate(),
        direction=direction,
        entry_price=Price(100),
        quantity=Quantity(1),
        opened_at=closed_at - timedelta(hours=1),
        currency="USDT",
    )
    if fees:
        trade.add_fee(Money(fees, "USDT"))
    for expense in expenses:
        trade.add_expense(Expense(Money(expense, "USDT")))
    gross_value = Decimal(str(gross if gross is not None else net))
    exit_price = 100 + gross_value if direction is TradeDirection.LONG else 100 - gross_value
    trade.close(Price(exit_price), closed_at)
    # The trade's domain PnL is authoritative. Use this helper's net argument
    # to make non-trade fixture construction explicit and deterministic.
    if trade.net_pnl.amount != Decimal(str(net)):
        raise AssertionError("fixture net must equal domain-calculated net PnL")
    result = StatisticsTradeRecord.from_trade(trade)
    return replace(result, resolution_context=context)


def make_field(code, value_type=CustomFieldValueType.TEXT, *, phase=CustomFieldPhase.ANY, status=CustomFieldStatus.ACTIVE):
    definition = CustomFieldDefinition.create(
        code=code,
        name=code,
        value_type=value_type,
        source=CustomFieldSource.MANUAL,
        phase=phase,
        created_at=BASE,
    )
    return definition if status is CustomFieldStatus.ACTIVE else definition.deactivate()


def make_value(record, definition, raw, *, recorded_at=BASE):
    return TradeCustomValue.create(record.trade_id, definition, raw, recorded_at)


def test_empty_summary_has_zero_sums_and_undefined_rates():
    engine = StatisticsEngine(QueryFake())
    result = run(engine.get_performance_summary())

    assert isinstance(result, PerformanceSummary)
    assert result.trade_count == 0
    assert result.sample_size == 0
    assert result.gross_pnl == Decimal("0")
    assert result.net_pnl == Decimal("0")
    assert result.win_rate is None
    assert result.profit_factor is None
    assert result.expectancy is None
    assert result.currency is None


def test_current_open_count_is_independent_of_realized_period_filter():
    account = AccountId.generate()
    instrument = InstrumentId.generate()
    trade = Trade.open(
        account, instrument, TradeDirection.LONG, Price(100), Quantity(1), BASE, "USDT"
    )
    open_record = StatisticsTradeRecord.from_trade(trade)

    class QueryWithCurrentOpen(QueryFake):
        async def count_current_open(self, *, account_id=None, instrument_id=None):
            assert account_id == account
            assert instrument_id is None
            return 1

    for period in (
        StatisticsFilter(account_id=account, from_at=BASE, to_at=BASE + timedelta(days=1)),
        StatisticsFilter(account_id=account, from_at=BASE - timedelta(days=7)),
        StatisticsFilter(account_id=account, from_at=BASE - timedelta(days=30)),
        StatisticsFilter(account_id=account),
    ):
        result = run(StatisticsEngine(QueryWithCurrentOpen((open_record,))).get_performance_summary(period))
        assert result.open_count == 1
        assert result.trade_count == 0


def test_cumulative_pnl_is_ordered_and_uses_only_ready_closed_records():
    records = [
        closed_record(Decimal("2"), closed_at=BASE + timedelta(days=2)),
        closed_record(Decimal("-1"), closed_at=BASE + timedelta(days=1)),
    ]
    points = run(StatisticsEngine(QueryFake(records)).get_cumulative_pnl())
    assert [point.pnl for point in points] == [Decimal("-1"), Decimal("2")]
    assert [point.cumulative_pnl for point in points] == [Decimal("-1"), Decimal("1")]


def test_summary_uses_net_pnl_for_classification_and_aggregates_signed_costs():
    account = AccountId.generate()
    records = (
        closed_record(Decimal("7"), gross=Decimal("10"), fees=1, expenses=(-2,), account_id=account),
        closed_record(Decimal("-5"), gross=Decimal("-5"), account_id=account),
        closed_record(Decimal("0"), gross=Decimal("0"), account_id=account),
    )
    result = run(StatisticsEngine(QueryFake(records)).get_performance_summary())

    assert (result.win_count, result.loss_count, result.breakeven_count) == (1, 1, 1)
    assert result.win_rate == Decimal("0.5")
    assert result.gross_pnl == Decimal("5")
    assert result.net_pnl == Decimal("2")
    assert result.total_fees == Decimal("1")
    assert result.total_expenses == Decimal("-2")
    assert result.average_net_pnl == Decimal("2") / Decimal("3")
    assert result.average_win == Decimal("7")
    assert result.average_loss == Decimal("-5")
    assert result.profit_factor == Decimal("1.4")
    assert result.expectancy == result.average_net_pnl
    assert result.largest_win == Decimal("7")
    assert result.largest_loss == Decimal("-5")
    assert result.median_net_pnl == Decimal("0")


def test_profit_factor_edge_cases_never_emit_infinity_or_nan():
    win = closed_record(Decimal("5"))
    loss = closed_record(Decimal("-5"))
    win_result = run(StatisticsEngine(QueryFake([win])).get_performance_summary())
    loss_result = run(StatisticsEngine(QueryFake([loss])).get_performance_summary())

    assert win_result.profit_factor is None
    assert loss_result.profit_factor == Decimal("0")
    assert win_result.profit_factor not in (Decimal("Infinity"), Decimal("NaN"))


def test_filters_are_account_instrument_direction_and_from_inclusive_to_exclusive():
    account = AccountId.generate()
    instrument = InstrumentId.generate()
    matching = closed_record(5, account_id=account, instrument_id=instrument, closed_at=BASE + timedelta(days=1))
    outside = closed_record(7, account_id=account, instrument_id=instrument, closed_at=BASE + timedelta(days=2))
    wrong_direction = closed_record(
        9,
        account_id=account,
        instrument_id=instrument,
        direction=TradeDirection.SHORT,
        closed_at=BASE + timedelta(days=1),
    )
    filters = StatisticsFilter(
        account_id=account,
        instrument_id=instrument,
        direction=TradeDirection.LONG,
        from_at=BASE + timedelta(days=1),
        to_at=BASE + timedelta(days=2),
    )
    result = run(StatisticsEngine(QueryFake([matching, outside, wrong_direction])).get_performance_summary(filters))
    assert result.trade_count == 1
    assert result.net_pnl == Decimal("5")
    with pytest.raises(ValueError, match="timezone-aware"):
        StatisticsFilter(from_at=datetime(2026, 9, 1))


def test_closed_is_default_and_static_groups_are_deterministic():
    account_a = AccountId.generate()
    account_b = AccountId.generate()
    records = [
        closed_record(1, account_id=account_a),
        closed_record(3, account_id=account_b),
    ]
    query = QueryFake(records)
    result = run(StatisticsEngine(query).get_grouped_performance(GroupedPerformanceRequest(StatisticsGroupBy.ACCOUNT)))
    assert [group.summary.sample_size for group in result.groups] == [1, 1]
    assert {group.key for group in result.groups} == {str(account_a), str(account_b)}
    assert StatisticsFilter().status.value == "CLOSED"

    instrument_result = run(StatisticsEngine(query).get_grouped_performance(
        GroupedPerformanceRequest(StatisticsGroupBy.INSTRUMENT)
    ))
    assert {group.key for group in instrument_result.groups} == {str(item.instrument_id) for item in records}
    short = closed_record(2, account_id=account_a, direction=TradeDirection.SHORT)
    direction_result = run(StatisticsEngine(QueryFake([*records, short])).get_grouped_performance(
        GroupedPerformanceRequest(StatisticsGroupBy.DIRECTION)
    ))
    assert {group.key for group in direction_result.groups} == {"LONG", "SHORT"}


def test_dynamic_grouping_supports_text_number_yes_no_and_choice_identity():
    records = [closed_record(1), closed_record(2), closed_record(3), closed_record(4)]
    for value_type, raw_values in (
        (CustomFieldValueType.TEXT, ["A", "A", "B", None]),
        (CustomFieldValueType.NUMBER, [Decimal("1.0"), Decimal("1.0"), Decimal("2.0"), None]),
        (CustomFieldValueType.YES_NO, [True, True, False, None]),
    ):
        definition = make_field(f"field_{value_type.value.lower()}", value_type)
        values = [make_value(record, definition, raw) for record, raw in zip(records, raw_values) if raw is not None]
        result = run(StatisticsEngine(QueryFake(records, DynamicFieldMetadata(definition), values)).get_grouped_performance(
            GroupedPerformanceRequest(StatisticsGroupBy.DYNAMIC_FIELD, field_id=definition.id)
        ))
        assert result.eligible_trade_count == 4
        assert result.known_value_count == 3
        assert result.missing_value_count == 1
        assert len(result.groups) == 2

    definition = make_field("setup_choice", CustomFieldValueType.CHOICE)
    option_a = CustomFieldOption.create(definition.id, "a", "First", option_id=CustomFieldOptionId.generate())
    option_b = CustomFieldOption.create(definition.id, "b", "Second", option_id=CustomFieldOptionId.generate())
    values = [make_value(records[0], definition, option_a.id), make_value(records[1], definition, option_b.id)]
    option_b = option_b.deactivate()
    result = run(StatisticsEngine(QueryFake(
        records,
        DynamicFieldMetadata(definition, options=(option_a, option_b)),
        values,
    )).get_grouped_performance(GroupedPerformanceRequest(
        StatisticsGroupBy.DYNAMIC_FIELD,
        field_code="setup_choice",
    )))
    assert {group.key for group in result.groups} == {f"choice:{option_a.id}", f"choice:{option_b.id}"}
    assert {group.label for group in result.groups} == {"First", "Second"}


def test_dynamic_coverage_is_scope_aware_and_inactive_history_remains_readable():
    eligible_context = CustomFieldResolutionContext(CustomFieldPhase.POST_TRADE, market="PERP")
    unrelated_context = CustomFieldResolutionContext(CustomFieldPhase.POST_TRADE, market="SPOT")
    records = [
        closed_record(index + 1, context=eligible_context if index < 5 else unrelated_context)
        for index in range(7)
    ]
    definition = make_field("historical_setup")
    scope = CustomFieldScope.create(definition.id, market="PERP")
    values = [make_value(records[index], definition, f"setup_{index}") for index in range(3)]
    inactive = definition.deactivate()
    query = QueryFake(records, DynamicFieldMetadata(inactive, scopes=(scope,)), values)
    engine = StatisticsEngine(query)

    coverage = run(engine.get_dynamic_field_coverage(DynamicFieldCoverageRequest(field_id=definition.id)))
    grouped = run(engine.get_grouped_performance(GroupedPerformanceRequest(
        StatisticsGroupBy.DYNAMIC_FIELD,
        field_id=definition.id,
    )))

    assert (coverage.eligible_trade_count, coverage.filled_count, coverage.missing_count) == (5, 3, 2)
    assert coverage.coverage_rate == Decimal("0.6")
    assert (grouped.eligible_trade_count, grouped.known_value_count, grouped.missing_value_count) == (5, 3, 2)
    assert grouped.groups and all(group.key != "__missing__" for group in grouped.groups)


def test_dynamic_missing_bucket_and_minimum_sample_size_are_explicit():
    records = [closed_record(1), closed_record(2), closed_record(3)]
    definition = make_field("tag")
    values = [make_value(records[0], definition, "A")]
    result = run(StatisticsEngine(QueryFake(records, DynamicFieldMetadata(definition), values)).get_grouped_performance(
        GroupedPerformanceRequest(
            StatisticsGroupBy.DYNAMIC_FIELD,
            field_id=definition.id,
            include_missing=True,
            min_sample_size=2,
        )
    ))
    assert [group.key for group in result.groups] == ["__missing__"]
    assert result.groups[0].summary.sample_size == 2
