from datetime import datetime, timezone
from decimal import Decimal

from app.application.dtos import GetTradeDetailsResult, InstrumentView, TradeView
from app.core.accounts.account_id import AccountId
from app.core.automatic_data import (
    AutomaticFactorAvailability,
    AutomaticFactorObservation,
    AutomaticFactorQuality,
    AutomaticFactorSourceKind,
    AutomaticObservationValueType,
    CaptureSemantics,
)
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId
from app.telegram.formatting import _duration_text, details_text


NOW = datetime(2026, 9, 7, 12, 34, tzinfo=timezone.utc)


def make_trade(*, closed=False):
    trade = Trade.open(
        account_id=AccountId.generate(), instrument_id=InstrumentId.generate(),
        direction=TradeDirection.SHORT, entry_price=Price("100"), quantity=Quantity("2"),
        opened_at=NOW, currency="USDT", fees=Money("0", "USDT"), trade_id=TradeId.generate(),
    )
    if closed:
        trade.close(Price("99"), datetime(2026, 9, 7, 14, 9, tzinfo=timezone.utc))
    return trade


def observation(trade, factor_id, value, *, unit=None, currency=None, quality=AutomaticFactorQuality.VALID):
    integer = factor_id == "entry_day_of_week"
    return AutomaticFactorObservation(
        trade_id=trade.trade_id,
        factor_id=factor_id,
        definition_version=1,
        calculation_version="1",
        value_type=AutomaticObservationValueType.INTEGER if integer else AutomaticObservationValueType.DECIMAL,
        value=value,
        unit=unit,
        currency=currency,
        source_kind=AutomaticFactorSourceKind.MARKET_DATA if not integer else AutomaticFactorSourceKind.DERIVED,
        provider_key="INTERNAL_TEST_PROVIDER",
        capture_semantics=CaptureSemantics.AT_ENTRY,
        captured_at=NOW,
        source_timestamp=NOW,
        quality_status=quality,
        availability_status=AutomaticFactorAvailability.AVAILABLE if quality is AutomaticFactorQuality.VALID else AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        provenance={"should_not": "be rendered"},
    )


def details(trade, observations):
    instrument = InstrumentView(trade.instrument_id, "4USDT", "4 / USDT", "BYBIT", "LINEAR", True)
    return details_text(GetTradeDetailsResult(
        TradeView.from_trade(trade), (), instrument,
        automatic_observations=tuple(observations),
    ))


def test_closed_trade_renders_russian_automatic_factors_and_duration():
    trade = make_trade(closed=True)
    text = details(trade, (
        observation(trade, "entry_day_of_week", 1),
        observation(trade, "volume_1d_at_entry", Decimal("178020290.000000"), unit="base"),
        observation(trade, "turnover_1d_at_entry", Decimal("4364728.81728"), unit="USDT", currency="USDT"),
        observation(trade, "avg_volume_prev_5d", Decimal("475170829.200000"), unit="base"),
        observation(trade, "previous_day_volume", None, unit="base", quality=AutomaticFactorQuality.MISSING),
        observation(trade, "previous_day_turnover", Decimal("11327863.176869"), unit="USDT", currency="USDT"),
        observation(trade, "avg_turnover_prev_5d", Decimal("11582162.105239"), unit="USDT", currency="USDT"),
        observation(trade, "rvol_at_entry", Decimal("1.835"), unit="ratio"),
        observation(trade, "holding_duration_seconds", Decimal("5713"), unit="seconds"),
    ))

    assert "Автоданные" in text
    assert "День недели входа: Понедельник" in text
    assert "Дневной объём к входу: 178 020 290" in text
    assert "Дневной оборот к входу: 4 364 728.82 USDT" in text
    assert "Оборот предыдущего дня: 11 327 863.18 USDT" in text
    assert "Средний объём за 5 дней: 475 170 829.2" in text
    assert "Средний оборот за 5 дней: 11 582 162.11 USDT" in text
    assert "Объём предыдущего дня: —" in text
    assert "RVOL на входе: 1.84x" in text
    assert "Длительность сделки: 1 ч 35 мин 13 сек" in text
    assert "MARKET_DATA" not in text
    assert "INTERNAL_TEST_PROVIDER" not in text
    assert "provenance" not in text
    assert "volume_1d_at_entry" not in text


def test_open_trade_renders_missing_as_dash_and_does_not_show_duration():
    trade = make_trade()
    text = details(trade, (
        observation(trade, "volume_1d_at_entry", Decimal("123")),
        observation(trade, "rvol_at_entry", Decimal("1.84"), unit="ratio"),
        observation(trade, "previous_day_volume", None, quality=AutomaticFactorQuality.MISSING),
    ))

    assert "Дневной объём к входу: 123" in text
    assert "RVOL на входе: 1.84x" in text
    assert "Объём предыдущего дня: —" in text
    assert "Длительность сделки:" not in text
    assert "Объём предыдущего дня: 0" not in text


def test_duration_always_keeps_seconds_and_truncates_fractional_second_for_ui():
    assert _duration_text(Decimal("42")) == "42 сек"
    assert _duration_text(Decimal("187.024")) == "3 мин 07 сек"
    assert _duration_text(Decimal("1873")) == "31 мин 13 сек"
    assert _duration_text(Decimal("5713")) == "1 ч 35 мин 13 сек"
