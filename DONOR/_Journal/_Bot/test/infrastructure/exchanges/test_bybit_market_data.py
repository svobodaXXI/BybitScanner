import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.accounts.account_id import AccountId
from app.core.automatic_data import AutomaticFactorQuality
from app.core.instruments import Instrument, InstrumentId
from app.infrastructure.exchanges.bybit.config import BybitSettings
from app.infrastructure.exchanges.bybit.market_data import BybitMarketDataProvider


class Instruments:
    def __init__(self, instrument):
        self.instrument = instrument

    async def get_by_id(self, instrument_id):
        return self.instrument if instrument_id == self.instrument.instrument_id else None


class Client:
    def __init__(self):
        self.calls = []

    async def get_public(self, path, params):
        self.calls.append((path, dict(params)))
        start = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
        if params["interval"] == "D":
            rows = []
            for index in range(5):
                at = start + timedelta(days=index)
                rows.append([str(int(at.timestamp() * 1000)), "1", "1", "1", "1", str(100 + index), str(1000 + index)])
            return {"retCode": 0, "result": {"list": rows}}
        # Each comparison day has three closed minutes before the 00:03 entry.
        rows = []
        for index in range(3):
            at = start + timedelta(minutes=index)
            rows.append([str(int(at.timestamp() * 1000)), "1", "1", "1", "1", "1", "10"])
        return {"retCode": 0, "result": {"list": rows}}


def test_bybit_snapshot_uses_utc_closed_days_and_equal_elapsed_minute_windows():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    snapshot = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id,
        datetime(2026, 9, 7, 0, 3, 30, tzinfo=timezone.utc),
        factor_ids=(
            "volume_1d_at_entry", "turnover_1d_at_entry", "previous_day_volume",
            "previous_day_turnover", "avg_volume_prev_5d", "avg_turnover_prev_5d", "rvol_at_entry",
        ),
    ))

    assert snapshot.provider_key == "BYBIT_V5_KLINE"
    assert snapshot.points["volume_1d_at_entry"].value == Decimal("3")
    assert snapshot.points["turnover_1d_at_entry"].value == Decimal("30")
    assert snapshot.points["previous_day_volume"].value == Decimal("104")
    assert snapshot.points["avg_volume_prev_5d"].value == Decimal("102")
    assert snapshot.points["avg_turnover_prev_5d"].value == Decimal("1002")
    assert snapshot.points["rvol_at_entry"].value == Decimal("1")
    current_last = datetime(2026, 9, 7, 0, 2, tzinfo=timezone.utc)
    assert snapshot.points["volume_1d_at_entry"].source_timestamp == current_last
    assert snapshot.points["turnover_1d_at_entry"].source_timestamp == current_last
    assert snapshot.points["rvol_at_entry"].source_timestamp == current_last
    assert snapshot.points["rvol_at_entry"].provenance["current_cutoff"] == current_last.isoformat()
    assert snapshot.points["rvol_at_entry"].provenance["historical_window_start"] == "2026-09-02T00:00:00+00:00"
    assert snapshot.points["rvol_at_entry"].provenance["historical_window_end"] == "2026-09-06T00:02:00+00:00"
    assert len(snapshot.points["rvol_at_entry"].provenance["comparison_days"]) == 5
    assert snapshot.points["previous_day_volume"].source_timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert snapshot.points["previous_day_turnover"].source_timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert snapshot.points["avg_volume_prev_5d"].source_timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert snapshot.points["avg_turnover_prev_5d"].source_timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert snapshot.points["avg_volume_prev_5d"].provenance["window_start"] == "2026-09-02T00:00:00+00:00"
    assert snapshot.points["avg_volume_prev_5d"].provenance["window_end"] == "2026-09-06T00:00:00+00:00"
    assert len(snapshot.points["avg_volume_prev_5d"].provenance["contributing_candles"]) == 5
    assert all(point.quality_status is AutomaticFactorQuality.VALID for point in snapshot.points.values())
    assert len(client.calls) == 7  # six 1m windows plus one daily request, not one call per factor


class V2Client(Client):
    async def get_public(self, path, params):
        self.calls.append((path, dict(params)))
        start = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
        if params["interval"] == "D":
            rows = []
            for index in range(15):
                at = start + timedelta(days=index)
                rows.append([
                    str(int(at.timestamp() * 1000)), str(90 + index), str(100 + index),
                    str(80 + index), str(95 + index), "100", "1000",
                ])
            return {"retCode": 0, "result": {"list": rows}}

        rows = []
        if start.date() == datetime(2026, 9, 7, tzinfo=timezone.utc).date():
            values = ((100, 102, 99, 101, 2, 200), (101, 105, 100, 104, 3, 600), (104, 106, 103, 105, 5, 1000))
        else:
            values = ((100, 100, 100, 100, 1, 10),) * 3
        for index, values_at_candle in enumerate(values + ((999, 999, 999, 999, 999, 999),)):
            at = start + timedelta(minutes=index)
            rows.append([str(int(at.timestamp() * 1000)), *(str(value) for value in values_at_candle)])
        return {"retCode": 0, "result": {"list": rows}}


class V3Client(Client):
    def __init__(self):
        super().__init__()
        self.funding_rows = [
            {"fundingRateTimestamp": "1788782400000", "fundingRate": "0.0003"},
            {"fundingRateTimestamp": "1788768000000", "fundingRate": "-0.0002"},
            {"fundingRateTimestamp": "1788753600000", "fundingRate": "0.0001"},
            {"fundingRateTimestamp": "1788796800000", "fundingRate": "0.0009"},
        ]

    async def get_public(self, path, params):
        self.calls.append((path, dict(params)))
        if path == "/v5/market/open-interest":
            start = datetime.fromtimestamp(int(params["startTime"]) / 1000, tz=timezone.utc)
            end = datetime.fromtimestamp(int(params["endTime"]) / 1000, tz=timezone.utc)
            cutoff = datetime(2026, 9, 7, 12, 25, tzinfo=timezone.utc)
            records = []
            cursor = start
            while cursor <= end:
                value = {cutoff: 200, cutoff - timedelta(hours=1): 100,
                         cutoff - timedelta(hours=4): 160, cutoff - timedelta(days=1): 50}.get(cursor, 75)
                records.append({"timestamp": str(int(cursor.timestamp() * 1000)), "openInterest": str(value)})
                cursor += timedelta(minutes=5)
            records = [row for row in reversed(records) if start <= datetime.fromtimestamp(int(row["timestamp"]) / 1000, tz=timezone.utc) <= end]
            return {"retCode": 0, "result": {"list": records[:200]}}
        if path == "/v5/market/funding/history":
            return {"retCode": 0, "result": {"list": self.funding_rows}}
        if path == "/v5/market/mark-price-kline":
            at = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
            return {"retCode": 0, "result": {"list": [[str(int(at.timestamp() * 1000)), "110", "110", "110", "110"]]}}
        if path == "/v5/market/index-price-kline":
            at = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
            return {"retCode": 0, "result": {"list": [[str(int(at.timestamp() * 1000)), "100", "100", "100", "100"]]}}
        raise AssertionError(f"unexpected endpoint: {path}")


V3_FACTORS = (
    "open_interest_base_at_entry", "open_interest_notional_usdt_at_entry",
    "open_interest_change_1h_pct_at_entry", "open_interest_change_4h_pct_at_entry",
    "open_interest_change_24h_pct_at_entry", "last_settled_funding_rate_at_entry",
    "avg_last_3_settled_funding_rate_at_entry", "funding_interval_minutes_inferred_at_entry",
    "minutes_since_last_funding_at_entry", "minutes_to_next_funding_inferred_at_entry",
    "mark_price_at_entry_snapshot", "index_price_at_entry_snapshot", "mark_index_basis_pct_at_entry",
)


def v3_provider():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = V3Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    return BybitMarketDataProvider(settings, Instruments(instrument), client), instrument, client


def test_bybit_v3_snapshot_uses_exact_historical_sources_and_formulas():
    provider, instrument, client = v3_provider()
    opened_at = datetime(2026, 9, 7, 12, 34, 30, tzinfo=timezone.utc)
    snapshot = asyncio.run(provider.get_entry_snapshot(instrument.instrument_id, opened_at, factor_ids=V3_FACTORS))
    points = snapshot.points

    assert points["open_interest_base_at_entry"].value == Decimal("200")
    assert points["open_interest_notional_usdt_at_entry"].value == Decimal("22000")
    assert points["open_interest_change_1h_pct_at_entry"].value == Decimal("100")
    assert points["open_interest_change_4h_pct_at_entry"].value == Decimal("25")
    assert points["open_interest_change_24h_pct_at_entry"].value == Decimal("300")
    assert points["last_settled_funding_rate_at_entry"].value == Decimal("0.0003")
    assert points["avg_last_3_settled_funding_rate_at_entry"].value == Decimal("0.0002") / Decimal("3")
    assert points["funding_interval_minutes_inferred_at_entry"].value == 240
    assert points["minutes_since_last_funding_at_entry"].value == Decimal("34.5")
    assert points["minutes_to_next_funding_inferred_at_entry"].value == Decimal("205.5")
    assert points["mark_price_at_entry_snapshot"].value == Decimal("110")
    assert points["index_price_at_entry_snapshot"].value == Decimal("100")
    assert points["mark_index_basis_pct_at_entry"].value == Decimal("10")

    oi_cutoff = datetime(2026, 9, 7, 12, 25, tzinfo=timezone.utc)
    price_cutoff = datetime(2026, 9, 7, 12, 33, tzinfo=timezone.utc)
    assert points["open_interest_base_at_entry"].source_timestamp == oi_cutoff
    assert points["open_interest_base_at_entry"].provenance["oi_cutoff"] == oi_cutoff.isoformat()
    assert points["open_interest_change_24h_pct_at_entry"].provenance["reference_timestamp"] == "2026-09-06T12:25:00+00:00"
    assert points["last_settled_funding_rate_at_entry"].source_timestamp == datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)
    assert len(points["avg_last_3_settled_funding_rate_at_entry"].provenance["settlement_timestamps"]) == 3
    assert points["funding_interval_minutes_inferred_at_entry"].provenance["inferred_interval_minutes"] == 240
    assert points["mark_price_at_entry_snapshot"].source_timestamp == price_cutoff
    assert points["index_price_at_entry_snapshot"].provenance["price_cutoff"] == price_cutoff.isoformat()
    assert points["mark_index_basis_pct_at_entry"].provenance["calculation"] == "(mark / index - 1) * 100"
    basis_provenance = points["mark_index_basis_pct_at_entry"].provenance
    assert basis_provenance["source_endpoints"] == [
        "/v5/market/mark-price-kline", "/v5/market/index-price-kline",
    ]
    assert basis_provenance["price_cutoff"] == price_cutoff.isoformat()
    assert basis_provenance["mark_candle_timestamp"] == price_cutoff.isoformat()
    assert basis_provenance["index_candle_timestamp"] == price_cutoff.isoformat()
    assert "/v5/market/mark_index_basis-price-kline" not in str(basis_provenance)
    assert "no nearest substitution and no look-ahead" in basis_provenance["calculation_policy"]
    assert len([path for path, _ in client.calls if path == "/v5/market/open-interest"]) == 2
    assert len(client.calls) == 5


def test_bybit_v3_selective_dependencies_are_exact_and_do_not_add_points():
    provider, instrument, client = v3_provider()
    opened_at = datetime(2026, 9, 7, 12, 34, 30, tzinfo=timezone.utc)

    basis = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id, opened_at, factor_ids=("mark_index_basis_pct_at_entry",),
    ))
    assert set(basis.points) == {"mark_index_basis_pct_at_entry"}
    assert basis.points["mark_index_basis_pct_at_entry"].value == Decimal("10")
    assert [path for path, _ in client.calls] == ["/v5/market/mark-price-kline", "/v5/market/index-price-kline"]

    provider, instrument, client = v3_provider()
    notional = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id, opened_at, factor_ids=("open_interest_notional_usdt_at_entry",),
    ))
    assert set(notional.points) == {"open_interest_notional_usdt_at_entry"}
    assert notional.points["open_interest_notional_usdt_at_entry"].value == Decimal("22000")
    assert [path for path, _ in client.calls].count("/v5/market/open-interest") == 2
    assert [path for path, _ in client.calls].count("/v5/market/mark-price-kline") == 1
    assert all(path not in {"/v5/market/funding/history", "/v5/market/index-price-kline"} for path, _ in client.calls)

    provider, instrument, client = v3_provider()
    oi_change = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id, opened_at, factor_ids=("open_interest_change_1h_pct_at_entry",),
    ))
    assert set(oi_change.points) == {"open_interest_change_1h_pct_at_entry"}
    assert oi_change.points["open_interest_change_1h_pct_at_entry"].value == Decimal("100")
    assert len(client.calls) == 2

    provider, instrument, client = v3_provider()
    funding = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id, opened_at, factor_ids=("last_settled_funding_rate_at_entry",),
    ))
    assert set(funding.points) == {"last_settled_funding_rate_at_entry"}
    assert funding.points["last_settled_funding_rate_at_entry"].value == Decimal("0.0003")
    assert [path for path, _ in client.calls] == ["/v5/market/funding/history"]


def test_bybit_v3_missing_source_is_not_zero():
    class EmptyV3Client(V3Client):
        async def get_public(self, path, params):
            self.calls.append((path, dict(params)))
            return {"retCode": 0, "result": {"list": []}}

    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = EmptyV3Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    snapshot = asyncio.run(provider.get_entry_snapshot(instrument.instrument_id, datetime(2026, 9, 7, 12, 34, tzinfo=timezone.utc), factor_ids=V3_FACTORS))
    assert all(point.value is None for point in snapshot.points.values())
    assert all(point.source_timestamp is None for point in snapshot.points.values())


def test_bybit_v2_snapshot_formulas_provenance_and_no_lookahead():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = V2Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    factor_ids = (
        "market_price_at_entry_snapshot", "day_open_price", "day_high_at_entry", "day_low_at_entry",
        "day_change_pct_at_entry", "day_range_pct_at_entry", "day_range_position_at_entry",
        "atr_1d_14", "atr_1d_14_pct", "day_range_to_atr", "vwap_1d_at_entry", "distance_to_vwap_pct",
        "change_24h_pct_at_entry",
    )
    snapshot = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id,
        datetime(2026, 9, 7, 0, 3, 30, tzinfo=timezone.utc),
        factor_ids=factor_ids,
    ))
    points = snapshot.points
    cutoff = datetime(2026, 9, 7, 0, 2, tzinfo=timezone.utc)
    assert points["market_price_at_entry_snapshot"].value == Decimal("105")
    assert points["day_open_price"].value == Decimal("100")
    assert points["day_high_at_entry"].value == Decimal("106")
    assert points["day_low_at_entry"].value == Decimal("99")
    assert points["day_change_pct_at_entry"].value == Decimal("5")
    assert points["day_range_pct_at_entry"].value == Decimal("7")
    assert points["day_range_position_at_entry"].value == Decimal(6) / Decimal(7)
    assert points["vwap_1d_at_entry"].value == Decimal("180")
    assert points["distance_to_vwap_pct"].value == (Decimal("105") / Decimal("180") - 1) * 100
    assert points["change_24h_pct_at_entry"].value == Decimal("5")
    assert points["atr_1d_14"].value == Decimal("20")
    assert points["atr_1d_14_pct"].value == Decimal(20) / Decimal(105) * 100
    assert points["day_range_to_atr"].value == Decimal("0.35")
    assert points["market_price_at_entry_snapshot"].source_timestamp == cutoff
    assert points["day_open_price"].source_timestamp == datetime(2026, 9, 7, 0, 0, tzinfo=timezone.utc)
    assert points["vwap_1d_at_entry"].source_timestamp == cutoff
    assert points["change_24h_pct_at_entry"].source_timestamp == cutoff
    assert points["change_24h_pct_at_entry"].provenance["reference_candle_timestamp"] == "2026-09-06T00:02:00+00:00"
    assert points["change_24h_pct_at_entry"].provenance["cutoff_candle_timestamp"] == cutoff.isoformat()
    assert points["vwap_1d_at_entry"].provenance["contributing_intraday_start"] == "2026-09-07T00:00:00+00:00"
    assert points["vwap_1d_at_entry"].provenance["contributing_intraday_end"] == cutoff.isoformat()
    assert points["atr_1d_14"].source_timestamp == datetime(2026, 9, 6, tzinfo=timezone.utc)
    assert len(points["atr_1d_14"].provenance["contributing_candle_timestamps"]) == 14
    assert points["atr_1d_14"].provenance["preceding_candle_timestamp"] == "2026-08-23T00:00:00+00:00"
    assert len(client.calls) == 7


def test_selective_atr_pct_fetches_both_intraday_and_daily_dependencies():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = V2Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    snapshot = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id,
        datetime(2026, 9, 7, 0, 3, 30, tzinfo=timezone.utc),
        factor_ids=("atr_1d_14_pct",),
    ))

    assert set(snapshot.points) == {"atr_1d_14_pct"}
    assert snapshot.points["atr_1d_14_pct"].value == Decimal(20) / Decimal(105) * 100
    assert len(client.calls) == 7
    assert {params["interval"] for _, params in client.calls} == {"1", "D"}


def test_selective_day_range_to_atr_fetches_both_intraday_and_daily_dependencies():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    client = V2Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    snapshot = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id,
        datetime(2026, 9, 7, 0, 3, 30, tzinfo=timezone.utc),
        factor_ids=("day_range_to_atr",),
    ))

    assert set(snapshot.points) == {"day_range_to_atr"}
    assert snapshot.points["day_range_to_atr"].value == Decimal("0.35")
    assert len(client.calls) == 7
    assert {params["interval"] for _, params in client.calls} == {"1", "D"}


def test_bybit_v2_denominator_edges_and_missing_are_not_zero():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")
    class EmptyV2Client(V2Client):
        async def get_public(self, path, params):
            self.calls.append((path, dict(params)))
            start = datetime.fromtimestamp(int(params["start"]) / 1000, tz=timezone.utc)
            if params["interval"] == "D":
                rows = []
                for index in range(15):
                    at = start + timedelta(days=index)
                    rows.append([str(int(at.timestamp() * 1000)), "10", "10", "10", "10", "0", "0"])
                return {"retCode": 0, "result": {"list": rows}}
            rows = []
            for index in range(3):
                at = start + timedelta(minutes=index)
                close = "10" if start.date() == datetime(2026, 9, 7, tzinfo=timezone.utc).date() else "0"
                rows.append([str(int(at.timestamp() * 1000)), "10", "10", "10", close, "0", "0"])
            return {"retCode": 0, "result": {"list": rows}}

    client = EmptyV2Client()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    factor_ids = (
        "market_price_at_entry_snapshot", "day_range_position_at_entry", "vwap_1d_at_entry",
        "distance_to_vwap_pct", "change_24h_pct_at_entry", "atr_1d_14", "atr_1d_14_pct", "day_range_to_atr",
    )
    snapshot = asyncio.run(provider.get_entry_snapshot(
        instrument.instrument_id, datetime(2026, 9, 7, 0, 3, tzinfo=timezone.utc), factor_ids=factor_ids,
    ))
    assert snapshot.points["market_price_at_entry_snapshot"].value == Decimal("10")
    assert snapshot.points["atr_1d_14"].value == Decimal("0")
    assert snapshot.points["atr_1d_14_pct"].value == Decimal("0")
    for factor_id in (
        "day_range_position_at_entry", "vwap_1d_at_entry", "distance_to_vwap_pct",
        "change_24h_pct_at_entry", "day_range_to_atr",
    ):
        assert snapshot.points[factor_id].value is None
        assert snapshot.points[factor_id].source_timestamp is None


def test_bybit_snapshot_does_not_turn_empty_intraday_source_into_zero():
    instrument = Instrument(InstrumentId.generate(), "BTCUSDT", "Bitcoin", "BYBIT", "LINEAR")

    class EmptyClient(Client):
        async def get_public(self, path, params):
            self.calls.append((path, dict(params)))
            if params["interval"] == "D":
                return {"retCode": 0, "result": {"list": []}}
            return {"retCode": 0, "result": {"list": []}}

    client = EmptyClient()
    settings = BybitSettings(api_key="key", api_secret="secret", account_id=AccountId.generate(), max_retries=0)
    provider = BybitMarketDataProvider(settings, Instruments(instrument), client)
    snapshot = asyncio.run(provider.get_entry_snapshot(instrument.instrument_id, datetime(2026, 9, 7, 1, 0, tzinfo=timezone.utc), factor_ids=("volume_1d_at_entry", "rvol_at_entry")))

    assert snapshot.points["volume_1d_at_entry"].value is None
    assert snapshot.points["rvol_at_entry"].value is None
    assert snapshot.points["volume_1d_at_entry"].quality_status is AutomaticFactorQuality.MISSING
    assert snapshot.points["volume_1d_at_entry"].source_timestamp is None
