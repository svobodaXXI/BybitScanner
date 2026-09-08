from datetime import datetime, timezone
from decimal import Decimal

from app.core.automatic_data import AutomaticFactorAvailability, AutomaticFactorObservation, AutomaticFactorQuality, AutomaticFactorSourceKind, AutomaticFactorValueType, CaptureSemantics
from app.core.trades.trade_id import TradeId
from app.infrastructure.persistence.mappers import automatic_observation_from_orm, automatic_observation_to_orm


def test_generic_observation_mapper_round_trip_preserves_value_quality_capability_and_provenance():
    source = AutomaticFactorObservation(
        trade_id=TradeId.generate(), factor_id="funding_rate", value_type=AutomaticFactorValueType.DECIMAL,
        value=Decimal("0.001"), unit="rate", currency="usdt", source_kind=AutomaticFactorSourceKind.EXCHANGE,
        provider_key="exchange-x", capture_semantics=CaptureSemantics.AT_ENTRY,
        captured_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        quality_status=AutomaticFactorQuality.ESTIMATED,
        availability_status=AutomaticFactorAvailability.AVAILABLE,
        provenance={"request_id": "abc"},
    )
    restored = automatic_observation_from_orm(automatic_observation_to_orm(source))
    assert restored.trade_id == source.trade_id
    assert restored.factor_id == source.factor_id
    assert restored.value == source.value
    assert restored.quality_status is AutomaticFactorQuality.ESTIMATED
    assert restored.availability_status is AutomaticFactorAvailability.AVAILABLE
    assert restored.provenance == {"request_id": "abc"}
