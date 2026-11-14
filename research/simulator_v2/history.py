"""Bounded, strictly closed M1 history for isolated Simulator 2.0.

Uses the existing research Candle type and the prototype's proven backwards
pagination contract. Its only optional network operation is an unsigned GET to
Bybit's PUBLIC market/kline endpoint; no account or trading API is imported.
Chunks may be consumed sequentially by IsolatedTimeline without retaining
the full 30/90-day range in memory. Nothing is written to disk.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import re
from typing import Callable, Iterator, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from research.historical_market_replay import Candle
from research.simulator_v2.timeline import MINUTE_MS, SYMBOL_RE

PUBLIC_KLINE_URL = "https://api.bybit.com/v5/market/kline"
MAX_RESPONSE_BYTES = 2_000_000
SOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")
FetchCandles = Callable[..., object]


@dataclass(frozen=True)
class HistoryChunk:
    symbol: str
    start_ms: int
    end_ms: int  # exclusive
    source_id: str
    candles: tuple[Candle, ...]
    sha256: str


def last_closed_m1_boundary_ms() -> int:
    """UTC timestamp after the latest complete minute, NOT the forming one."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return (now_ms // MINUTE_MS) * MINUTE_MS


def fetch_public_m1_klines(symbol: str, interval: str, limit: int, *, end_ms: int):
    """ONLY public, unsigned, GET /v5/market/kline; no configurable URL."""
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("invalid public M1 symbol")
    if interval != "1" or type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("only M1 historical candles are allowed")
    if type(end_ms) is not int or end_ms < 0:
        raise ValueError("invalid M1 history cursor")
    query = urlencode({
        "category": "linear", "symbol": symbol,
        "interval": "1", "limit": limit, "end": end_ms,
    })
    request = Request(
        PUBLIC_KLINE_URL + "?" + query,
        headers={
            "User-Agent": "BybitScanner-SimulatorV2-Research/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(request, timeout=12) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("public candle response exceeds size limit")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or payload.get("retCode") != 0:
        raise ValueError("public M1 market history request was rejected")
    result = payload.get("result")
    rows = result.get("list") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError("malformed public M1 market response")
    normalized = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            raise ValueError("invalid public M1 candle row")
        normalized.append({
            "time": row[0], "open": row[1], "high": row[2],
            "low": row[3], "close": row[4], "volume": row[5],
        })
    return normalized


def _load_exact_chunk(
    *, symbol: str, start_ms: int, end_ms: int,
    page_limit: int, fetch_candles: FetchCandles,
) -> tuple[Candle, ...]:
    """Same fail-closed backward cursor convention as the existing M5 loader."""
    expected_count = (end_ms - start_ms) // MINUTE_MS
    collected: dict[int, Candle] = {}
    cursor = end_ms - 1
    for _ in range(expected_count + 2):
        raw = fetch_candles(symbol, "1", page_limit, end_ms=cursor)
        rows = raw.to_dict(orient="records") if hasattr(raw, "to_dict") else raw
        if not isinstance(rows, (list, tuple)) or not rows:
            raise ValueError("M1 history ended before requested range")
        oldest = None
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("invalid historical M1 row")
            timestamp = int(row["time"])
            if timestamp > cursor:
                continue  # Ignore an incorrectly returned future/forming candle.
            if timestamp < 0 or timestamp % MINUTE_MS:
                raise ValueError("unaligned M1 historical timestamp")
            oldest = timestamp if oldest is None else min(oldest, timestamp)
            if start_ms <= timestamp < end_ms:
                candle = Candle(
                    start_ms=timestamp, interval_ms=MINUTE_MS,
                    open=row["open"], high=row["high"], low=row["low"],
                    close=row["close"], volume=row["volume"],
                )
                if timestamp in collected and collected[timestamp] != candle:
                    raise ValueError("conflicting duplicate historical M1 candle")
                collected[timestamp] = candle
        if oldest is None or oldest >= cursor:
            raise ValueError("M1 history pagination did not advance")
        if oldest <= start_ms:
            break
        cursor = oldest - 1
    else:
        raise ValueError("M1 history pagination exceeded strict bound")
    expected = range(start_ms, end_ms, MINUTE_MS)
    if any(timestamp not in collected for timestamp in expected):
        raise ValueError("gap in historical M1 archive; refusing fabricated replay")
    return tuple(collected[timestamp] for timestamp in expected)


def iter_closed_m1_chunks(
    *, symbol: str, start_ms: int, end_ms: int,
    latest_closed_boundary_ms: int,
    chunk_minutes: int = 1440,
    page_limit: int = 1000,
    fetch_candles: FetchCandles = fetch_public_m1_klines,
    source_id: str = "BYBIT_PUBLIC_V5_M1",
) -> Iterator[HistoryChunk]:
    """Yield complete UTC-aligned chunks. No partial/unchecked chunk is emitted.

    Pass an independently established close cutoff; a live caller should use
    last_closed_m1_boundary_ms(). Inject a fixture fetch for offline tests.
    Re-run a failed chunk rather than proceeding over missing price history.
    """
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("single run needs a linear USDT symbol")
    if any(type(v) is not int for v in (
        start_ms, end_ms, latest_closed_boundary_ms, chunk_minutes, page_limit
    )):
        raise ValueError("M1 history bounds and sizes must be integers")
    if (
        start_ms < 0 or end_ms <= start_ms
        or start_ms % MINUTE_MS or end_ms % MINUTE_MS
        or end_ms > latest_closed_boundary_ms
        or latest_closed_boundary_ms % MINUTE_MS
    ):
        raise ValueError("requested M1 history is incomplete or not UTC-aligned")
    if not 1 <= chunk_minutes <= 10080 or not 1 <= page_limit <= 1000:
        raise ValueError("invalid bounded history paging configuration")
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("invalid market archive source identity")
    if not callable(fetch_candles):
        raise TypeError("read-only historical market fetch callback is required")

    cursor = start_ms
    while cursor < end_ms:
        chunk_end = min(end_ms, cursor + chunk_minutes * MINUTE_MS)
        candles = _load_exact_chunk(
            symbol=symbol, start_ms=cursor, end_ms=chunk_end,
            page_limit=page_limit, fetch_candles=fetch_candles,
        )
        canonical = [
            [c.start_ms, *(str(getattr(c, key)) for key in
                ("open", "high", "low", "close", "volume"))]
            for c in candles
        ]
        digest = hashlib.sha256(
            json.dumps(canonical, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        yield HistoryChunk(symbol, cursor, chunk_end, source_id, candles, digest)
        cursor = chunk_end
