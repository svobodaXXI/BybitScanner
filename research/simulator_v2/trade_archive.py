"""Offline import of Bybit public linear-perpetual DAILY TRADES into derived M1.

This is NOT Bybit's official OHLCV kline stream. The M1 candles are aggregated
from recorded trades. Only a user-supplied local CSV.gz file is read; this
module does not fetch URLs, authenticate, place orders, or touch PAPER/MAIN.

Bybit public trade archive layout (NOT an account API):
https://public.bybit.com/trading/{symbol}/{symbol}{YYYY-MM-DD}.csv.gz
Expected CSV: timestamp (Unix seconds), symbol, price, size, trdMatchID.
Missing any minute fails CLOSED rather than inventing last-price candles.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
import gzip
import hashlib
from pathlib import Path

from research.historical_market_replay import Candle
from research.simulator_v2.cache import _checksum, _rows
from research.simulator_v2.history import HistoryChunk, MINUTE_MS
from research.simulator_v2.timeline import SYMBOL_RE

SOURCE_ID = "BYBIT_PUBLIC_TRADES_DERIVED_M1"
MAX_ARCHIVE_BYTES = 128_000_000
MAX_RECORDS = 12_000_000
NEEDED_COLUMNS = {"timestamp", "symbol", "size", "price", "trdMatchID"}


def parse_local_trade_day(
    path: Path, *, symbol: str, utc_day: date,
    latest_closed_boundary_ms: int,
) -> tuple[HistoryChunk, str]:
    """Return exactly 1440 trade-derived M1 bars plus compressed-file SHA256.

    Trading day is UTC midnight-to-midnight, exclusive end. File name must
    match the documented Bybit *linear* archive convention. Caller is
    responsible for verifying provenance of any locally supplied file; a
    matching name and hash alone do NOT prove it came from Bybit.
    """
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise ValueError("explicit regular local trade CSV.gz required")
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("invalid Bybit linear symbol")
    if type(utc_day) is not date:
        raise ValueError("explicit UTC date required")
    if path.name != f"{symbol}{utc_day.isoformat()}.csv.gz":
        raise ValueError("Bybit public linear trade file name mismatch")
    if type(latest_closed_boundary_ms) is not int:
        raise ValueError("closed market boundary must be integer milliseconds")

    start = int(datetime(utc_day.year, utc_day.month, utc_day.day,
                         tzinfo=timezone.utc).timestamp() * 1000)
    end = start + 1440 * MINUTE_MS
    if start < 0 or end > latest_closed_boundary_ms or latest_closed_boundary_ms % MINUTE_MS:
        raise ValueError("day includes unclosed, future or invalid M1 candles")
    if not 0 < path.stat().st_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("empty or oversized Bybit public trades archive")

    # The archive may be newest-first or unsorted. Build OHLC by timestamp,
    # never by the arbitrary CSV file traversal order.
    minute_bars: dict[int, dict[str, object]] = {}
    rows = 0
    with gzip.open(path, mode="rt", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(set(reader.fieldnames))
            or not NEEDED_COLUMNS.issubset(reader.fieldnames)
        ):
            raise ValueError("unsupported Bybit public trade CSV column schema")
        for line in reader:
            rows += 1
            if rows > MAX_RECORDS:
                raise ValueError("Bybit trade archive exceeds bounded row limit")
            if line.get("symbol") != symbol or any(line.get(col) is None for col in NEEDED_COLUMNS):
                raise ValueError("invalid/foreign Bybit trade row")
            if not line["trdMatchID"]:
                raise ValueError("missing public trade identifier")
            try:
                stamp = Decimal(line["timestamp"])
                price = Decimal(line["price"])
                quantity = Decimal(line["size"])
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("malformed trade price, size or timestamp") from exc
            if (
                not stamp.is_finite() or not price.is_finite() or not quantity.is_finite()
                or stamp < 0 or price <= 0 or quantity <= 0
            ):
                raise ValueError("invalid numeric Bybit trade data")
            timestamp_ms = int((stamp * 1000).to_integral_value(rounding=ROUND_FLOOR))
            if not start <= timestamp_ms < end:
                raise ValueError("foreign UTC day in trade archive")
            minute_start = (timestamp_ms // MINUTE_MS) * MINUTE_MS
            item = minute_bars.get(minute_start)
            if item is None:
                minute_bars[minute_start] = {
                    "first": (stamp, line["trdMatchID"]),
                    "last": (stamp, line["trdMatchID"]),
                    "open": price, "close": price, "high": price,
                    "low": price, "volume": quantity,
                }
                continue
            # Trade ID as stable tie-breaker for identical timestamps.
            # Such a tie may differ from actual exchange execution ordering;
            # retain DERIVED provenance and never claim official Kline parity.
            order = (stamp, line["trdMatchID"])
            if order < item["first"]:
                item["first"], item["open"] = order, price
            if order > item["last"]:
                item["last"], item["close"] = order, price
            item["high"] = max(item["high"], price)
            item["low"] = min(item["low"], price)
            item["volume"] += quantity

    if len(minute_bars) != 1440:
        raise ValueError(f"missing {1440 - len(minute_bars)} trade-derived M1 minutes")
    candles = tuple(
        Candle(
            start_ms=start + i * MINUTE_MS, interval_ms=MINUTE_MS,
            open=minute_bars[start + i * MINUTE_MS]["open"],
            high=minute_bars[start + i * MINUTE_MS]["high"],
            low=minute_bars[start + i * MINUTE_MS]["low"],
            close=minute_bars[start + i * MINUTE_MS]["close"],
            volume=minute_bars[start + i * MINUTE_MS]["volume"],
        )
        for i in range(1440)
    )
    raw_sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            raw_sha.update(block)
    archive_hash = raw_sha.hexdigest()
    return (
        HistoryChunk(
            symbol=symbol, start_ms=start, end_ms=end,
            source_id=SOURCE_ID, candles=candles, sha256=_checksum(_rows(candles)),
        ),
        archive_hash,
    )
