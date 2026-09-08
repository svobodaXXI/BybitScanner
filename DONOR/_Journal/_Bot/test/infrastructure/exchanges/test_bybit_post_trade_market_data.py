import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.application.automatic_market_data import PostTradeMarketContext
from app.core.accounts.account_id import AccountId
from app.core.automatic_data import AutomaticFactorAvailability, AutomaticFactorQuality
from app.core.instruments import Instrument, InstrumentId
from app.core.trades.enums import TradeDirection
from app.infrastructure.exchanges.bybit.config import BybitSettings
from app.infrastructure.exchanges.bybit.market_data import BybitMarketDataProvider


class Instruments:
    def __init__(self, instrument):
        self.instrument = instrument

    async def get_by_id(self, instrument_id):
        return self.instrument if instrument_id == self.instrument.instrument_id else None


FACTORS = (
    "mae_observed_1m_extreme_price", "mfe_observed_1m_extreme_price",
    "mae_observed_1m_price_distance", "mfe_observed_1m_price_distance",
    "mae_observed_1m_pct", "mfe_observed_1m_pct",
    "mae_observed_1m_gross_pnl_usdt", "mfe_observed_1m_gross_pnl_usdt",
)


def row(at, open_price, high, low, close):
    return [str(int(at.timestamp() * 1000)), str(open_price), str(high), str(low), str(close), "1", "1"]


class Client:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.calls = []

    async def get_public(self, path, params):
        self.calls.append((path, dict(params)))
        assert path == "/v5/market/kline"
        start = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
        end = datetime.fromtimestamp(int(params["end"]) / 1000, tz=timezone.utc)
        return {"retCode": 0, "result": {"list": [
            item for item in self.rows
            if start <= datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc) <= end
        ]}}


def provider(client):
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    return BybitMarketDataProvider(settings, Instruments(instrument), client), instrument


def context(opened_at, closed_at, direction=TradeDirection.LONG, entry="100", exit="104", quantity="2"):
    return PostTradeMarketContext(
        instrument_id=InstrumentId.generate(), direction=direction,
        opened_at=opened_at, closed_at=closed_at,
        entry_price=Decimal(entry), exit_price=None if exit is None else Decimal(exit),
        quantity=Decimal(quantity),
    )


def aligned_rows(start, count, *, low="98", high="106", close="100"):
    return [row(start + index * timedelta(minutes=1), "100", high, low, close) for index in range(count)]


def test_long_mae_mfe_excludes_partial_candles_and_uses_earliest_tie():
    opened = datetime(2026, 9, 7, 16, 36, 25, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 7, 17, 7, 38, tzinfo=timezone.utc)
    rows = aligned_rows(datetime(2026, 9, 7, 16, 36, tzinfo=timezone.utc), 32)
    rows[0] = row(datetime(2026, 9, 7, 16, 36, tzinfo=timezone.utc), "100", "999", "1", "100")
    rows[9] = row(datetime(2026, 9, 7, 16, 45, tzinfo=timezone.utc), "100", "110", "90", "100")
    rows[10] = row(datetime(2026, 9, 7, 16, 46, tzinfo=timezone.utc), "100", "110", "90", "100")
    rows[14] = row(datetime(2026, 9, 7, 16, 50, tzinfo=timezone.utc), "100", "120", "98", "100")
    rows[-1] = row(datetime(2026, 9, 7, 17, 7, tzinfo=timezone.utc), "100", "999", "1", "100")
    client = Client(rows)
    provider_instance, instrument = provider(client)
    trade_context = context(opened, closed)
    object.__setattr__(trade_context, "instrument_id", instrument.instrument_id)

    snapshot = asyncio.run(provider_instance.get_post_trade_snapshot(trade_context, factor_ids=FACTORS))
    points = snapshot.points
    assert points["mae_observed_1m_extreme_price"].value == Decimal("90")
    assert points["mfe_observed_1m_extreme_price"].value == Decimal("120")
    assert points["mae_observed_1m_price_distance"].value == Decimal("10")
    assert points["mfe_observed_1m_price_distance"].value == Decimal("20")
    assert points["mae_observed_1m_price_distance"].provenance["calculation"] == "max(entry_price - adverse_extreme, 0)"
    assert points["mfe_observed_1m_price_distance"].provenance["calculation"] == "max(favorable_extreme - entry_price, 0)"
    assert points["mae_observed_1m_pct"].value == Decimal("10")
    assert points["mfe_observed_1m_pct"].value == Decimal("20")
    assert points["mae_observed_1m_gross_pnl_usdt"].value == Decimal("20")
    assert points["mfe_observed_1m_gross_pnl_usdt"].value == Decimal("40")
    assert points["mae_observed_1m_extreme_price"].source_timestamp == datetime(2026, 9, 7, 16, 45, tzinfo=timezone.utc)
    assert points["mfe_observed_1m_extreme_price"].source_timestamp == datetime(2026, 9, 7, 16, 50, tzinfo=timezone.utc)
    assert points["mae_observed_1m_extreme_price"].provenance["expected_full_candle_count"] == 30
    assert points["mae_observed_1m_extreme_price"].provenance["actual_full_candle_count"] == 30
    assert len(client.calls) == 1


def test_short_mae_mfe_and_exact_minute_boundaries():
    opened = datetime(2026, 9, 7, 16, 36, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 7, 16, 38, tzinfo=timezone.utc)
    rows = [
        row(datetime(2026, 9, 7, 16, 36, tzinfo=timezone.utc), "100", "100", "100", "100"),
        row(datetime(2026, 9, 7, 16, 37, tzinfo=timezone.utc), "100", "110", "80", "100"),
        row(datetime(2026, 9, 7, 16, 38, tzinfo=timezone.utc), "100", "999", "1", "100"),
    ]
    client = Client(rows)
    provider_instance, instrument = provider(client)
    trade_context = context(opened, closed, TradeDirection.SHORT, exit="96")
    object.__setattr__(trade_context, "instrument_id", instrument.instrument_id)
    points = asyncio.run(provider_instance.get_post_trade_snapshot(trade_context, factor_ids=FACTORS)).points

    assert points["mae_observed_1m_extreme_price"].value == Decimal("110")
    assert points["mfe_observed_1m_extreme_price"].value == Decimal("80")
    assert points["mae_observed_1m_price_distance"].value == Decimal("10")
    assert points["mfe_observed_1m_price_distance"].value == Decimal("20")
    assert points["mae_observed_1m_price_distance"].provenance["calculation"] == "max(adverse_extreme - entry_price, 0)"
    assert points["mfe_observed_1m_price_distance"].provenance["calculation"] == "max(entry_price - favorable_extreme, 0)"
    assert len(client.calls) == 1


def test_sub_minute_uses_only_endpoints_and_zero_excursions_are_valid():
    class FailingClient(Client):
        async def get_public(self, path, params):
            raise AssertionError("sub-minute trade must not fetch klines")

    opened = datetime(2026, 9, 7, 16, 36, 25, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 7, 16, 36, 50, tzinfo=timezone.utc)
    client = FailingClient()
    provider_instance, instrument = provider(client)
    trade_context = context(opened, closed, exit="100")
    object.__setattr__(trade_context, "instrument_id", instrument.instrument_id)
    points = asyncio.run(provider_instance.get_post_trade_snapshot(trade_context, factor_ids=FACTORS)).points

    assert points["mae_observed_1m_extreme_price"].value == Decimal("100")
    assert points["mfe_observed_1m_extreme_price"].value == Decimal("100")
    assert points["mae_observed_1m_price_distance"].value == Decimal("0")
    assert points["mfe_observed_1m_price_distance"].value == Decimal("0")
    assert points["mae_observed_1m_pct"].quality_status is AutomaticFactorQuality.VALID
    assert points["mfe_observed_1m_gross_pnl_usdt"].quality_status is AutomaticFactorQuality.VALID
    assert points["mae_observed_1m_extreme_price"].provenance["actual_full_candle_count"] == 0
    assert client.calls == []


def test_missing_candle_gap_is_missing_not_partial_and_long_trade_chunks():
    opened = datetime(2026, 9, 7, 16, 36, 25, tzinfo=timezone.utc)
    closed = datetime(2026, 9, 7, 16, 40, 38, tzinfo=timezone.utc)
    rows = [
        row(datetime(2026, 9, 7, 16, 37, tzinfo=timezone.utc), "100", "101", "99", "100"),
        row(datetime(2026, 9, 7, 16, 39, tzinfo=timezone.utc), "100", "101", "99", "100"),
    ]
    client = Client(rows)
    provider_instance, instrument = provider(client)
    trade_context = context(opened, closed)
    object.__setattr__(trade_context, "instrument_id", instrument.instrument_id)
    snapshot = asyncio.run(provider_instance.get_post_trade_snapshot(trade_context, factor_ids=FACTORS))
    assert all(point.value is None for point in snapshot.points.values())
    assert snapshot.points["mae_observed_1m_extreme_price"].provenance["expected_full_candle_count"] == 3
    assert snapshot.points["mae_observed_1m_extreme_price"].provenance["actual_full_candle_count"] == 2

    class ChunkClient(Client):
        async def get_public(self, path, params):
            self.calls.append((path, dict(params)))
            start = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
            end = datetime.fromtimestamp(int(params["end"]) / 1000, tz=timezone.utc)
            rows = []
            cursor = start
            while cursor <= end:
                rows.append(row(cursor, "100", "101", "99", "100"))
                cursor += timedelta(minutes=1)
            return {"retCode": 0, "result": {"list": rows}}

    chunk_client = ChunkClient()
    provider_instance, instrument = provider(chunk_client)
    long_context = context(
        datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 9, 1, 16, 42, tzinfo=timezone.utc),
    )
    object.__setattr__(long_context, "instrument_id", instrument.instrument_id)
    snapshot = asyncio.run(provider_instance.get_post_trade_snapshot(long_context, factor_ids=(FACTORS[0],)))
    assert snapshot.points[FACTORS[0]].quality_status is AutomaticFactorQuality.VALID
    assert len(chunk_client.calls) == 2


def test_missing_exit_and_neutral_direction_are_explicit_without_requests():
    client = Client()
    provider_instance, instrument = provider(client)
    opened = datetime(2026, 9, 7, 16, 36, tzinfo=timezone.utc)
    missing_exit = context(opened, opened + timedelta(minutes=2), exit=None)
    object.__setattr__(missing_exit, "instrument_id", instrument.instrument_id)
    missing = asyncio.run(provider_instance.get_post_trade_snapshot(missing_exit, factor_ids=FACTORS))
    assert all(point.value is None for point in missing.points.values())
    assert client.calls == []

    neutral = context(
        opened, opened + timedelta(minutes=2), direction=TradeDirection.NEUTRAL,
    )
    object.__setattr__(neutral, "instrument_id", instrument.instrument_id)
    not_applicable = asyncio.run(provider_instance.get_post_trade_snapshot(neutral, factor_ids=FACTORS))
    assert all(point.value is None for point in not_applicable.points.values())
    assert all(point.availability_status is AutomaticFactorAvailability.NOT_APPLICABLE for point in not_applicable.points.values())
    assert client.calls == []
