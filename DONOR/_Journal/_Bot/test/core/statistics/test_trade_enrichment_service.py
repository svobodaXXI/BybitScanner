from datetime import datetime, time, timezone
from decimal import Decimal

import pytest

from app.application.statistics import (
    TradeEnrichmentService,
    TradeEnrichmentStatus,
)
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldPhase,
    CustomFieldScope,
    CustomFieldSource,
    CustomFieldValueType,
    DerivedValueContext,
    DerivedValueService,
    TradingSessionRule,
    TradeCustomValue,
)
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)


def field(code, *, source=CustomFieldSource.MANUAL, required=False, phase=CustomFieldPhase.ANY, value_type=CustomFieldValueType.TEXT):
    return CustomFieldDefinition.create(
        code=code,
        name=code,
        value_type=value_type,
        source=source,
        phase=phase,
        required=required,
        created_at=NOW,
    )


def context(*, closed_at=None, stop_price=None, risk=None, net_pnl=None):
    return DerivedValueContext(
        opened_at=NOW,
        closed_at=closed_at,
        entry_price=Price(100),
        quantity=Quantity(2),
        stop_price=stop_price,
        risk=risk,
        net_pnl=net_pnl,
    )


def value(trade_id, definition, raw_value, *, version=None):
    return TradeCustomValue.create(
        trade_id=trade_id,
        field_definition=definition,
        value=raw_value,
        recorded_at=NOW,
        definition_version=version,
    )


def test_only_auto_fields_are_not_required_and_derived_values_are_generated():
    trade_id = TradeId.generate()
    position = field("position_value", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    exchange = field("fee_quality", source=CustomFieldSource.EXCHANGE, required=True)
    result = TradeEnrichmentService().enrich(
        [position, exchange],
        [],
        [],
        resolution_context=_resolution_context(),
        derived_context=context(),
        trade_id=trade_id,
        recorded_at=NOW,
    )

    assert result.status is TradeEnrichmentStatus.NOT_REQUIRED
    assert result.generated_values[0].value == Decimal("200")
    assert [issue.field for issue in result.unavailable_auto_fields] == [exchange]
    assert not result.missing_manual_required


def _resolution_context(
    phase=CustomFieldPhase.OPEN,
    *,
    strategy_code="LONG_CONTINUATION",
    setup_code="BREAKOUT",
):
    from app.core.statistics import CustomFieldResolutionContext

    return CustomFieldResolutionContext(
        phase=phase,
        exchange="BYBIT",
        market="CRYPTO",
        strategy_code=strategy_code,
        setup_code=setup_code,
    )


def test_manual_statuses_optional_and_required():
    required = field("strategy", required=True)
    optional = field("psychology", required=False)
    service = TradeEnrichmentService()
    pending = service.enrich([required, optional], [], [], _resolution_context(), context(), trade_id=TradeId.generate())
    assert pending.status is TradeEnrichmentStatus.PENDING
    assert pending.missing_manual_required == (required,)
    assert pending.missing_manual_optional == (optional,)

    trade_id = TradeId.generate()
    complete = service.enrich(
        [required, optional],
        [],
        [value(trade_id, required, "LONG_CONTINUATION")],
        _resolution_context(),
        context(),
        trade_id=trade_id,
    )
    assert complete.status is TradeEnrichmentStatus.COMPLETE
    assert complete.missing_manual_optional == (optional,)


def test_existing_derived_value_wins_and_is_not_regenerated():
    trade_id = TradeId.generate()
    derived = field("position_value", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    existing = value(trade_id, derived, Decimal("999"))
    result = TradeEnrichmentService().enrich(
        [derived], [], [existing], _resolution_context(), context(), trade_id=trade_id, recorded_at=NOW
    )
    assert result.existing_values == (existing,)
    assert not result.generated_values
    assert result.all_values == (existing,)


def test_derived_unavailable_and_unsupported_are_classified():
    trade_id = TradeId.generate()
    holding = field("holding_duration", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    unknown = field("new_metric", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    result = TradeEnrichmentService().enrich(
        [holding, unknown], [], [], _resolution_context(), context(), trade_id=trade_id, recorded_at=NOW
    )
    assert [issue.field for issue in result.unavailable_auto_fields] == [holding]
    assert [issue.field for issue in result.unsupported_auto_fields] == [unknown]


@pytest.mark.parametrize("source", [CustomFieldSource.SYSTEM, CustomFieldSource.MARKET_DATA, CustomFieldSource.EXCHANGE])
def test_non_derived_auto_sources_never_become_manual_missing(source):
    definition = field("auto_value", source=source, required=True)
    result = TradeEnrichmentService().enrich([definition], [], [], _resolution_context(), context(), trade_id=TradeId.generate())
    assert result.status is TradeEnrichmentStatus.NOT_REQUIRED
    assert not result.missing_manual_required
    assert result.unavailable_auto_fields[0].source is source


def test_old_value_version_does_not_satisfy_current_manual_or_derived_field():
    trade_id = TradeId.generate()
    manual_v2 = field("review", required=True)
    manual_v2 = CustomFieldDefinition(
        id=manual_v2.id,
        code=manual_v2.code,
        name=manual_v2.name,
        value_type=manual_v2.value_type,
        source=manual_v2.source,
        phase=manual_v2.phase,
        required=manual_v2.required,
        definition_version=2,
        created_at=manual_v2.created_at,
    )
    old_manual = value(trade_id, manual_v2, "old", version=2)
    # The factory intentionally prevents manufacturing a v1 value from a v2 definition.
    old_manual = TradeCustomValue(
        id=old_manual.id,
        trade_id=trade_id,
        field_id=manual_v2.id,
        value="old",
        recorded_at=NOW,
        source=CustomFieldSource.MANUAL,
        definition_version=1,
    )
    result = TradeEnrichmentService().enrich([manual_v2], [], [old_manual], _resolution_context(), context(), trade_id=trade_id)
    assert result.status is TradeEnrichmentStatus.PENDING
    assert result.missing_manual_required == (manual_v2,)
    assert not result.existing_values


def test_duplicate_current_values_are_rejected():
    trade_id = TradeId.generate()
    definition = field("review")
    first = value(trade_id, definition, "one")
    second = value(trade_id, definition, "two")
    with pytest.raises(ValueError):
        TradeEnrichmentService().enrich([definition], [], [first, second], _resolution_context(), context(), trade_id=trade_id)


def test_open_context_realistic_scenario_then_manual_value_completes_enrichment():
    trade_id = TradeId.generate()
    market_condition = field("market_condition", required=True, phase=CustomFieldPhase.OPEN)
    breakout_quality = field("breakout_quality", phase=CustomFieldPhase.OPEN)
    day = field("day_of_week", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.TEXT)
    position = field("position_value", source=CustomFieldSource.DERIVED, value_type=CustomFieldValueType.NUMBER)
    exchange = field("bybit_fee_quality", source=CustomFieldSource.EXCHANGE)
    scopes = [
        CustomFieldScope.global_scope(market_condition.id),
        CustomFieldScope.create(breakout_quality.id, strategy_code="LONG_CONTINUATION", setup_code="BREAKOUT"),
        CustomFieldScope.global_scope(day.id),
        CustomFieldScope.global_scope(position.id),
        CustomFieldScope.create(exchange.id, exchange="BYBIT"),
    ]
    service = TradeEnrichmentService()
    first = service.enrich(
        [market_condition, breakout_quality, day, position, exchange],
        scopes,
        [],
        _resolution_context(),
        context(),
        trade_id=trade_id,
        recorded_at=NOW,
    )
    assert first.status is TradeEnrichmentStatus.PENDING
    assert first.missing_manual_required == (market_condition,)
    assert first.missing_manual_optional == (breakout_quality,)
    assert [v.field_id for v in first.generated_values] == [day.id, position.id]
    assert [issue.field for issue in first.unavailable_auto_fields] == [exchange]

    second = service.enrich(
        [market_condition, breakout_quality, day, position, exchange],
        scopes,
        [value(trade_id, market_condition, "TREND")],
        _resolution_context(),
        context(),
        trade_id=trade_id,
        recorded_at=NOW,
    )
    assert second.status is TradeEnrichmentStatus.COMPLETE


def test_post_trade_scenario_uses_resolver_phase_and_completes_after_review():
    trade_id = TradeId.generate()
    review = field("trade_review", required=True, phase=CustomFieldPhase.POST_TRADE)
    psychology = field("psychology", phase=CustomFieldPhase.POST_TRADE)
    duration = field("holding_duration", source=CustomFieldSource.DERIVED, phase=CustomFieldPhase.POST_TRADE, value_type=CustomFieldValueType.NUMBER)
    result_r = field("result_r", source=CustomFieldSource.DERIVED, phase=CustomFieldPhase.POST_TRADE, value_type=CustomFieldValueType.NUMBER)
    closed = context(closed_at=datetime(2026, 6, 1, 11, 30, tzinfo=timezone.utc), risk=Decimal("10"), net_pnl=Decimal("25"))
    service = TradeEnrichmentService()
    first = service.enrich(
        [review, psychology, duration, result_r], [], [], _resolution_context(CustomFieldPhase.POST_TRADE), closed,
        trade_id=trade_id, recorded_at=NOW,
    )
    assert first.status is TradeEnrichmentStatus.PENDING
    assert [v.field_id for v in first.generated_values] == [duration.id, result_r.id]
    second = service.enrich(
        [review, psychology, duration, result_r], [], [value(trade_id, review, "good")],
        _resolution_context(CustomFieldPhase.POST_TRADE), closed, trade_id=trade_id, recorded_at=NOW,
    )
    assert second.status is TradeEnrichmentStatus.COMPLETE
