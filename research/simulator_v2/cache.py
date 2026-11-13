"""Validated disk cache for the separate, virtual-only Simulator 2.0 M1 feed.

Stores ONLY public OHLCV history. It cannot access orders, accounts, PAPER,
Scanner/Robot runtimes, credentials, or the H-017 prototype's files. Cache
misses reuse the existing research.simulator_v2.history loader exactly.
Corrupt entries fail closed rather than silently being replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Iterator, Mapping

from research.historical_market_replay import Candle
from research.simulator_v2.history import (
    HistoryChunk, MINUTE_MS, SOURCE_ID_RE, SYMBOL_RE,
    fetch_public_m1_klines, iter_closed_m1_chunks,
)

SCHEMA_VERSION = 1


def _rows(candles: tuple[Candle, ...]) -> list[list[object]]:
    return [
        [bar.start_ms, str(bar.open), str(bar.high), str(bar.low),
         str(bar.close), str(bar.volume)]
        for bar in candles
    ]


def _checksum(rows: list[list[object]]) -> str:
    canonical = json.dumps(rows, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _load_cache(
    path: Path, *, symbol: str, start_ms: int, end_ms: int,
    source_id: str,
) -> HistoryChunk:
    if path.is_symlink():
        raise ValueError("SIMULATION candle cache must not be a symlink")
    # Bound reads: this file contains at most (end-start)/M1 OHLCV rows.
    byte_limit = 4096 + ((end_ms - start_ms) // MINUTE_MS) * 300
    with path.open("rb") as handle:
        payload = handle.read(byte_limit + 1)
    if len(payload) > byte_limit:
        raise ValueError("oversized SIMULATION candle cache")
    try:
        entry = json.loads(payload)
        if not isinstance(entry, dict) or set(entry) != {
            "schema", "symbol", "source_id", "start_ms", "end_ms",
            "sha256", "candles",
        }:
            raise ValueError("invalid SIMULATION candle cache schema")
        if (
            type(entry["schema"]) is not int or entry["schema"] != SCHEMA_VERSION
            or entry["symbol"] != symbol or entry["source_id"] != source_id
            or type(entry["start_ms"]) is not int or entry["start_ms"] != start_ms
            or type(entry["end_ms"]) is not int or entry["end_ms"] != end_ms
        ):
            raise ValueError("SIMULATION cache source/range identity mismatch")
        raw = entry["candles"]
        count = (end_ms - start_ms) // MINUTE_MS
        if not isinstance(raw, list) or len(raw) != count:
            raise ValueError("SIMULATION cache has missing candles")
        candles = []
        for index, values in enumerate(raw):
            if (
                not isinstance(values, list) or len(values) != 6
                or type(values[0]) is not int
                or values[0] != start_ms + index * MINUTE_MS
                or any(not isinstance(v, str) for v in values[1:])
            ):
                raise ValueError("SIMULATION cache has invalid candle rows")
            candles.append(Candle(
                start_ms=values[0], interval_ms=MINUTE_MS,
                open=values[1], high=values[2], low=values[3],
                close=values[4], volume=values[5],
            ))
        checksum = _checksum(_rows(tuple(candles)))
        if entry["sha256"] != checksum or raw != _rows(tuple(candles)):
            raise ValueError("SIMULATION candle cache checksum mismatch")
        return HistoryChunk(symbol, start_ms, end_ms, source_id, tuple(candles), checksum)
    except (KeyError, TypeError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError(f"invalid SIMULATION candle cache: {path.name}") from exc


def _save_cache(path: Path, chunk: HistoryChunk) -> None:
    rows = _rows(chunk.candles)
    if _checksum(rows) != chunk.sha256:
        raise ValueError("refusing to cache inconsistent historical chunk")
    record = {
        "schema": SCHEMA_VERSION, "symbol": chunk.symbol,
        "source_id": chunk.source_id, "start_ms": chunk.start_ms,
        "end_ms": chunk.end_ms, "sha256": chunk.sha256, "candles": rows,
    }
    payload = json.dumps(record, separators=(",", ":"), sort_keys=True).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".sim-v2-", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        # A cache-only atomic rename. No user-owned files are removed.
        if path.exists() or path.is_symlink():
            raise ValueError("cache collision; refusing overwrite")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def iter_cached_m1_chunks(
    *, cache_dir: Path, symbol: str, start_ms: int, end_ms: int,
    latest_closed_boundary_ms: int, chunk_minutes: int = 1440,
    page_limit: int = 1000,
    fetch_candles: Callable[..., object] = fetch_public_m1_klines,
    source_id: str = "BYBIT_PUBLIC_V5_M1",
) -> Iterator[HistoryChunk]:
    """Use only exact verified immutable chunks; fetch/store missing intervals.

    `cache_dir` must be an explicitly dedicated Simulator 2.0 data directory,
    never the H-017 folder, PAPER database directory, or a shared order ledger.
    End is exclusive. All boundaries are CLOSED UTC M1 candles.
    """
    if not SYMBOL_RE.fullmatch(symbol) or not symbol.endswith("USDT"):
        raise ValueError("invalid SIMULATION history symbol")
    if not SOURCE_ID_RE.fullmatch(source_id):
        raise ValueError("invalid source identity")
    if any(type(v) is not int for v in (
        start_ms, end_ms, latest_closed_boundary_ms, chunk_minutes, page_limit
    )):
        raise ValueError("history coordinates must be integers")
    if (
        start_ms < 0 or end_ms <= start_ms
        or start_ms % MINUTE_MS or end_ms % MINUTE_MS
        or latest_closed_boundary_ms % MINUTE_MS
        or end_ms > latest_closed_boundary_ms
        or not 1 <= chunk_minutes <= 10080
        or not 1 <= page_limit <= 1000
    ):
        raise ValueError("invalid or unclosed SIMULATION history range")
    if not callable(fetch_candles):
        raise TypeError("public read-only historical fetch callback required")
    if not isinstance(cache_dir, Path):
        raise TypeError("explicit Path to dedicated cache directory required")
    if cache_dir.is_symlink():
        raise ValueError("SIMULATION cache directory cannot be a symlink")

    cursor = start_ms
    while cursor < end_ms:
        chunk_end = min(end_ms, cursor + chunk_minutes * MINUTE_MS)
        source_key = hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:20]
        path = cache_dir / f"m1_{symbol}_{cursor}_{chunk_end}_{source_key}.json"
        if path.exists() or path.is_symlink():
            chunk = _load_cache(
                path, symbol=symbol, start_ms=cursor,
                end_ms=chunk_end, source_id=source_id,
            )
        else:
            chunk = next(iter_closed_m1_chunks(
                symbol=symbol, start_ms=cursor, end_ms=chunk_end,
                latest_closed_boundary_ms=latest_closed_boundary_ms,
                chunk_minutes=chunk_minutes, page_limit=page_limit,
                fetch_candles=fetch_candles, source_id=source_id,
            ))
            cache_dir.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                chunk = _load_cache(
                    path, symbol=symbol, start_ms=cursor,
                    end_ms=chunk_end, source_id=source_id,
                )
            else:
                _save_cache(path, chunk)
        yield chunk
        cursor = chunk_end
