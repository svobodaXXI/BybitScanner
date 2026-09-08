import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from app.application.dtos import GetTradeDetailsCommand
from app.application.use_cases.get_trade_details import GetTradeDetails
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


NOW = datetime(2026, 9, 7, 12, 34, tzinfo=timezone.utc)


def run(coroutine):
    return asyncio.run(coroutine)


def make_trade(*, closed=False):
    trade = Trade.open(
        account_id=AccountId.generate(), instrument_id=InstrumentId.generate(),
        direction=TradeDirection.LONG, entry_price=Price("100"), quantity=Quantity("2"),
        opened_at=NOW, currency="USDT", fees=Money("0", "USDT"), trade_id=TradeId.generate(),
    )
    if closed:
        trade.close(Price("101"), datetime(2026, 9, 7, 14, 9, tzinfo=timezone.utc))
    return trade


class TradeRepository:
    def __init__(self, trade):
        self.trade = trade

    async def get_by_id(self, trade_id):
        return self.trade if trade_id == self.trade.trade_id else None


class EmptyFields:
    async def list_definitions(self, *, include_inactive=False):
        return ()


class EmptyValues:
    async def list_by_trade(self, trade_id):
        return ()


class AutomaticRepository:
    def __init__(self, observations):
        self.observations = tuple(observations)

    async def list_for_trade(self, trade_id):
        return tuple(item for item in self.observations if item.trade_id == trade_id)


def observation(trade, factor_id, value, *, definition_version=1, calculation_version="1", quality=AutomaticFactorQuality.VALID):
    value_type = AutomaticObservationValueType.INTEGER if factor_id == "entry_day_of_week" else AutomaticObservationValueType.DECIMAL
    return AutomaticFactorObservation(
        trade_id=trade.trade_id,
        factor_id=factor_id,
        definition_version=definition_version,
        calculation_version=calculation_version,
        value_type=value_type,
        value=value,
        unit="seconds" if factor_id == "holding_duration_seconds" else None,
        source_kind=AutomaticFactorSourceKind.DERIVED if factor_id == "holding_duration_seconds" else AutomaticFactorSourceKind.MARKET_DATA,
        provider_key="TEST_PROVIDER",
        capture_semantics=CaptureSemantics.POST_TRADE if factor_id == "holding_duration_seconds" else CaptureSemantics.AT_ENTRY,
        captured_at=NOW,
        source_timestamp=NOW,
        quality_status=quality,
        availability_status=AutomaticFactorAvailability.AVAILABLE if quality is AutomaticFactorQuality.VALID else AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        provenance={"internal": "not for UI"},
    )


def test_get_trade_details_returns_current_versioned_automatic_observations():
    trade = make_trade(closed=True)
    repository = AutomaticRepository((
        observation(trade, "entry_day_of_week", 1),
        observation(trade, "holding_duration_seconds", Decimal("60"), definition_version=1),
        observation(trade, "holding_duration_seconds", Decimal("5700"), definition_version=2, calculation_version="2"),
    ))

    result = run(GetTradeDetails(
        TradeRepository(trade), EmptyFields(), EmptyValues(),
        automatic_observation_repository=repository,
    ).execute(GetTradeDetailsCommand(trade.trade_id)))

    assert [item.factor_id for item in result.automatic_observations] == [
        "holding_duration_seconds", "entry_day_of_week",
    ]
    duration = next(item for item in result.automatic_observations if item.factor_id == "holding_duration_seconds")
    assert duration.value == Decimal("5700")
    assert duration.definition_version == 2
    assert duration.calculation_version == "2"

