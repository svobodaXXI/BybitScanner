from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.automatic_data import AutomaticFactorQueryService
from app.core.automatic_data import (
    AutomaticFactorAvailability,
    AutomaticFactorBucketPolicy,
    AutomaticFactorCategory,
    AutomaticFactorDefinition,
    AutomaticFactorObservation,
    AutomaticFactorQuality,
    AutomaticFactorRegistry,
    AutomaticFactorSourceKind,
    AutomaticFactorValueType,
    CaptureSemantics,
)
from app.core.trades.trade_id import TradeId


def definition(factor_id="atr"):
    return AutomaticFactorDefinition(
        factor_id, "ATR", "Average true range", AutomaticFactorCategory.VOLATILITY_RANGE,
        AutomaticFactorValueType.DECIMAL, unit="price", source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR, supports_filter=True,
    )


def observation(trade_id, value, quality=AutomaticFactorQuality.VALID):
    return AutomaticFactorObservation(
        trade_id=trade_id, factor_id="atr", value_type=AutomaticFactorValueType.DECIMAL,
        value=value, source_kind=AutomaticFactorSourceKind.MARKET_DATA,
        capture_semantics=CaptureSemantics.PREVIOUS_CLOSED_BAR,
        captured_at=datetime(2026, 9, 1, tzinfo=timezone.utc), quality_status=quality,
        availability_status=AutomaticFactorAvailability.AVAILABLE, provenance={"source": "test"},
    )


def test_registry_is_stable_and_rejects_duplicate_factor_ids():
    with pytest.raises(ValueError, match="unique"):
        AutomaticFactorRegistry((definition(), definition()))
    assert AutomaticFactorRegistry((definition(),)).require("atr").category_id is AutomaticFactorCategory.VOLATILITY_RANGE


def test_observation_validates_metadata_and_keeps_missing_distinct_from_zero():
    missing = observation(TradeId.generate(), None, AutomaticFactorQuality.MISSING)
    zero = observation(TradeId.generate(), Decimal("0"))
    assert missing.value is None and missing.quality_status is AutomaticFactorQuality.MISSING
    assert zero.value == Decimal("0") and zero.quality_status is AutomaticFactorQuality.VALID
    with pytest.raises(ValueError):
        AutomaticFactorObservation(trade_id=TradeId.generate(), factor_id="x", value_type="DECIMAL", value=1, source_kind="DERIVED", capture_semantics="AT_ENTRY", captured_at=datetime.now(timezone.utc), quality_status="BOGUS")


class FakeRepository:
    def __init__(self, items): self.items = tuple(items)
    async def list(self, factor_id, trade_ids=()): return tuple(item for item in self.items if item.factor_id == factor_id)


def test_generic_factor_query_supports_coverage_and_bucket_without_factor_methods():
    first, second = TradeId.generate(), TradeId.generate()
    service = AutomaticFactorQueryService(FakeRepository((observation(first, 1), observation(second, None, AutomaticFactorQuality.MISSING))), AutomaticFactorRegistry((definition(),)))
    import asyncio
    coverage = asyncio.run(service.coverage("atr", trade_ids=(first, second)))
    buckets = asyncio.run(service.bucket("atr", trade_ids=(first, second), policy=AutomaticFactorBucketPolicy.FIXED_BINS, bins=(1,)))
    assert coverage["calculated"] == 1 and coverage["missing"] == 1
    assert list(buckets) == [0]
