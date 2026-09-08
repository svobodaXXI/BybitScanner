import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.application.automatic_market_data import (
    AutomaticTradeDataCapture,
    MarketDataPoint,
    MarketDataSnapshot,
    PostTradeMarketSnapshot,
)
from app.core.accounts.account_id import AccountId
from app.core.automatic_data import (
    AutomaticFactorAvailability,
    AutomaticFactorQuality,
    AutomaticFactorValueType,
    AutomaticObservationValueType,
    DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
)
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 9, 7, 12, 34, 56, 123000, tzinfo=timezone.utc)


def trade(*, closed=False):
    item = Trade.open(
        account_id=AccountId.generate(), instrument_id=InstrumentId.generate(),
        direction=TradeDirection.LONG, entry_price=Price("100"), quantity=Quantity("2"),
        opened_at=NOW, currency="USDT", trade_id=TradeId.generate(),
    )
    if closed:
        item.close(Price("101"), NOW + timedelta(hours=1, seconds=2, microseconds=500000))
    return item


class ObservationRepository:
    def __init__(self, observations=()):
        self.observations = list(observations)

    async def list_for_trade(self, trade_id):
        return tuple(item for item in self.observations if item.trade_id == trade_id)

    async def save(self, observation):
        identity = (observation.factor_id, observation.definition_version, observation.calculation_version, observation.capture_semantics)
        for index, current in enumerate(self.observations):
            current_identity = (current.factor_id, current.definition_version, current.calculation_version, current.capture_semantics)
            if current.trade_id == observation.trade_id and current_identity == identity:
                if current.value is None and observation.value is not None:
                    self.observations[index] = observation
                return
        self.observations.append(observation)


class Provider:
    provider_key = "TEST_MARKET"

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    async def get_entry_snapshot(self, instrument_id, as_of, *, factor_ids=()):
        self.calls.append((instrument_id, as_of, factor_ids))
        return self.snapshot


def run(coro):
    return asyncio.run(coro)


def test_registry_contains_v1_factors_and_capture_is_as_of_opened_at():
    expected = {
        "holding_duration_seconds", "entry_hour", "entry_day_of_week",
        "volume_1d_at_entry", "turnover_1d_at_entry", "previous_day_volume",
        "previous_day_turnover", "avg_volume_prev_5d", "avg_turnover_prev_5d", "rvol_at_entry",
        "market_price_at_entry_snapshot", "day_open_price", "day_high_at_entry", "day_low_at_entry",
        "day_change_pct_at_entry", "day_range_pct_at_entry", "day_range_position_at_entry",
        "atr_1d_14", "atr_1d_14_pct", "day_range_to_atr", "vwap_1d_at_entry",
        "distance_to_vwap_pct", "change_24h_pct_at_entry",
        "open_interest_base_at_entry", "open_interest_notional_usdt_at_entry",
        "open_interest_change_1h_pct_at_entry", "open_interest_change_4h_pct_at_entry",
        "open_interest_change_24h_pct_at_entry", "last_settled_funding_rate_at_entry",
        "avg_last_3_settled_funding_rate_at_entry", "funding_interval_minutes_inferred_at_entry",
        "minutes_since_last_funding_at_entry", "minutes_to_next_funding_inferred_at_entry",
        "mark_price_at_entry_snapshot", "index_price_at_entry_snapshot", "mark_index_basis_pct_at_entry",
        "mae_observed_1m_extreme_price", "mfe_observed_1m_extreme_price",
        "mae_observed_1m_price_distance", "mfe_observed_1m_price_distance",
        "mae_observed_1m_pct", "mfe_observed_1m_pct",
        "mae_observed_1m_gross_pnl_usdt", "mfe_observed_1m_gross_pnl_usdt",
        "exit_directional_move_price_signed", "exit_directional_move_pct_signed",
        "exit_efficiency_pct_of_observed_mfe", "profit_capture_pct_of_observed_mfe",
        "mfe_giveback_price_distance", "mfe_giveback_pct_of_observed_mfe",
        "mfe_giveback_pct_of_entry", "mfe_giveback_gross_pnl_usdt",
    }
    assert {item.factor_id for item in DEFAULT_AUTOMATIC_FACTOR_REGISTRY} == expected
    item = trade()
    market_ids = tuple(item.factor_id for item in DEFAULT_AUTOMATIC_FACTOR_REGISTRY if item.source_kind.value == "MARKET_DATA")
    entry_market_ids = tuple(
        item.factor_id for item in DEFAULT_AUTOMATIC_FACTOR_REGISTRY
        if item.source_kind.value == "MARKET_DATA" and item.capture_semantics.value != "POST_TRADE"
    )
    snapshot = MarketDataSnapshot(
        item.instrument_id, NOW,
        {factor_id: MarketDataPoint(
            10 if factor_id == "funding_interval_minutes_inferred_at_entry" else Decimal("10"),
            source_timestamp=NOW, provenance={"fixture": True},
        ) for factor_id in entry_market_ids},
        "TEST_MARKET",
    )
    provider = Provider(snapshot)
    repository = ObservationRepository()
    captured = run(AutomaticTradeDataCapture(provider).capture(item, repository, captured_at=NOW + timedelta(days=1)))

    assert provider.calls == [(item.instrument_id, NOW, entry_market_ids)]
    assert {value.factor_id for value in captured} == {
        "entry_hour", "entry_day_of_week", *entry_market_ids,
    }
    assert next(value for value in captured if value.factor_id == "entry_hour").value == 12
    assert next(value for value in captured if value.factor_id == "entry_day_of_week").value == 1
    assert all(value.source_timestamp == NOW for value in captured)
    assert all(value.captured_at == NOW + timedelta(days=1) for value in captured)


def test_entry_hour_preserves_legacy_local_timezone_identity():
    definition = DEFAULT_AUTOMATIC_FACTOR_REGISTRY.require("entry_hour")
    assert definition.definition_version == 1
    assert definition.calculation_version == "1"
    assert "локальному времени пользователя" in definition.description

    item = trade()
    repository = ObservationRepository()
    captured = run(AutomaticTradeDataCapture(
        entry_timezone=timezone(timedelta(hours=3), "UTC+03")
    ).capture(item, repository, captured_at=NOW))
    entry_hour = next(value for value in captured if value.factor_id == "entry_hour")
    assert entry_hour.value == 15
    assert entry_hour.definition_version == 1
    assert entry_hour.calculation_version == "1"
    assert entry_hour.provenance["timezone"] == "UTC+03"


def test_full_close_persists_exact_duration_and_repeated_capture_is_idempotent():
    item = trade(closed=True)
    repository = ObservationRepository()
    capture = AutomaticTradeDataCapture()
    first = run(capture.capture(item, repository, captured_at=NOW))
    second = run(capture.capture(item, repository, captured_at=NOW + timedelta(days=1)))

    duration = next(value for value in first if value.factor_id == "holding_duration_seconds")
    assert duration.value == Decimal("3602.5")
    assert duration.value_type is AutomaticObservationValueType.DECIMAL
    assert duration.definition_version == 2
    assert duration.calculation_version == "2"
    definition = DEFAULT_AUTOMATIC_FACTOR_REGISTRY.require("holding_duration_seconds")
    assert definition.value_type is AutomaticFactorValueType.DECIMAL
    assert definition.definition_version == 2
    assert definition.calculation_version == "2"
    assert duration.quality_status is AutomaticFactorQuality.VALID
    assert second == ()
    assert len(repository.observations) == 11


def test_closed_trade_uses_post_trade_provider_once_and_open_trade_never_requests_it():
    class ProviderWithPostTrade(Provider):
        def __init__(self, snapshot):
            super().__init__(snapshot)
            self.post_calls = []

        async def get_post_trade_snapshot(self, context, *, factor_ids=()):
            self.post_calls.append((context, factor_ids))
            return PostTradeMarketSnapshot(
                context.instrument_id, context.opened_at, context.closed_at,
                {factor_id: MarketDataPoint(
                    10 if factor_id == "funding_interval_minutes_inferred_at_entry" else Decimal("10"),
                    source_timestamp=context.closed_at,
                )
                 for factor_id in factor_ids},
                self.provider_key,
            )

    item = trade(closed=True)
    entry_ids = tuple(
        definition.factor_id for definition in DEFAULT_AUTOMATIC_FACTOR_REGISTRY
        if definition.source_kind.value == "MARKET_DATA"
        and definition.capture_semantics.value != "POST_TRADE"
    )
    entry_snapshot = MarketDataSnapshot(
        item.instrument_id, NOW,
        {factor_id: MarketDataPoint(
            10 if factor_id == "funding_interval_minutes_inferred_at_entry" else Decimal("10"),
            source_timestamp=NOW,
        ) for factor_id in entry_ids},
        "TEST_MARKET",
    )
    provider = ProviderWithPostTrade(entry_snapshot)
    repository = ObservationRepository()
    capture = AutomaticTradeDataCapture(provider)
    first = run(capture.capture(item, repository, captured_at=NOW))
    second = run(capture.capture(item, repository, captured_at=NOW + timedelta(days=1)))

    assert len(provider.post_calls) == 1
    assert set(provider.post_calls[0][1]) == {
        definition.factor_id for definition in DEFAULT_AUTOMATIC_FACTOR_REGISTRY
        if definition.capture_semantics.value == "POST_TRADE"
        and definition.source_kind.value == "MARKET_DATA"
    }
    assert {value.factor_id for value in first} >= set(provider.post_calls[0][1])
    assert second == ()

    open_item = trade()
    open_provider = ProviderWithPostTrade(entry_snapshot)
    run(AutomaticTradeDataCapture(open_provider).capture(open_item, ObservationRepository()))
    assert open_provider.post_calls == []


def test_provider_missing_values_are_missing_and_can_be_repaired_without_duplicates():
    item = trade()
    market_id = "volume_1d_at_entry"
    missing = MarketDataSnapshot(
        item.instrument_id, NOW,
        {market_id: MarketDataPoint(
            None,
            quality_status=AutomaticFactorQuality.MISSING,
            availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        )},
        "TEST_MARKET",
    )
    provider = Provider(missing)
    repository = ObservationRepository()
    capture = AutomaticTradeDataCapture(provider)
    run(capture.capture(item, repository))
    observation = next(value for value in repository.observations if value.factor_id == market_id)
    assert observation.value is None
    assert observation.quality_status is AutomaticFactorQuality.MISSING

    provider.snapshot = MarketDataSnapshot(item.instrument_id, NOW, {market_id: MarketDataPoint(Decimal("42"))}, "TEST_MARKET")
    run(capture.capture(item, repository))
    repaired = next(value for value in repository.observations if value.factor_id == market_id)
    assert repaired.value == Decimal("42")
    assert len([value for value in repository.observations if value.factor_id == market_id]) == 1
