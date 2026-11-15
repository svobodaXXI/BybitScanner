"""Bounded, local-only verified M5 history cache for Machine Time.

Only exact public Bybit klines; no arbitrary paths, PAPER, orders or credentials.
A failed/incomplete fetch cannot publish a partial cache as complete history.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import threading
from uuid import uuid4

from research.historical_candle_feed import FIVE_MINUTES_MS, load_closed_five_minute_history
from research.historical_market_replay import Candle

DAY_MS = 86_400_000
CACHE_SCHEMA = "MACHINE_TIME_PUBLIC_M5_CACHE_V1"
CACHE_LOCK = threading.Lock()
MAX_DAY_BYTES = 160_000


def _row(candle: Candle) -> dict[str, str | int]:
    return {
        "time": candle.start_ms,
        "open": str(candle.open), "high": str(candle.high),
        "low": str(candle.low), "close": str(candle.close),
        "volume": str(candle.volume),
    }


def _checked_row(row: object, *, day: int) -> Candle:
    if not isinstance(row, dict) or set(row) != {"time", "open", "high", "low", "close", "volume"}:
        raise ValueError("invalid local public M5 candle")
    time = row["time"]
    if type(time) is not int or time % FIVE_MINUTES_MS or time // DAY_MS != day:
        raise ValueError("invalid local public M5 timestamp")
    return Candle(
        start_ms=time, interval_ms=FIVE_MINUTES_MS,
        open=row["open"], high=row["high"], low=row["low"],
        close=row["close"], volume=row["volume"],
    )


def _day_file(directory: Path, symbol: str, day: int) -> Path:
    return directory / f"{symbol}-{day}.json"


def _read_day(directory: Path, symbol: str, day: int) -> dict[int, Candle]:
    path = _day_file(directory, symbol, day)
    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DAY_BYTES:
        raise ValueError("unsafe local public M5 cache file")
    raw = json.loads(path.read_bytes())
    if not isinstance(raw, dict) or raw.get("schema") != CACHE_SCHEMA or raw.get("symbol") != symbol or raw.get("day") != day:
        raise ValueError("invalid public M5 cache identity")
    rows = raw.get("candles")
    if not isinstance(rows, list) or len(rows) > 288:
        raise ValueError("invalid local public M5 cache")
    result: dict[int, Candle] = {}
    for row in rows:
        item = _checked_row(row, day=day)
        if item.start_ms in result:
            raise ValueError("duplicate local public M5 candle")
        result[item.start_ms] = item
    return result


def _write_day(directory: Path, symbol: str, day: int, rows: dict[int, Candle]) -> None:
    path = _day_file(directory, symbol, day)
    if path.is_symlink():
        raise ValueError("unsafe local public M5 cache path")
    document = {
        "schema": CACHE_SCHEMA, "symbol": symbol, "day": day,
        "candles": [_row(rows[t]) for t in sorted(rows)],
    }
    content = json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(content) > MAX_DAY_BYTES:
        raise ValueError("local public M5 cache exceeds size bound")
    temporary = directory / (path.name + "." + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as target:
            target.write(content)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def complete_history_fetch(
    *, symbol: str, start_ms: int, end_ms: int, directory: Path,
    upstream_fetch,
):
    """Return a feed adapter backed by verified local bars; fetch only missing spans.

    The caller already validates symbol, bounds and candle close time.
    The hidden 72-hour warmup is covered as well as the visible range.
    """
    if start_ms < 0 or end_ms <= start_ms or start_ms % FIVE_MINUTES_MS or end_ms % FIVE_MINUTES_MS:
        raise ValueError("invalid M5 cache bounds")
    if not symbol.endswith("USDT") or not symbol.isalnum() or len(symbol) > 30:
        raise ValueError("invalid M5 cache symbol")
    if directory.is_symlink():
        raise ValueError("unsafe public M5 cache directory")
    with CACHE_LOCK:
        directory.mkdir(parents=True, exist_ok=True)
        first_day, last_day = start_ms // DAY_MS, (end_ms - 1) // DAY_MS
        days = {day: _read_day(directory, symbol, day)
                for day in range(first_day, last_day + 1)}
        known = {t: candle for rows in days.values() for t, candle in rows.items()}
        missing = [t for t in range(start_ms, end_ms, FIVE_MINUTES_MS) if t not in known]
        spans = []
        for t in missing:
            if spans and spans[-1][1] == t:
                spans[-1] = (spans[-1][0], t + FIVE_MINUTES_MS)
            else:
                spans.append((t, t + FIVE_MINUTES_MS))
        changed = set()
        for lo, hi in spans:
            fetched = load_closed_five_minute_history(
                symbol=symbol, start_ms=lo, end_ms=hi, fetch_candles=upstream_fetch,
            )
            for candle in fetched:
                previous = known.get(candle.start_ms)
                if previous is not None and previous != candle:
                    raise ValueError("conflicting public M5 history")
                known[candle.start_ms] = candle
                day = candle.start_ms // DAY_MS
                days[day][candle.start_ms] = candle
                changed.add(day)
        if any(t not in known for t in range(start_ms, end_ms, FIVE_MINUTES_MS)):
            raise ValueError("incomplete public M5 history")
        for day in sorted(changed):
            _write_day(directory, symbol, day, days[day])
        ordered = [_row(known[t]) for t in range(start_ms, end_ms, FIVE_MINUTES_MS)]
    def read_cached(request_symbol: str, interval: str, limit: int, *, end_ms: int):
        if request_symbol != symbol or interval != "5" or not 1 <= limit <= 1000:
            raise ValueError("invalid cached M5 request")
        return [row for row in reversed(ordered) if row["time"] <= end_ms][:limit]
    return read_cached
