from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.common.risk import Risk
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldPhase,
    CustomFieldSource,
    CustomFieldValueType,
    DerivedValueConfigurationError,
    DerivedValueContext,
    DerivedValueService,
    DerivedValueStatus,
    TradingSessionRule,
)


UTC = timezone.utc
OPENED = datetime(2026, 5, 4, 14, 15, tzinfo=UTC)  # Monday


def derived_field(code, value_type=CustomFieldValueType.NUMBER):
    return CustomFieldDefinition.create(
        code=code,
        name=code.replace("_", " ").title(),
        value_type=value_type,
        source=CustomFieldSource.DERIVED,
        phase=CustomFieldPhase.ANY,
        created_at=OPENED,
    )


def context(**overrides):
    values = {
        "opened_at": OPENED,
        "entry_price": Price(100),
        "quantity": Quantity(2),
    }
    values.update(overrides)
    return DerivedValueContext(**values)


def test_result_contract_has_three_explicit_states():
    service = DerivedValueService()
    calculated = service.calculate(derived_field("position_value"), context())
    unavailable = service.calculate(derived_field("holding_duration"), context())
    unsupported = service.calculate(derived_field("future_metric"), context())

    assert calculated.status is DerivedValueStatus.CALCULATED
    assert calculated.value == Decimal("200")
    assert unavailable.status is DerivedValueStatus.NOT_AVAILABLE
    assert unavailable.value is None
    assert unsupported.status is DerivedValueStatus.UNSUPPORTED
    assert unsupported.value is None
    assert unsupported.reason


@pytest.mark.parametrize("code", ["day_of_week", "entry_hour", "position_value", "holding_duration", "stop_distance", "result_r"])
def test_non_derived_field_is_rejected(code):
    field = CustomFieldDefinition.create(
        code=code,
        name=code,
        value_type=CustomFieldValueType.TEXT if code == "day_of_week" else CustomFieldValueType.NUMBER,
        source=CustomFieldSource.MANUAL,
        created_at=OPENED,
    )
    with pytest.raises(DerivedValueConfigurationError):
        DerivedValueService().calculate(field, context())


def test_day_of_week_and_entry_hour_use_explicit_context_timezone():
    late_utc = datetime(2026, 5, 4, 23, 30, tzinfo=UTC)
    ctx = context(opened_at=late_utc, timezone=timezone(timedelta(hours=3), "UTC+03"))
    service = DerivedValueService()
    assert service.calculate(derived_field("day_of_week", CustomFieldValueType.TEXT), ctx).value == "TUESDAY"
    assert service.calculate(derived_field("entry_hour"), ctx).value == Decimal("2")


def test_naive_datetime_is_rejected_and_absent_timezone_does_not_use_machine_timezone():
    with pytest.raises(ValueError):
        context(opened_at=datetime(2026, 5, 4, 14, 15))
    # The context's own aware timezone is used when no explicit business timezone exists.
    local_time = datetime(2026, 5, 4, 14, 15, tzinfo=timezone(timedelta(hours=3), "UTC+03"))
    result = DerivedValueService().calculate(derived_field("entry_hour"), context(opened_at=local_time))
    assert result.value == Decimal("14")


def test_trading_session_config_is_explicit_and_supports_cross_midnight():
    service = DerivedValueService(
        session_rules=(
            TradingSessionRule("ASIA", time(0), time(8)),
            TradingSessionRule("EUROPE", time(8), time(16)),
            TradingSessionRule("US", time(16), time(23)),
        )
    )
    assert service.calculate(derived_field("trading_session", CustomFieldValueType.TEXT), context()).value == "EUROPE"
    assert service.calculate(
        derived_field("trading_session", CustomFieldValueType.TEXT),
        context(opened_at=datetime(2026, 5, 4, 23, 30, tzinfo=UTC)),
    ).status is DerivedValueStatus.NOT_AVAILABLE

    overnight = DerivedValueService(session_rules=(TradingSessionRule("OVERNIGHT", time(22), time(2)),))
    assert overnight.calculate(
        derived_field("trading_session", CustomFieldValueType.TEXT),
        context(opened_at=datetime(2026, 5, 5, 1, 30, tzinfo=UTC)),
    ).value == "OVERNIGHT"


def test_session_without_config_or_outside_config_is_not_available():
    field = derived_field("trading_session", CustomFieldValueType.TEXT)
    assert DerivedValueService().calculate(field, context()).status is DerivedValueStatus.NOT_AVAILABLE
    service = DerivedValueService(session_rules=(TradingSessionRule("EUROPE", "08:00", "16:00"),))
    result = service.calculate(field, context(opened_at=datetime(2026, 5, 4, 7, 59, tzinfo=UTC)))
    assert result.status is DerivedValueStatus.NOT_AVAILABLE
    assert "outside" in result.reason


def test_overlapping_session_rules_are_rejected():
    with pytest.raises(ValueError):
        DerivedValueService(
            session_rules=(
                TradingSessionRule("A", time(8), time(12)),
                TradingSessionRule("B", time(11), time(15)),
            )
        )
    with pytest.raises(ValueError):
        DerivedValueService().calculate(
            derived_field("trading_session", CustomFieldValueType.TEXT),
            context(session_rules=(TradingSessionRule("A", time(8), time(12)), TradingSessionRule("B", time(11), time(15)))),
        )


def test_position_value_uses_decimal_without_float():
    result = DerivedValueService().calculate(
        derived_field("position_value"),
        context(entry_price=Decimal("100.10"), quantity=Decimal("2.5")),
    )
    assert result.value == Decimal("250.250")
    with pytest.raises((TypeError, ValueError)):
        context(entry_price=1.25)


def test_holding_duration_is_decimal_minutes_and_open_trade_is_unavailable():
    field = derived_field("holding_duration")
    closed = context(closed_at=datetime(2026, 5, 4, 15, 45, tzinfo=UTC))
    assert DerivedValueService().calculate(field, closed).value == Decimal("90")
    assert DerivedValueService().calculate(field, context()).status is DerivedValueStatus.NOT_AVAILABLE


@pytest.mark.parametrize("entry, stop", [(100, 95), (100, 105)])
def test_stop_distance_is_absolute_and_direction_agnostic(entry, stop):
    result = DerivedValueService().calculate(
        derived_field("stop_distance"),
        context(entry_price=Price(entry), stop_price=Price(stop)),
    )
    assert result.value == Decimal("5")
    assert DerivedValueService().calculate(derived_field("stop_distance"), context()).status is DerivedValueStatus.NOT_AVAILABLE


@pytest.mark.parametrize(
    ("net_pnl", "risk", "expected"),
    [(Decimal("250"), Decimal("100"), Decimal("2.5")), (Decimal("-50"), Decimal("100"), Decimal("-0.5")), (Decimal("0"), Decimal("100"), Decimal("0"))],
)
def test_result_r_uses_net_pnl_and_risk(net_pnl, risk, expected):
    result = DerivedValueService().calculate(derived_field("result_r"), context(net_pnl=net_pnl, risk=risk))
    assert result.value == expected


def test_result_r_accepts_existing_risk_and_money_objects_and_missing_or_zero_is_unavailable():
    field = derived_field("result_r")
    service = DerivedValueService()
    ctx = context(net_pnl=Money(Decimal("25"), "USDT"), risk=Risk(Money(Decimal("10"), "USDT")))
    assert service.calculate(field, ctx).value == Decimal("2.5")
    assert service.calculate(field, context(net_pnl=Decimal("1"))).status is DerivedValueStatus.NOT_AVAILABLE
    assert service.calculate(field, context(net_pnl=Decimal("1"), risk=Decimal("0"))).status is DerivedValueStatus.NOT_AVAILABLE


def test_dynamic_field_type_compatibility_is_explicit():
    service = DerivedValueService()
    with pytest.raises(DerivedValueConfigurationError):
        service.calculate(derived_field("position_value", CustomFieldValueType.TEXT), context())
    with pytest.raises(DerivedValueConfigurationError):
        service.calculate(derived_field("day_of_week"), context())


def test_realistic_journal_context_calculates_all_supported_values():
    ctx = context(
        closed_at=datetime(2026, 5, 4, 15, 45, tzinfo=UTC),
        entry_price=Price(100),
        quantity=Quantity(2),
        stop_price=Price(95),
        risk=Decimal("10"),
        net_pnl=Decimal("25"),
    )
    service = DerivedValueService(session_rules=(TradingSessionRule("EUROPE", time(8), time(16)),))
    values = {
        code: service.calculate(
            derived_field(code, CustomFieldValueType.TEXT if code in {"day_of_week", "trading_session"} else CustomFieldValueType.NUMBER),
            ctx,
        ).value
        for code in ("day_of_week", "entry_hour", "trading_session", "position_value", "holding_duration", "stop_distance", "result_r")
    }
    assert values == {
        "day_of_week": "MONDAY",
        "entry_hour": Decimal("14"),
        "trading_session": "EUROPE",
        "position_value": Decimal("200"),
        "holding_duration": Decimal("90"),
        "stop_distance": Decimal("5"),
        "result_r": Decimal("2.5"),
    }
