import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application import (
    EnrichTradeWithMarketData,
    EnrichTradeWithMarketDataCommand,
    MarketDataContext,
    MarketDataFetchStatus,
)
from app.application.errors import MarketDataMappingError, MarketDataUnavailableError
from app.application.ports import MarketDataProvider
from app.core.accounts.account_id import AccountId
from app.core.common.money import Money
from app.core.common.price import Price
from app.core.common.quantity import Quantity
from app.core.instruments.instrument_id import InstrumentId
from app.core.statistics import (
    CustomFieldDefinition,
    CustomFieldPhase,
    CustomFieldSource,
    CustomFieldValueType,
    TradeCustomValue,
)
from app.core.trades.enums import TradeDirection
from app.core.trades.trade import Trade
from app.core.trades.trade_id import TradeId


NOW = datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)


def run(coroutine):
    return asyncio.run(coroutine)


def field(code, *, source, phase=CustomFieldPhase.ANY, value_type=CustomFieldValueType.NUMBER):
    return CustomFieldDefinition.create(
        code=code,
        name=code,
        value_type=value_type,
        source=source,
        phase=phase,
        created_at=NOW,
    )


def make_trade(*, closed=False):
    trade = Trade.open(
        account_id=AccountId.generate(),
        instrument_id=INSTRUMENT_ID,
        direction=TradeDirection.LONG,
        entry_price=Price(100),
        quantity=Quantity(2),
        opened_at=NOW,
        currency="USDT",
        trade_id=TradeId.generate(),
    )
    if closed:
        trade.close(Price(110), NOW + timedelta(hours=1))
    return trade


INSTRUMENT_ID = InstrumentId.generate()


class TradeRepo:
    def __init__(self, trade):
        self.trade = trade

    async def get_by_id(self, trade_id):
        return self.trade if self.trade.trade_id == trade_id else None


class FieldRepo:
    def __init__(self, definitions):
        self.definitions = tuple(definitions)

    async def list_definitions(self, *, include_inactive=False):
        return tuple(item for item in self.definitions if include_inactive or item.is_active)

    async def list_scopes(self, field_id=None):
        return ()


class ValueRepo:
    def __init__(self, existing=(), fail_on_add_number=None):
        self.values = list(existing)
        self.fail_on_add_number = fail_on_add_number
        self.add_count = 0

    async def list_by_trade(self, trade_id):
        return tuple(value for value in self.values if value.trade_id == trade_id)

    async def add(self, value):
        self.add_count += 1
        if self.fail_on_add_number == self.add_count:
            raise RuntimeError("forced value persistence failure")
        self.values.append(value)


class FakeUow:
    def __init__(self, trade, definitions, values):
        self.trades = TradeRepo(trade)
        self.custom_fields = FieldRepo(definitions)
        self.custom_values = values
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self):
        self._before = list(self.custom_values.values)
        self.committed = False
        self.rolled_back = False
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None or not self.committed:
            await self.rollback()

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True
        self.custom_values.values[:] = self._before


class ProviderFake:
    def __init__(self, context=None, error=None):
        self.context = context
        self.error = error
        self.calls = []

    async def get_trade_context(self, instrument_id, at, *, required_keys=()):
        self.calls.append((instrument_id, at, required_keys))
        if self.error is not None:
            raise self.error
        return self.context


def make_use_case(trade, definitions, provider, values=None):
    value_repo = values or ValueRepo()
    uow = FakeUow(trade, definitions, value_repo)
    return EnrichTradeWithMarketData(lambda: uow, provider), uow, value_repo


def test_market_data_context_is_utc_immutable_and_decimal_only():
    context = MarketDataContext(
        INSTRUMENT_ID,
        datetime(2026, 9, 3, 13, 0, tzinfo=timezone(timedelta(hours=3))),
        {" ATR_15M ": Decimal("1.25")},
    )

    assert context.as_of == datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc)
    assert context.get("atr_15m") == Decimal("1.25")
    assert context.has("ATR_15M")
    with pytest.raises(ValueError, match="timezone-aware"):
        MarketDataContext(INSTRUMENT_ID, datetime(2026, 9, 3, 10, 0), {})
    with pytest.raises(TypeError, match="Decimal"):
        MarketDataContext(INSTRUMENT_ID, NOW, {"atr_15m": 1.25})


def test_provider_protocol_accepts_normalized_fake_provider():
    provider = ProviderFake(MarketDataContext(INSTRUMENT_ID, NOW, {}))
    assert isinstance(provider, MarketDataProvider)


def test_market_data_and_existing_derived_fields_use_current_dynamic_statistics():
    market = field("atr_15m", source=CustomFieldSource.MARKET_DATA)
    unrelated_market = field("day_change_pct", source=CustomFieldSource.MARKET_DATA)
    manual = field("trade_note", source=CustomFieldSource.MANUAL, value_type=CustomFieldValueType.TEXT)
    exchange = field("exchange_fee", source=CustomFieldSource.EXCHANGE)
    system = field("system_tag", source=CustomFieldSource.SYSTEM, value_type=CustomFieldValueType.TEXT)
    derived = field("position_value", source=CustomFieldSource.DERIVED)
    provider = ProviderFake(MarketDataContext(INSTRUMENT_ID, NOW, {"atr_15m": Decimal("1.5")}))
    use_case, uow, values = make_use_case(
        make_trade(), [market, unrelated_market, manual, exchange, system, derived], provider
    )

    result = run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))

    assert provider.calls == [(INSTRUMENT_ID, NOW, ("atr_15m", "day_change_pct"))]
    assert {value.field_id for value in values.values} == {market.id, derived.id}
    assert next(value for value in values.values if value.field_id == market.id).value == Decimal("1.5")
    assert next(value for value in values.values if value.field_id == derived.id).value == Decimal("200")
    assert result.market_data_status is MarketDataFetchStatus.AVAILABLE
    assert {issue.code for issue in result.unavailable_auto_fields} == {
        "day_change_pct", "exchange_fee", "system_tag"
    }
    assert [str(field.code) for field in result.enrichment.missing_manual_optional] == ["trade_note"]


def test_missing_market_data_stays_missing_and_provider_unavailability_is_clean():
    market = field("atr_15m", source=CustomFieldSource.MARKET_DATA)
    missing_provider = ProviderFake(MarketDataContext(INSTRUMENT_ID, NOW, {}))
    use_case, uow, values = make_use_case(make_trade(), [market], missing_provider)
    result = run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))

    assert not values.values
    assert result.unavailable_auto_fields[0].code == "atr_15m"
    assert result.market_data_status is MarketDataFetchStatus.AVAILABLE

    unavailable = ProviderFake(error=MarketDataUnavailableError("temporary outage"))
    use_case, uow, values = make_use_case(make_trade(), [market], unavailable)
    result = run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))
    assert not values.values
    assert result.market_data_status is MarketDataFetchStatus.UNAVAILABLE


def test_phase_resolution_is_open_post_trade_and_any_aware():
    open_field = field("open_value", source=CustomFieldSource.MARKET_DATA, phase=CustomFieldPhase.OPEN)
    post_field = field("post_value", source=CustomFieldSource.MARKET_DATA, phase=CustomFieldPhase.POST_TRADE)
    any_field = field("any_value", source=CustomFieldSource.MARKET_DATA, phase=CustomFieldPhase.ANY)
    context = MarketDataContext(
        INSTRUMENT_ID,
        NOW,
        {"open_value": Decimal("1"), "post_value": Decimal("2"), "any_value": Decimal("3")},
    )

    provider = ProviderFake(context)
    use_case, uow, values = make_use_case(make_trade(), [open_field, post_field, any_field], provider)
    run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))
    assert {value.field_id for value in values.values} == {open_field.id, any_field.id}
    assert provider.calls[0][1] == NOW

    provider = ProviderFake(context)
    closed = make_trade(closed=True)
    use_case, uow, values = make_use_case(closed, [open_field, post_field, any_field], provider)
    run(use_case.execute(EnrichTradeWithMarketDataCommand(closed.trade_id, recorded_at=NOW)))
    assert {value.field_id for value in values.values} == {post_field.id, any_field.id}
    assert provider.calls[0][1] == closed.closed_at


def test_existing_value_is_not_overwritten_and_no_provider_call_is_needed():
    market = field("atr_15m", source=CustomFieldSource.MARKET_DATA)
    trade = make_trade()
    existing = TradeCustomValue.create(trade.trade_id, market, Decimal("1.0"), NOW)
    provider = ProviderFake(MarketDataContext(INSTRUMENT_ID, NOW, {"atr_15m": Decimal("2.0")}))
    use_case, uow, values = make_use_case(trade, [market], provider, ValueRepo([existing]))

    result = run(use_case.execute(EnrichTradeWithMarketDataCommand(trade.trade_id, recorded_at=NOW)))

    assert values.values == [existing]
    assert provider.calls == []
    assert result.generated_values == ()


def test_provider_instrument_mismatch_is_explicit_and_multiple_values_roll_back_together():
    market = field("first_value", source=CustomFieldSource.MARKET_DATA)
    other = field("second_value", source=CustomFieldSource.MARKET_DATA)
    wrong_context = MarketDataContext(InstrumentId.generate(), NOW, {"first_value": Decimal("1")})
    use_case, uow, _ = make_use_case(make_trade(), [market], ProviderFake(wrong_context))
    with pytest.raises(MarketDataMappingError):
        run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))

    provider = ProviderFake(MarketDataContext(INSTRUMENT_ID, NOW, {"first_value": Decimal("1"), "second_value": Decimal("2")}))
    values = ValueRepo(fail_on_add_number=2)
    use_case, uow, values = make_use_case(make_trade(), [market, other], provider, values)
    with pytest.raises(RuntimeError, match="forced"):
        run(use_case.execute(EnrichTradeWithMarketDataCommand(uow.trades.trade.trade_id, recorded_at=NOW)))
    assert values.values == []
    assert uow.rolled_back
