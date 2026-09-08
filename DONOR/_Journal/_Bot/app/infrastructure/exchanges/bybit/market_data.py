"""Bybit V5 market-data provider for automatic entry snapshots."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from app.application.automatic_market_data import (
    MarketDataPoint,
    MarketDataSnapshot,
    PostTradeMarketContext,
    PostTradeMarketSnapshot,
)
from app.core.automatic_data import AutomaticFactorAvailability, AutomaticFactorQuality

from .errors import BybitPayloadError, BybitRateLimitError, BybitRequestError


UTC_DAY = timedelta(days=1)
MINUTE = timedelta(minutes=1)
_MARKET_FACTORS = {
    "volume_1d_at_entry", "turnover_1d_at_entry", "previous_day_volume",
    "previous_day_turnover", "avg_volume_prev_5d", "avg_turnover_prev_5d", "rvol_at_entry",
    "market_price_at_entry_snapshot", "day_open_price", "day_high_at_entry",
    "day_low_at_entry", "day_change_pct_at_entry", "day_range_pct_at_entry",
    "day_range_position_at_entry", "atr_1d_14", "atr_1d_14_pct", "day_range_to_atr",
    "vwap_1d_at_entry", "distance_to_vwap_pct", "change_24h_pct_at_entry",
    "open_interest_base_at_entry", "open_interest_notional_usdt_at_entry",
    "open_interest_change_1h_pct_at_entry", "open_interest_change_4h_pct_at_entry",
    "open_interest_change_24h_pct_at_entry", "last_settled_funding_rate_at_entry",
    "avg_last_3_settled_funding_rate_at_entry", "funding_interval_minutes_inferred_at_entry",
    "minutes_since_last_funding_at_entry", "minutes_to_next_funding_inferred_at_entry",
    "mark_price_at_entry_snapshot", "index_price_at_entry_snapshot", "mark_index_basis_pct_at_entry",
}
_INTRADAY_FACTORS = {
    "volume_1d_at_entry", "turnover_1d_at_entry", "rvol_at_entry",
    "market_price_at_entry_snapshot", "day_open_price", "day_high_at_entry",
    "day_low_at_entry", "day_change_pct_at_entry", "day_range_pct_at_entry",
    "day_range_position_at_entry", "atr_1d_14_pct", "day_range_to_atr",
    "vwap_1d_at_entry", "distance_to_vwap_pct", "change_24h_pct_at_entry",
}
_DAILY_FACTORS = {
    "previous_day_volume", "previous_day_turnover", "avg_volume_prev_5d",
    "avg_turnover_prev_5d", "atr_1d_14", "atr_1d_14_pct", "day_range_to_atr",
}
_ATR_FACTORS = {"atr_1d_14", "atr_1d_14_pct", "day_range_to_atr"}
_OPEN_INTEREST_FACTORS = {
    "open_interest_base_at_entry", "open_interest_notional_usdt_at_entry",
    "open_interest_change_1h_pct_at_entry", "open_interest_change_4h_pct_at_entry",
    "open_interest_change_24h_pct_at_entry",
}
_FUNDING_FACTORS = {
    "last_settled_funding_rate_at_entry", "avg_last_3_settled_funding_rate_at_entry",
    "funding_interval_minutes_inferred_at_entry", "minutes_since_last_funding_at_entry",
    "minutes_to_next_funding_inferred_at_entry",
}
_MARK_FACTORS = {
    "mark_price_at_entry_snapshot", "mark_index_basis_pct_at_entry",
    "open_interest_notional_usdt_at_entry",
}
_INDEX_FACTORS = {"index_price_at_entry_snapshot", "mark_index_basis_pct_at_entry"}
_OPEN, _HIGH, _LOW, _CLOSE, _VOLUME, _TURNOVER = range(6)
_POST_TRADE_FACTORS = {
    "mae_observed_1m_extreme_price", "mfe_observed_1m_extreme_price",
    "mae_observed_1m_price_distance", "mfe_observed_1m_price_distance",
    "mae_observed_1m_pct", "mfe_observed_1m_pct",
    "mae_observed_1m_gross_pnl_usdt", "mfe_observed_1m_gross_pnl_usdt",
}


class BybitMarketDataProvider:
    """Fetch bounded kline data through the existing Bybit REST client.

    Bybit's linear volume is measured in base-coin units and turnover in the
    quote currency (USDT here).  All day boundaries and RVOL cutoffs are UTC.
    The entry minute itself is excluded because it is not a closed one-minute
    candle at the time of entry; this prevents look-ahead in historical data.
    """

    provider_key = "BYBIT_V5_KLINE"

    def __init__(self, settings, instrument_repository, client) -> None:
        self._settings = settings
        self._instruments = instrument_repository
        self._client = client

    async def get_entry_snapshot(self, instrument_id, as_of: datetime, *, factor_ids: tuple[str, ...] = ()) -> MarketDataSnapshot:
        as_of = _utc(as_of, "as_of")
        instrument = await self._instruments.get_by_id(instrument_id)
        if instrument is None:
            raise BybitPayloadError("instrument is not available for market-data lookup")
        if instrument.exchange != "BYBIT" or instrument.market != "LINEAR":
            return _missing_snapshot(instrument_id, as_of, factor_ids or tuple(_MARKET_FACTORS), "unsupported instrument")
        requested = set(factor_ids or _MARKET_FACTORS) & _MARKET_FACTORS
        if not requested:
            return MarketDataSnapshot(instrument_id, as_of, {}, self.provider_key)
        day_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        entry_minute = as_of.replace(second=0, microsecond=0)
        points: dict[str, MarketDataPoint] = {}

        minute_data = None
        need_minutes = requested & _INTRADAY_FACTORS
        if need_minutes:
            try:
                minute_data = await self._minute_windows(instrument.symbol, day_start, entry_minute)
            except Exception as error:
                for factor_id in need_minutes:
                    points[factor_id] = _missing_point(as_of, type(error).__name__)
            if minute_data is not None:
                current_rows = minute_data.get(day_start.date(), ())
                if current_rows:
                    current = _sum_rows(current_rows)
                    source_timestamp = current_rows[-1][0]
                    provenance = _minute_provenance(
                        day_start, entry_minute, current_rows,
                    )
                    if "volume_1d_at_entry" in requested:
                        points["volume_1d_at_entry"] = _available_point(
                            current[0], "base", source_timestamp, provenance,
                        )
                    if "turnover_1d_at_entry" in requested:
                        points["turnover_1d_at_entry"] = _available_point(
                            current[1], "USDT", source_timestamp, provenance,
                        )
                else:
                    for factor_id in need_minutes:
                        points[factor_id] = _missing_point(as_of, "missing current-day minute candles")

                if current_rows:
                    _capture_intraday_v2(
                        points, requested, current_rows, minute_data,
                        day_start, entry_minute, as_of,
                    )

        daily = None
        need_daily = requested & _DAILY_FACTORS
        if need_daily:
            try:
                daily_lookback = 15 if requested & _ATR_FACTORS else 5
                daily = await self._daily_rows(
                    instrument.symbol,
                    day_start - daily_lookback * UTC_DAY,
                    day_start - MINUTE,
                )
            except Exception as error:
                for factor_id in need_daily:
                    points[factor_id] = _missing_point(as_of, type(error).__name__)
            if daily is not None:
                ordered_days = [day_start.date() - timedelta(days=index) for index in range(1, 6)]
                rows = [daily.get(day) for day in ordered_days]
                if "previous_day_volume" in requested:
                    points["previous_day_volume"] = _daily_point(
                        rows[0], 4, "base", as_of, factor_id="previous_day_volume",
                    )
                if "previous_day_turnover" in requested:
                    points["previous_day_turnover"] = _daily_point(
                        rows[0], 5, "USDT", as_of, factor_id="previous_day_turnover",
                    )
                if "avg_volume_prev_5d" in requested:
                    points["avg_volume_prev_5d"] = _average_daily_point(
                        rows, 4, "base", as_of, factor_id="avg_volume_prev_5d",
                    )
                if "avg_turnover_prev_5d" in requested:
                    points["avg_turnover_prev_5d"] = _average_daily_point(
                        rows, 5, "USDT", as_of, factor_id="avg_turnover_prev_5d",
                    )
                if requested & _ATR_FACTORS:
                    _capture_atr_v2(points, requested, daily, day_start, current_rows if minute_data else (), as_of)

        if "rvol_at_entry" in requested and minute_data is not None:
            previous = []
            for index in range(1, 6):
                day = day_start - timedelta(days=index)
                previous.append(_sum_rows(minute_data.get(day.date(), ())))
            current_rows = minute_data.get(day_start.date(), ())
            if current_rows and all(minute_data.get(day_start.date() - timedelta(days=index), ()) for index in range(1, 6)):
                denominator = sum((item[0] for item in previous), Decimal("0")) / Decimal("5")
                current_volume = _sum_rows(current_rows)[0]
                if denominator > 0:
                    points["rvol_at_entry"] = _available_point(
                        current_volume / denominator,
                        "ratio",
                        current_rows[-1][0],
                        _rvol_provenance(day_start, entry_minute, current_rows, minute_data),
                    )
                else:
                    points["rvol_at_entry"] = _missing_point(as_of, "zero comparable historical volume")
            else:
                points["rvol_at_entry"] = _missing_point(as_of, "insufficient comparable minute history")

        price_cutoff = entry_minute - MINUTE
        mark_candle = None
        if requested & _MARK_FACTORS:
            try:
                mark_candle = await self._exact_price_candle(
                    instrument.symbol, "/v5/market/mark-price-kline", price_cutoff,
                )
            except Exception as error:
                _mark_requested_missing(points, requested, _MARK_FACTORS, as_of, type(error).__name__)
            if mark_candle is None:
                _mark_requested_missing(points, requested, _MARK_FACTORS, as_of, "missing exact mark-price candle")
            elif "mark_price_at_entry_snapshot" in requested:
                points["mark_price_at_entry_snapshot"] = _available_point(
                    mark_candle[1], "USDT", mark_candle[0],
                    _derivatives_price_provenance("mark", price_cutoff, mark_candle[0]),
                )

        index_candle = None
        if requested & _INDEX_FACTORS:
            try:
                index_candle = await self._exact_price_candle(
                    instrument.symbol, "/v5/market/index-price-kline", price_cutoff,
                )
            except Exception as error:
                _mark_requested_missing(points, requested, _INDEX_FACTORS, as_of, type(error).__name__)
            if index_candle is None:
                _mark_requested_missing(points, requested, _INDEX_FACTORS, as_of, "missing exact index-price candle")
            elif "index_price_at_entry_snapshot" in requested:
                points["index_price_at_entry_snapshot"] = _available_point(
                    index_candle[1], "USDT", index_candle[0],
                    _derivatives_price_provenance("index", price_cutoff, index_candle[0]),
                )

        oi_rows = None
        if requested & _OPEN_INTEREST_FACTORS:
            entry_5m_bucket = _floor_5_minutes(as_of)
            oi_cutoff = entry_5m_bucket - 5 * MINUTE
            try:
                oi_rows = await self._open_interest_rows(
                    instrument.symbol, oi_cutoff - UTC_DAY, oi_cutoff,
                )
            except Exception as error:
                _mark_requested_missing(points, requested, _OPEN_INTEREST_FACTORS, as_of, type(error).__name__)
            if oi_rows is not None:
                _capture_open_interest_v3(points, requested, oi_rows, mark_candle, oi_cutoff, as_of)

        if requested & _FUNDING_FACTORS:
            try:
                funding_rows = await self._funding_rows(instrument.symbol, as_of)
            except Exception as error:
                _mark_requested_missing(points, requested, _FUNDING_FACTORS, as_of, type(error).__name__)
            else:
                _capture_funding_v3(points, requested, funding_rows, as_of)

        if "mark_index_basis_pct_at_entry" in requested:
            if mark_candle is None or index_candle is None or index_candle[1] <= 0:
                points["mark_index_basis_pct_at_entry"] = _missing_point(as_of, "missing positive mark/index prices")
            else:
                points["mark_index_basis_pct_at_entry"] = _available_point(
                    (mark_candle[1] / index_candle[1] - Decimal("1")) * Decimal("100"),
                    "percent", mark_candle[0],
                    _basis_provenance(price_cutoff, mark_candle[0], index_candle[0]),
                )

        return MarketDataSnapshot(instrument_id, as_of, points, self.provider_key)

    async def get_post_trade_snapshot(
        self,
        context: PostTradeMarketContext,
        *,
        factor_ids: tuple[str, ...] = (),
    ) -> PostTradeMarketSnapshot:
        requested = set(factor_ids or _POST_TRADE_FACTORS) & _POST_TRADE_FACTORS
        if not requested:
            return PostTradeMarketSnapshot(
                context.instrument_id, context.opened_at, context.closed_at, {}, self.provider_key,
            )
        instrument = await self._instruments.get_by_id(context.instrument_id)
        if instrument is None or instrument.exchange != "BYBIT" or instrument.market != "LINEAR":
            return _missing_post_trade_snapshot(context, requested, "unsupported instrument")
        direction = getattr(context.direction, "value", context.direction)
        if direction not in {"LONG", "SHORT"}:
            return _not_applicable_post_trade_snapshot(context, requested, "unsupported trade direction")
        if (
            context.closed_at is None
            or context.closed_at < context.opened_at
            or context.entry_price <= 0
            or context.exit_price is None
            or context.exit_price <= 0
            or context.quantity <= 0
        ):
            return _missing_post_trade_snapshot(context, requested, "incomplete post-trade facts")

        first_full = _first_full_minute(context.opened_at)
        last_full = context.closed_at.replace(second=0, microsecond=0) - MINUTE
        expected_count = 0 if first_full > last_full else int((last_full - first_full) / MINUTE) + 1
        rows = []
        if expected_count:
            try:
                rows = await self._fetch_klines(instrument.symbol, "1", first_full, last_full)
            except Exception as error:
                return _missing_post_trade_snapshot(context, requested, type(error).__name__)
            expected_timestamps = tuple(first_full + index * MINUTE for index in range(expected_count))
            actual_timestamps = tuple(row[0] for row in rows)
            if actual_timestamps != expected_timestamps:
                return _missing_post_trade_snapshot(
                    context,
                    requested,
                    "missing or non-contiguous fully-contained minute candles",
                    provenance=_v4_provenance(context, first_full, last_full, expected_count, rows),
                )

        return _observed_post_trade_snapshot(context, requested, direction, rows, first_full, last_full, expected_count)

    async def _minute_windows(self, symbol: str, day_start: datetime, entry_minute: datetime):
        """Fetch the current and five comparison-day windows with no look-ahead."""
        result = {}
        for index in range(6):
            start = day_start - timedelta(days=index)
            end = start + (entry_minute - day_start) - MINUTE
            result[start.date()] = await self._fetch_klines(symbol, "1", start, end)
        return result

    async def _daily_rows(self, symbol: str, start: datetime, end: datetime):
        rows = await self._fetch_klines(symbol, "D", start, end)
        return {timestamp.date(): (timestamp, row) for timestamp, row in rows}

    async def _exact_price_candle(self, symbol: str, path: str, cutoff: datetime):
        payload = await self._request(path, {
            "category": self._settings.category,
            "symbol": symbol,
            "interval": "1",
            "start": str(_epoch_millis(cutoff)),
            "end": str(_epoch_millis(cutoff)),
            "limit": "1",
        })
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise BybitPayloadError("Bybit price kline response lacks result.list")
        for raw in result["list"]:
            parsed = _parse_price_kline(raw)
            if parsed is not None and parsed[0] == cutoff:
                return parsed
        return None

    async def _open_interest_rows(self, symbol: str, start: datetime, end: datetime):
        """Fetch the bounded exact 5m OI window, paginating backwards."""
        start_millis = _epoch_millis(start)
        end_millis = _epoch_millis(end)
        page_end = end_millis
        rows = []
        seen_pages = set()
        for _ in range(self._settings.max_pages):
            payload = await self._request("/v5/market/open-interest", {
                "category": self._settings.category,
                "symbol": symbol,
                "intervalTime": "5min",
                "startTime": str(start_millis),
                "endTime": str(page_end),
                "limit": "200",
            })
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("list"), list):
                raise BybitPayloadError("Bybit open-interest response lacks result.list")
            page = [_parse_open_interest_row(raw) for raw in result["list"]]
            page = [row for row in page if start <= row[0] <= end]
            if not page:
                break
            page_key = tuple(sorted(row[0] for row in page))
            if page_key in seen_pages:
                break
            seen_pages.add(page_key)
            rows.extend(page)
            oldest = min(row[0] for row in page)
            if oldest <= start:
                break
            next_page_end = _epoch_millis(oldest) - 1
            if next_page_end >= page_end:
                break
            page_end = next_page_end
        by_timestamp = {timestamp: value for timestamp, value in rows}
        return tuple((timestamp, by_timestamp[timestamp]) for timestamp in sorted(by_timestamp))

    async def _funding_rows(self, symbol: str, as_of: datetime):
        payload = await self._request("/v5/market/funding/history", {
            "category": self._settings.category,
            "symbol": symbol,
            "endTime": str(_epoch_millis(as_of)),
            "limit": "3",
        })
        result = payload.get("result")
        if not isinstance(result, dict) or not isinstance(result.get("list"), list):
            raise BybitPayloadError("Bybit funding response lacks result.list")
        rows = [_parse_funding_row(raw) for raw in result["list"]]
        return tuple(sorted((row for row in rows if row[0] <= as_of), key=lambda row: row[0]))

    async def _fetch_klines(self, symbol: str, interval: str, start: datetime, end: datetime):
        if end < start:
            return []
        rows = []
        step = UTC_DAY * 1000 if interval == "D" else MINUTE * 1000
        cursor = start
        while cursor <= end:
            chunk_end = min(end, cursor + step - timedelta(milliseconds=1))
            payload = await self._request("/v5/market/kline", {
                "category": self._settings.category,
                "symbol": symbol,
                "interval": interval,
                "start": str(_epoch_millis(cursor)),
                "end": str(_epoch_millis(chunk_end)),
                "limit": "1000",
            })
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("list"), list):
                raise BybitPayloadError("Bybit kline response lacks result.list")
            for raw in result["list"]:
                parsed = _parse_kline(raw)
                if parsed is not None and start <= parsed[0] <= end:
                    rows.append(parsed)
            cursor = chunk_end + timedelta(milliseconds=1)
        by_timestamp = {item[0]: item for item in rows}
        return [by_timestamp[key] for key in sorted(by_timestamp)]

    async def _request(self, path, params):
        getter = getattr(self._client, "get_public", None) or self._client.get
        for attempt in range(self._settings.max_retries + 1):
            try:
                payload = await getter(path, params)
                if not isinstance(payload, dict):
                    raise BybitPayloadError("Bybit response must be an object")
                ret_code = payload.get("retCode")
                if ret_code in {10006, 10429}:
                    raise BybitRateLimitError("Bybit API rate limit reached")
                if ret_code != 0:
                    raise BybitRequestError(f"Bybit market-data request failed: retCode={ret_code}")
                return payload
            except BybitRateLimitError:
                if attempt >= self._settings.max_retries:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
            except BybitRequestError:
                if attempt >= self._settings.max_retries:
                    raise
                await asyncio.sleep(0.25 * (2**attempt))
        raise AssertionError("unreachable")


def _parse_kline(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) < 7:
        raise BybitPayloadError("Bybit kline row must contain seven values")
    try:
        milliseconds_decimal = Decimal(str(raw[0]))
        if milliseconds_decimal != milliseconds_decimal.to_integral_value():
            raise ValueError("kline timestamp must be an integer millisecond")
        milliseconds = int(milliseconds_decimal)
        open_price = _decimal(raw[1])
        high = _decimal(raw[2])
        low = _decimal(raw[3])
        close = _decimal(raw[4])
        volume = _decimal(raw[5])
        turnover = _decimal(raw[6])
    except (TypeError, ValueError, InvalidOperation) as error:
        raise BybitPayloadError("invalid Bybit kline row") from error
    timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)
    return timestamp, (open_price, high, low, close, volume, turnover)


def _parse_price_kline(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) < 5:
        raise BybitPayloadError("Bybit price kline row must contain five values")
    timestamp = _parse_timestamp(raw[0], "price kline timestamp")
    try:
        close = _decimal(raw[4])
    except (TypeError, ValueError, InvalidOperation) as error:
        raise BybitPayloadError("invalid Bybit price kline row") from error
    return timestamp, close


def _parse_open_interest_row(raw):
    if not isinstance(raw, dict) or "timestamp" not in raw or "openInterest" not in raw:
        raise BybitPayloadError("invalid Bybit open-interest row")
    timestamp = _parse_timestamp(raw["timestamp"], "open-interest timestamp")
    try:
        value = _decimal(raw["openInterest"])
    except (TypeError, ValueError, InvalidOperation) as error:
        raise BybitPayloadError("invalid Bybit open-interest value") from error
    return timestamp, value


def _parse_funding_row(raw):
    if not isinstance(raw, dict) or "fundingRateTimestamp" not in raw or "fundingRate" not in raw:
        raise BybitPayloadError("invalid Bybit funding row")
    timestamp = _parse_timestamp(raw["fundingRateTimestamp"], "funding timestamp")
    try:
        rate = _signed_decimal(raw["fundingRate"])
    except (TypeError, ValueError, InvalidOperation) as error:
        raise BybitPayloadError("invalid Bybit funding rate") from error
    return timestamp, rate


def _parse_timestamp(value, name):
    try:
        milliseconds_decimal = Decimal(str(value))
        if milliseconds_decimal != milliseconds_decimal.to_integral_value():
            raise ValueError(f"{name} must be an integer millisecond")
        milliseconds = int(milliseconds_decimal)
    except (TypeError, ValueError, InvalidOperation) as error:
        raise BybitPayloadError(f"invalid {name}") from error
    return datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=milliseconds)


def _sum_rows(rows):
    return (
        sum((row[1][_VOLUME] for row in rows), Decimal("0")),
        sum((row[1][_TURNOVER] for row in rows), Decimal("0")),
    )


def _decimal(value):
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("kline value must be finite and non-negative")
    return result


def _signed_decimal(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("value must be finite")
    return result


def _available_point(value, unit, source_timestamp, provenance):
    return MarketDataPoint(
        value=value, unit=unit, currency="USDT" if unit == "USDT" else None,
        source_timestamp=source_timestamp, quality_status=AutomaticFactorQuality.VALID,
        availability_status=AutomaticFactorAvailability.AVAILABLE,
        provenance=provenance,
    )


def _daily_point(row, index, unit, as_of, *, factor_id):
    if row is None:
        return _missing_point(as_of, "missing closed daily candle")
    timestamp, values = row
    return _available_point(
        values[index], unit, timestamp,
        _daily_provenance(factor_id, (row,)),
    )


def _average_daily_point(rows, index, unit, as_of, *, factor_id):
    if any(row is None for row in rows):
        return _missing_point(as_of, "fewer than five previous closed daily candles")
    timestamps = tuple(row[0] for row in rows)
    return _available_point(
        sum((row[1][index] for row in rows), Decimal("0")) / Decimal("5"),
        unit,
        max(timestamps),
        _daily_provenance(factor_id, rows),
    )


def _first_full_minute(opened_at):
    boundary = opened_at.replace(second=0, microsecond=0)
    return boundary if opened_at == boundary else boundary + MINUTE


def _observed_post_trade_snapshot(context, requested, direction, rows, first_full, last_full, expected_count):
    candidates = {
        "adverse": [(context.opened_at, context.entry_price, "ENTRY_ENDPOINT")],
        "favorable": [(context.opened_at, context.entry_price, "ENTRY_ENDPOINT")],
    }
    for timestamp, values in rows:
        if direction == "LONG":
            candidates["adverse"].append((timestamp, values[_LOW], "KLINE_LOW"))
            candidates["favorable"].append((timestamp, values[_HIGH], "KLINE_HIGH"))
        else:
            candidates["adverse"].append((timestamp, values[_HIGH], "KLINE_HIGH"))
            candidates["favorable"].append((timestamp, values[_LOW], "KLINE_LOW"))
    candidates["adverse"].append((context.closed_at, context.exit_price, "EXIT_ENDPOINT"))
    candidates["favorable"].append((context.closed_at, context.exit_price, "EXIT_ENDPOINT"))
    adverse = _choose_extreme(candidates["adverse"], maximum=direction == "SHORT")
    favorable = _choose_extreme(candidates["favorable"], maximum=direction == "LONG")
    base_provenance = _v4_provenance(context, first_full, last_full, expected_count, rows)
    points = {}
    _set_excursion_points(
        points, requested, "mae", "adverse", adverse, context, base_provenance,
        direction,
    )
    _set_excursion_points(
        points, requested, "mfe", "favorable", favorable, context, base_provenance,
        direction,
    )
    return PostTradeMarketSnapshot(
        context.instrument_id, context.opened_at, context.closed_at, points, "BYBIT_V5_KLINE",
    )


def _choose_extreme(candidates, *, maximum):
    extreme_value = (max if maximum else min)(candidate[1] for candidate in candidates)
    return min((candidate for candidate in candidates if candidate[1] == extreme_value), key=lambda candidate: candidate[0])


def _set_excursion_points(
    points, requested, prefix, excursion_type, extreme, context, base_provenance, direction,
):
    timestamp, extreme_price, source_kind = extreme
    is_adverse = excursion_type == "adverse"
    distance = max(
        (
            context.entry_price - extreme_price
            if direction == "LONG" and is_adverse
            else extreme_price - context.entry_price
            if direction == "SHORT" and is_adverse
            else extreme_price - context.entry_price
            if direction == "LONG"
            else context.entry_price - extreme_price
        ),
        Decimal("0"),
    )
    factor_prefix = f"{prefix}_observed_1m"
    extreme_provenance = {
        **base_provenance,
        "extreme_source_kind": source_kind,
        "extreme_source_timestamp": timestamp.isoformat(),
        "extreme_price": str(extreme_price),
        "kline_extreme_timestamp_policy": "candle start timestamp; exact intraminute extreme second is unknown",
    }
    extreme_factor = f"{factor_prefix}_extreme_price"
    distance_factor = f"{factor_prefix}_price_distance"
    pct_factor = f"{factor_prefix}_pct"
    gross_factor = f"{factor_prefix}_gross_pnl_usdt"
    if extreme_factor in requested:
        points[extreme_factor] = _available_point(
            extreme_price, "USDT", timestamp, extreme_provenance,
        )
    if distance_factor in requested:
        points[distance_factor] = _available_point(
            distance, "USDT", timestamp,
            {
                **extreme_provenance,
                "calculation": _excursion_distance_formula(excursion_type, direction),
            },
        )
    if pct_factor in requested:
        if context.entry_price <= 0:
            points[pct_factor] = _missing_point_for_post_trade(context, "non-positive entry price")
        else:
            points[pct_factor] = _available_point(
                distance / context.entry_price * Decimal("100"), "percent", timestamp,
                {**extreme_provenance, "calculation": "price_distance / entry_price * 100"},
            )
    if gross_factor in requested:
        points[gross_factor] = _available_point(
            distance * context.quantity, "USDT", timestamp,
            {**extreme_provenance, "calculation": "price_distance * quantity; fees/funding/expenses excluded"},
        )


def _excursion_distance_formula(excursion_type, direction):
    formulas = {
        ("adverse", "LONG"): "max(entry_price - adverse_extreme, 0)",
        ("adverse", "SHORT"): "max(adverse_extreme - entry_price, 0)",
        ("favorable", "LONG"): "max(favorable_extreme - entry_price, 0)",
        ("favorable", "SHORT"): "max(entry_price - favorable_extreme, 0)",
    }
    return formulas[(excursion_type, direction)]


def _v4_provenance(context, first_full, last_full, expected_count, rows):
    return {
        "endpoint": "/v5/market/kline" if expected_count else None,
        "interval": "1",
        "semantic": "observed_1m_fully_contained_plus_trade_endpoints_v1",
        "opened_at": context.opened_at.isoformat(),
        "closed_at": context.closed_at.isoformat() if context.closed_at else None,
        "first_full_candle_start": first_full.isoformat() if expected_count else None,
        "last_full_candle_start": last_full.isoformat() if expected_count else None,
        "expected_full_candle_count": expected_count,
        "actual_full_candle_count": len(rows),
        "entry_endpoint_included": True,
        "exit_endpoint_included": True,
        "direction": getattr(context.direction, "value", context.direction),
        "closed_candle_policy": "only candles whose full [start, start + 1m] interval is contained in the trade interval",
    }


def _missing_point_for_post_trade(context, reason):
    return MarketDataPoint(
        value=None,
        quality_status=AutomaticFactorQuality.MISSING,
        availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        source_timestamp=None,
        provenance={"reason": reason, "opened_at": context.opened_at.isoformat()},
    )


def _capture_intraday_v2(points, requested, current_rows, minute_data, day_start, entry_minute, as_of):
    """Populate V2 factors from the one already-fetched closed intraday window."""
    first_row = current_rows[0]
    last_row = current_rows[-1]
    first_values = first_row[1]
    last_values = last_row[1]
    price = last_values[_CLOSE]
    day_open = first_values[_OPEN]
    day_high = max(row[1][_HIGH] for row in current_rows)
    day_low = min(row[1][_LOW] for row in current_rows)
    cutoff = last_row[0]
    provenance = _v2_intraday_provenance(day_start, entry_minute, current_rows)

    def set_value(factor_id, value, unit, *, source_timestamp=cutoff, extra=None):
        if factor_id in requested:
            point_provenance = provenance if extra is None else {**provenance, **extra}
            points[factor_id] = _available_point(value, unit, source_timestamp, point_provenance)

    set_value("market_price_at_entry_snapshot", price, "USDT")
    set_value("day_open_price", day_open, "USDT", source_timestamp=first_row[0])
    set_value("day_high_at_entry", day_high, "USDT")
    set_value("day_low_at_entry", day_low, "USDT")

    if day_open > 0:
        set_value("day_change_pct_at_entry", (price / day_open - Decimal("1")) * Decimal("100"), "percent")
        set_value("day_range_pct_at_entry", (day_high - day_low) / day_open * Decimal("100"), "percent")
    else:
        _mark_requested_missing(points, requested, {"day_change_pct_at_entry", "day_range_pct_at_entry"}, as_of, "non-positive day open")

    range_size = day_high - day_low
    if range_size > 0:
        set_value("day_range_position_at_entry", (price - day_low) / range_size, "ratio")
    else:
        _mark_requested_missing(points, requested, {"day_range_position_at_entry"}, as_of, "zero intraday range")

    volume, turnover = _sum_rows(current_rows)
    if volume > 0:
        vwap = turnover / volume
        set_value("vwap_1d_at_entry", vwap, "USDT")
        if vwap > 0:
            set_value("distance_to_vwap_pct", (price / vwap - Decimal("1")) * Decimal("100"), "percent")
        else:
            _mark_requested_missing(points, requested, {"distance_to_vwap_pct"}, as_of, "non-positive VWAP")
    else:
        _mark_requested_missing(points, requested, {"vwap_1d_at_entry", "distance_to_vwap_pct"}, as_of, "non-positive cumulative volume")

    if "change_24h_pct_at_entry" in requested:
        reference_timestamp = cutoff - UTC_DAY
        reference_rows = minute_data.get(reference_timestamp.date(), ())
        reference_row = next((row for row in reference_rows if row[0] == reference_timestamp), None)
        if reference_row is None or reference_row[1][_CLOSE] <= 0:
            points["change_24h_pct_at_entry"] = _missing_point(as_of, "missing exact 24-hour reference candle")
        else:
            points["change_24h_pct_at_entry"] = _available_point(
                (price / reference_row[1][_CLOSE] - Decimal("1")) * Decimal("100"),
                "percent",
                cutoff,
                {
                    **provenance,
                    "reference_candle_timestamp": reference_timestamp.isoformat(),
                    "reference_candle_close": str(reference_row[1][_CLOSE]),
                    "comparison": "exactly one UTC day before the current cutoff candle",
                },
            )


def _capture_atr_v2(points, requested, daily, day_start, current_rows, as_of):
    """Calculate arithmetic ATR14 from 15 prior fully closed UTC daily candles."""
    required_days = [day_start.date() - timedelta(days=index) for index in range(15, 0, -1)]
    rows = [daily.get(day) for day in required_days]
    atr_factor_ids = requested & _ATR_FACTORS
    if any(row is None for row in rows):
        _mark_requested_missing(points, requested, atr_factor_ids, as_of, "fewer than fifteen previous closed daily candles")
        return

    true_ranges = []
    for row, previous_row in zip(rows[1:], rows):
        high = row[1][_HIGH]
        low = row[1][_LOW]
        previous_close = previous_row[1][_CLOSE]
        true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
    atr = sum(true_ranges, Decimal("0")) / Decimal("14")
    atr_source = rows[-1][0]
    atr_provenance = {
        "endpoint": "/v5/market/kline",
        "interval": "D",
        "timezone": "UTC",
        "calculation": "arithmetic mean of 14 True Range values; not Wilder/RMA",
        "closed_only": True,
        "preceding_candle_timestamp": rows[0][0].isoformat(),
        "contributing_candle_timestamps": [row[0].isoformat() for row in rows[1:]],
        "required_candle_timestamps": [row[0].isoformat() for row in rows],
        "window_start": rows[1][0].isoformat(),
        "window_end": rows[-1][0].isoformat(),
    }
    if "atr_1d_14" in requested:
        points["atr_1d_14"] = _available_point(atr, "USDT", atr_source, atr_provenance)

    current_cutoff = current_rows[-1][0] if current_rows else atr_source
    price = current_rows[-1][1][_CLOSE] if current_rows else None
    if "atr_1d_14_pct" in requested:
        if price is not None and price > 0:
            points["atr_1d_14_pct"] = _available_point(
                atr / price * Decimal("100"),
                "percent",
                current_cutoff,
                {**atr_provenance, "derived_from": "atr_1d_14 / market_price_at_entry_snapshot"},
            )
        else:
            points["atr_1d_14_pct"] = _missing_point(as_of, "missing positive market price")

    if "day_range_to_atr" in requested:
        if current_rows and atr > 0:
            day_high = max(row[1][_HIGH] for row in current_rows)
            day_low = min(row[1][_LOW] for row in current_rows)
            points["day_range_to_atr"] = _available_point(
                (day_high - day_low) / atr,
                "ratio",
                current_cutoff,
                {**atr_provenance, "derived_from": "day_high_at_entry - day_low_at_entry / atr_1d_14"},
            )
        else:
            points["day_range_to_atr"] = _missing_point(as_of, "non-positive ATR or missing intraday range")


def _mark_requested_missing(points, requested, factor_ids, as_of, reason):
    for factor_id in requested & factor_ids:
        points[factor_id] = _missing_point(as_of, reason)


def _capture_open_interest_v3(points, requested, rows, mark_candle, oi_cutoff, as_of):
    by_timestamp = dict(rows)
    required_references = {
        "1h": oi_cutoff - timedelta(hours=1),
        "4h": oi_cutoff - timedelta(hours=4),
        "24h": oi_cutoff - UTC_DAY,
    }
    current = by_timestamp.get(oi_cutoff)
    provenance = {
        "endpoint": "/v5/market/open-interest",
        "interval": "5min",
        "oi_cutoff": oi_cutoff.isoformat(),
        "window_start": (oi_cutoff - UTC_DAY).isoformat(),
        "window_end": oi_cutoff.isoformat(),
        "closed_only": True,
        "exact_reference_timestamps": {
            label: timestamp.isoformat() for label, timestamp in required_references.items()
        },
        "available_record_count": len(rows),
        "calculation_policy": "exact timestamp lookup; nearest records are never substituted",
    }
    if current is None:
        _mark_requested_missing(points, requested, _OPEN_INTEREST_FACTORS, as_of, "missing exact OI cutoff record")
        return

    current_timestamp = oi_cutoff
    if "open_interest_base_at_entry" in requested:
        points["open_interest_base_at_entry"] = _available_point(
            current, "base", current_timestamp, provenance,
        )
    if "open_interest_notional_usdt_at_entry" in requested:
        if mark_candle is None or mark_candle[1] <= 0:
            points["open_interest_notional_usdt_at_entry"] = _missing_point(
                as_of, "missing positive mark price for OI notional",
            )
        else:
            points["open_interest_notional_usdt_at_entry"] = _available_point(
                current * mark_candle[1], "USDT", current_timestamp,
                {
                    **provenance,
                    "mark_candle_timestamp": mark_candle[0].isoformat(),
                    "calculation_policy": "open_interest_base_at_entry * mark_price_at_entry_snapshot",
                },
            )

    for label, factor_id in (
        ("1h", "open_interest_change_1h_pct_at_entry"),
        ("4h", "open_interest_change_4h_pct_at_entry"),
        ("24h", "open_interest_change_24h_pct_at_entry"),
    ):
        if factor_id not in requested:
            continue
        reference_timestamp = required_references[label]
        reference = by_timestamp.get(reference_timestamp)
        if reference is None or reference <= 0:
            points[factor_id] = _missing_point(as_of, f"missing exact OI {label} reference record")
        else:
            points[factor_id] = _available_point(
                (current / reference - Decimal("1")) * Decimal("100"),
                "percent", current_timestamp,
                {
                    **provenance,
                    "reference_timestamp": reference_timestamp.isoformat(),
                    "reference_label": label,
                    "calculation_policy": "(current / exact_reference - 1) * 100",
                },
            )


def _capture_funding_v3(points, requested, rows, as_of):
    funding_provenance = {
        "endpoint": "/v5/market/funding/history",
        "funding_cutoff": as_of.isoformat(),
        "cutoff_policy": "fundingRateTimestamp <= opened_at",
        "settled_only": True,
        "calculation_policy": "historical settled funding records; no predicted/current ticker funding",
    }
    if not rows:
        _mark_requested_missing(points, requested, _FUNDING_FACTORS, as_of, "missing settled funding history")
        return

    latest_timestamp, latest_rate = rows[-1]
    latest_three = rows[-3:]
    latest_two = rows[-2:]
    latest_provenance = {
        **funding_provenance,
        "settlement_timestamp": latest_timestamp.isoformat(),
        "settlement_timestamps": [timestamp.isoformat() for timestamp, _ in latest_three],
    }
    if "last_settled_funding_rate_at_entry" in requested:
        points["last_settled_funding_rate_at_entry"] = _available_point(
            latest_rate, "ratio", latest_timestamp, latest_provenance,
        )
    if "avg_last_3_settled_funding_rate_at_entry" in requested:
        if len(latest_three) < 3:
            points["avg_last_3_settled_funding_rate_at_entry"] = _missing_point(
                as_of, "fewer than three settled funding records",
            )
        else:
            points["avg_last_3_settled_funding_rate_at_entry"] = _available_point(
                sum((rate for _, rate in latest_three), Decimal("0")) / Decimal("3"),
                "ratio", latest_timestamp,
                {
                    **latest_provenance,
                    "settlement_timestamps": [timestamp.isoformat() for timestamp, _ in latest_three],
                    "calculation_policy": "arithmetic mean of latest 3 settled funding rates",
                },
            )

    interval_minutes = None
    if len(latest_two) >= 2:
        interval_delta = latest_two[-1][0] - latest_two[-2][0]
        interval_microseconds = _timedelta_microseconds(interval_delta)
        if interval_microseconds > 0 and interval_microseconds % 60_000_000 == 0:
            interval_minutes = interval_microseconds // 60_000_000
    interval_provenance = {
        **latest_provenance,
        "previous_settlement_timestamp": latest_two[-2][0].isoformat() if len(latest_two) >= 2 else None,
        "inferred_interval_minutes": interval_minutes,
        "calculation_policy": "latest settlement timestamp minus previous settlement timestamp",
    }
    if "funding_interval_minutes_inferred_at_entry" in requested:
        if interval_minutes is None:
            points["funding_interval_minutes_inferred_at_entry"] = _missing_point(
                as_of, "funding interval cannot be inferred from two settlements",
            )
        else:
            points["funding_interval_minutes_inferred_at_entry"] = _available_point(
                interval_minutes, "minutes", latest_timestamp, interval_provenance,
            )

    since_minutes = _timedelta_minutes(as_of - latest_timestamp)
    if "minutes_since_last_funding_at_entry" in requested:
        if since_minutes < 0:
            points["minutes_since_last_funding_at_entry"] = _missing_point(as_of, "negative time since funding")
        else:
            points["minutes_since_last_funding_at_entry"] = _available_point(
                since_minutes, "minutes", latest_timestamp,
                {**latest_provenance, "calculation_policy": "(opened_at - latest_settlement) in exact minutes"},
            )
    if "minutes_to_next_funding_inferred_at_entry" in requested:
        if interval_minutes is None:
            points["minutes_to_next_funding_inferred_at_entry"] = _missing_point(
                as_of, "funding interval unavailable for next settlement",
            )
        else:
            next_expected = latest_timestamp + timedelta(minutes=interval_minutes)
            until_next = _timedelta_minutes(next_expected - as_of)
            if until_next < 0:
                points["minutes_to_next_funding_inferred_at_entry"] = _missing_point(
                    as_of, "inferred next funding is in the past",
                )
            else:
                points["minutes_to_next_funding_inferred_at_entry"] = _available_point(
                    until_next, "minutes", latest_timestamp,
                    {
                        **interval_provenance,
                        "next_expected_settlement_timestamp": next_expected.isoformat(),
                        "calculation_policy": "latest_settlement + inferred_interval - opened_at",
                    },
                )


def _floor_5_minutes(value):
    return value.replace(minute=(value.minute // 5) * 5, second=0, microsecond=0)


def _timedelta_microseconds(value):
    return (value.days * 86_400 + value.seconds) * 1_000_000 + value.microseconds


def _timedelta_minutes(value):
    return Decimal(_timedelta_microseconds(value)) / Decimal(60_000_000)


def _derivatives_price_provenance(kind, price_cutoff, source_timestamp):
    return {
        "endpoint": f"/v5/market/{kind}-price-kline",
        "interval": "1",
        "timezone": "UTC",
        "price_cutoff": price_cutoff.isoformat(),
        "source_candle_timestamp": source_timestamp.isoformat(),
        "closed_only": True,
        "calculation_policy": "exact closed 1m candle at price_cutoff; no nearest substitution",
    }


def _basis_provenance(price_cutoff, mark_timestamp, index_timestamp):
    return {
        "source_endpoints": [
            "/v5/market/mark-price-kline",
            "/v5/market/index-price-kline",
        ],
        "price_cutoff": price_cutoff.isoformat(),
        "mark_candle_timestamp": mark_timestamp.isoformat(),
        "index_candle_timestamp": index_timestamp.isoformat(),
        "closed_only": True,
        "calculation": "(mark / index - 1) * 100",
        "calculation_policy": "exact closed 1m candles at price_cutoff; no nearest substitution and no look-ahead",
    }


def _v2_intraday_provenance(day_start, entry_minute, rows):
    return {
        "endpoint": "/v5/market/kline",
        "interval": "1",
        "timezone": "UTC",
        "utc_day_start": day_start.isoformat(),
        "cutoff_candle_timestamp": rows[-1][0].isoformat(),
        "contributing_intraday_start": rows[0][0].isoformat(),
        "contributing_intraday_end": rows[-1][0].isoformat(),
        "contributing_intraday_count": len(rows),
        "lookahead_policy": "exclude entry minute; use fully closed candles through cutoff",
    }


def _missing_point(as_of, reason):
    return MarketDataPoint(
        value=None, quality_status=AutomaticFactorQuality.MISSING,
        availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
        source_timestamp=None, provenance={"reason": reason, "as_of": as_of.isoformat()},
    )


def _missing_snapshot(instrument_id, as_of, factor_ids, reason):
    return MarketDataSnapshot(
        instrument_id, as_of,
        {factor_id: _missing_point(as_of, reason) for factor_id in factor_ids},
        BybitMarketDataProvider.provider_key,
    )


def _missing_post_trade_snapshot(context, factor_ids, reason, *, provenance=None):
    base_provenance = {
        "semantic": "observed_1m_fully_contained_plus_trade_endpoints_v1",
        "reason": reason,
        "opened_at": context.opened_at.isoformat(),
        "closed_at": context.closed_at.isoformat() if context.closed_at else None,
    }
    if provenance:
        base_provenance.update(provenance)
    return PostTradeMarketSnapshot(
        context.instrument_id, context.opened_at, context.closed_at,
        {
            factor_id: MarketDataPoint(
                value=None,
                quality_status=AutomaticFactorQuality.MISSING,
                availability_status=AutomaticFactorAvailability.MISSING_SOURCE_DATA,
                source_timestamp=None,
                provenance=base_provenance,
            )
            for factor_id in factor_ids
        },
        "BYBIT_V5_KLINE",
    )


def _not_applicable_post_trade_snapshot(context, factor_ids, reason):
    return PostTradeMarketSnapshot(
        context.instrument_id, context.opened_at, context.closed_at,
        {
            factor_id: MarketDataPoint(
                value=None,
                quality_status=AutomaticFactorQuality.MISSING,
                availability_status=AutomaticFactorAvailability.NOT_APPLICABLE,
                source_timestamp=None,
                provenance={"semantic": "observed_1m_fully_contained_plus_trade_endpoints_v1", "reason": reason},
            )
            for factor_id in factor_ids
        },
        "BYBIT_V5_KLINE",
    )


def _utc(value, name):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _epoch_millis(value):
    return int((value - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1000)


def _minute_provenance(day_start, entry_minute, rows):
    return {
        "endpoint": "/v5/market/kline",
        "interval": "1",
        "timezone": "UTC",
        "current_cutoff": (entry_minute - MINUTE).isoformat(),
        "candle_count": len(rows),
        "used_candle_start": rows[0][0].isoformat(),
        "used_candle_end": rows[-1][0].isoformat(),
        "lookahead_policy": "exclude entry minute; use closed candles through cutoff",
    }


def _rvol_provenance(day_start, entry_minute, current_rows, minute_data):
    comparison_days = []
    for index in range(1, 6):
        day = day_start - timedelta(days=index)
        rows = minute_data.get(day.date(), ())
        comparison_days.append({
            "date": day.date().isoformat(),
            "cutoff": (day + (entry_minute - day_start) - MINUTE).isoformat(),
            "used_candle_start": rows[0][0].isoformat(),
            "used_candle_end": rows[-1][0].isoformat(),
            "candle_count": len(rows),
        })
    return {
        **_minute_provenance(day_start, entry_minute, current_rows),
        "historical_window_start": (day_start - 5 * UTC_DAY).isoformat(),
        "historical_window_end": (day_start - UTC_DAY + (entry_minute - day_start) - MINUTE).isoformat(),
        "comparison_days": comparison_days,
        "comparison": "average cumulative volume through the same elapsed UTC-day minute over five prior full days",
    }


def _daily_provenance(factor_id, rows):
    timestamps = tuple(row[0] for row in rows)
    return {
        "endpoint": "/v5/market/kline",
        "interval": "D",
        "timezone": "UTC",
        "factor_id": factor_id,
        "window_start": min(timestamps).isoformat(),
        "window_end": max(timestamps).isoformat(),
        "contributing_candles": [timestamp.isoformat() for timestamp in sorted(timestamps)],
        "closed_only": True,
    }
