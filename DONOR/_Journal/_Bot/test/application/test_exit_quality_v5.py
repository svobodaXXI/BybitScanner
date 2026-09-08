import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

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
    AutomaticFactorRegistry,
    CaptureSemantics,
    DEFAULT_AUTOMATIC_FACTOR_REGISTRY,
)
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments import InstrumentId
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 9, 7, 12, 34, 56, 123000, tzinfo=timezone.utc)
V4_ID = "mfe_observed_1m_price_distance"
V5_IDS = (
    "exit_directional_move_price_signed", "exit_directional_move_pct_signed",
    "exit_efficiency_pct_of_observed_mfe", "profit_capture_pct_of_observed_mfe",
    "mfe_giveback_price_distance", "mfe_giveback_pct_of_observed_mfe",
    "mfe_giveback_pct_of_entry", "mfe_giveback_gross_pnl_usdt",
)


class ObservationRepository:
    def __init__(self, observations=()):
        self.observations = list(observations)

    async def list_for_trade(self, trade_id):
        return tuple(item for item in self.observations if item.trade_id == trade_id)

    async def save(self, observation):
        identity = (
            observation.trade_id, observation.factor_id, observation.definition_version,
            observation.calculation_version, observation.capture_semantics,
        )
        for index, current in enumerate(self.observations):
            current_identity = (
                current.trade_id, current.factor_id, current.definition_version,
                current.calculation_version, current.capture_semantics,
            )
            if current_identity != identity:
                continue
            if current.value is None and observation.value is not None:
                self.observations[index] = observation
            return
        self.observations.append(observation)


class Provider:
    provider_key = "TEST_MARKET"

    def __init__(self, mfe):
        self.mfe = mfe
        self.post_calls = []

    async def get_entry_snapshot(self, instrument_id, as_of, *, factor_ids=()):
        return MarketDataSnapshot(instrument_id, as_of, {}, self.provider_key)

    async def get_post_trade_snapshot(self, context, *, factor_ids=()):
        self.post_calls.append(tuple(factor_ids))
        points = {}
        if V4_ID in factor_ids:
            points[V4_ID] = MarketDataPoint(
                self.mfe,
                unit="USDT",
                source_timestamp=context.opened_at,
                provenance={"fixture": True},
            )
        return PostTradeMarketSnapshot(
            context.instrument_id, context.opened_at, context.closed_at,
            points, self.provider_key,
        )


def registry():
    definitions = [DEFAULT_AUTOMATIC_FACTOR_REGISTRY.require(V4_ID)]
    definitions.extend(
        definition for definition in DEFAULT_AUTOMATIC_FACTOR_REGISTRY
        if definition.factor_id in V5_IDS
    )
    return AutomaticFactorRegistry(definitions)


def make_trade(direction, exit_price):
    item = Trade.open(
        account_id=AccountId.generate(), instrument_id=InstrumentId.generate(),
        direction=direction, entry_price=Price("100"), quantity=Quantity("2"),
        opened_at=NOW, currency="USDT", trade_id=TradeId.generate(),
    )
    item.close(Price(str(exit_price)), NOW + timedelta(minutes=10))
    return item


def capture(trade, mfe, repository=None, provider=None):
    provider = provider or Provider(Decimal(str(mfe)))
    repository = repository or ObservationRepository()
    result = asyncio.run(
        AutomaticTradeDataCapture(provider, registry()).capture(trade, repository, captured_at=NOW)
    )
    return result, repository, provider


def values(repository):
    return {item.factor_id: item for item in repository.observations if item.factor_id in V5_IDS}


@pytest.mark.parametrize("direction", [TradeDirection.LONG, TradeDirection.SHORT])
def test_long_and_short_exit_quality_formulas(direction):
    item = make_trade(direction, "110" if direction is TradeDirection.LONG else "90")
    _, repository, _ = capture(item, "15")
    points = values(repository)

    assert points["exit_directional_move_price_signed"].value == Decimal("10")
    assert points["exit_directional_move_pct_signed"].value == Decimal("10")
    assert points["exit_efficiency_pct_of_observed_mfe"].value == Decimal("200") / Decimal("3")
    assert points["profit_capture_pct_of_observed_mfe"].value == Decimal("200") / Decimal("3")
    assert points["mfe_giveback_price_distance"].value == Decimal("5")
    assert points["mfe_giveback_pct_of_observed_mfe"].value == Decimal("100") / Decimal("3")
    assert points["mfe_giveback_pct_of_entry"].value == Decimal("5")
    assert points["mfe_giveback_gross_pnl_usdt"].value == Decimal("10")

    for point in points.values():
        assert point.source_timestamp == item.closed_at
        assert point.provenance["semantic"] == "exit_quality_from_observed_1m_mfe_v1"
        assert point.provenance["dependency"] == {
            "factor_id": V4_ID,
            "definition_version": 1,
            "calculation_version": "1",
            "capture_semantics": "POST_TRADE",
            "source_timestamp": NOW.isoformat(),
            "value": "15",
        }


def test_exit_exactly_at_mfe_has_full_efficiency_and_no_giveback():
    _, repository, _ = capture(make_trade(TradeDirection.LONG, "115"), "15")
    points = values(repository)
    assert points["exit_efficiency_pct_of_observed_mfe"].value == Decimal("100")
    assert points["profit_capture_pct_of_observed_mfe"].value == Decimal("100")
    assert points["mfe_giveback_price_distance"].value == Decimal("0")


def test_exit_at_entry_and_losing_exit_show_zero_and_over_100_giveback():
    _, at_entry_repo, _ = capture(make_trade(TradeDirection.LONG, "100"), "15")
    at_entry = values(at_entry_repo)
    assert at_entry["exit_efficiency_pct_of_observed_mfe"].value == Decimal("0")
    assert at_entry["profit_capture_pct_of_observed_mfe"].value == Decimal("0")
    assert at_entry["mfe_giveback_pct_of_observed_mfe"].value == Decimal("100")

    _, losing_repo, _ = capture(make_trade(TradeDirection.LONG, "95"), "15")
    losing = values(losing_repo)
    assert losing["exit_efficiency_pct_of_observed_mfe"].value == -Decimal("100") / Decimal("3")
    assert losing["profit_capture_pct_of_observed_mfe"].value == Decimal("0")
    assert losing["mfe_giveback_pct_of_observed_mfe"].value == Decimal("400") / Decimal("3")


def test_zero_mfe_preserves_valid_zero_and_calculates_non_denominator_factors():
    _, repository, _ = capture(make_trade(TradeDirection.LONG, "98"), "0")
    points = values(repository)
    assert points["exit_directional_move_price_signed"].value == Decimal("-2")
    assert points["exit_directional_move_pct_signed"].value == Decimal("-2")
    assert points["mfe_giveback_price_distance"].value == Decimal("2")
    assert points["mfe_giveback_pct_of_entry"].value == Decimal("2")
    assert points["mfe_giveback_gross_pnl_usdt"].value == Decimal("4")
    for factor_id in (
        "exit_efficiency_pct_of_observed_mfe", "profit_capture_pct_of_observed_mfe",
        "mfe_giveback_pct_of_observed_mfe",
    ):
        assert points[factor_id].value is None
        assert points[factor_id].quality_status is AutomaticFactorQuality.MISSING

    _, zero_repository, _ = capture(make_trade(TradeDirection.LONG, "100"), "0")
    zero = values(zero_repository)
    assert zero["exit_directional_move_price_signed"].value == Decimal("0")
    assert zero["mfe_giveback_price_distance"].value == Decimal("0")
    assert zero["mfe_giveback_gross_pnl_usdt"].value == Decimal("0")


def test_negative_mfe_and_d_greater_than_m_are_explicit_dependency_errors():
    _, negative_repository, _ = capture(make_trade(TradeDirection.LONG, "98"), "-1")
    negative = values(negative_repository)
    assert negative["exit_directional_move_price_signed"].value == Decimal("-2")
    assert negative["mfe_giveback_price_distance"].quality_status is AutomaticFactorQuality.ERROR
    assert negative["mfe_giveback_price_distance"].availability_status is AutomaticFactorAvailability.ERROR

    _, inconsistent_repository, _ = capture(make_trade(TradeDirection.LONG, "120"), "15")
    inconsistent = values(inconsistent_repository)
    assert inconsistent["exit_directional_move_price_signed"].value == Decimal("20")
    assert inconsistent["mfe_giveback_price_distance"].value is None
    assert inconsistent["mfe_giveback_price_distance"].provenance["reason"] == "inconsistent dependency: D > M"
    assert inconsistent["exit_directional_move_pct_signed"].value == Decimal("20")


def test_missing_v4_is_repairable_and_v5_derives_in_same_capture_call():
    trade_item = make_trade(TradeDirection.LONG, "110")
    repository = ObservationRepository()
    provider = Provider(None)
    capture_service = AutomaticTradeDataCapture(provider, registry())
    asyncio.run(capture_service.capture(trade_item, repository, captured_at=NOW))
    assert all(item.value is None for item in values(repository).values())
    assert all(item.source_timestamp == trade_item.closed_at for item in values(repository).values())

    provider.mfe = Decimal("10")
    second = asyncio.run(capture_service.capture(trade_item, repository, captured_at=NOW + timedelta(days=1)))
    assert values(repository)["exit_efficiency_pct_of_observed_mfe"].value == Decimal("100")
    assert {item.factor_id for item in second} >= set(V5_IDS)
    assert all(
        factor_id not in provider.post_calls[0]
        for factor_id in V5_IDS
    )
    assert all(
        sum(item.factor_id == factor_id for item in repository.observations) == 1
        for factor_id in (V4_ID, *V5_IDS)
    )


def test_stale_v4_version_is_not_used_instead_of_current_identity():
    item = make_trade(TradeDirection.LONG, "110")
    repository = ObservationRepository()
    current = DEFAULT_AUTOMATIC_FACTOR_REGISTRY.require(V4_ID)
    from app.core.automatic_data import AutomaticFactorObservation

    repository.observations.append(AutomaticFactorObservation(
        trade_id=item.trade_id, factor_id=V4_ID, definition_version=99,
        calculation_version="99", value_type="DECIMAL", value=Decimal("100"),
        unit="USDT", source_kind="MARKET_DATA", provider_key="OLD",
        capture_semantics=CaptureSemantics.POST_TRADE, captured_at=NOW,
        source_timestamp=NOW, provenance={"stale": True},
    ))
    _, repository, _ = capture(item, "10", repository=repository)
    efficiency = values(repository)["exit_efficiency_pct_of_observed_mfe"]
    assert efficiency.value == Decimal("100")
    assert efficiency.provenance["dependency"]["definition_version"] == current.definition_version
    assert efficiency.provenance["dependency"]["calculation_version"] == current.calculation_version
    assert efficiency.provenance["dependency"]["capture_semantics"] == current.capture_semantics.value


def test_open_trade_does_not_create_v5_observations():
    item = Trade.open(
        account_id=AccountId.generate(), instrument_id=InstrumentId.generate(),
        direction=TradeDirection.LONG, entry_price=Price("100"), quantity=Quantity("2"),
        opened_at=NOW, currency="USDT", trade_id=TradeId.generate(),
    )
    _, repository, provider = capture(item, "10")
    assert values(repository) == {}
    assert provider.post_calls == []
