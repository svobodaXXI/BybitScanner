"""Server-verified, closed-candle continuation for owner retrospective reviews.

This read-only Bybit public-data query never alters the archived signal, opens a
new market stream, accesses PAPER DB, or creates a Robot trading candidate.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import time


from signal_geometry_snapshot import canonical_bytes, validate_snapshot

TF_MS = {"1": 60_000, "5": 300_000, "15": 900_000, "60": 3_600_000, "D": 86_400_000}
MAX_EXTENSION_BARS = 1000
EDITOR_STEP_BARS = 20


class RetrospectiveBarsError(ValueError):
    pass


def extension_digest(bars: list[dict]) -> str:
    return hashlib.sha256(canonical_bytes(bars)).hexdigest()


def validate_extension(snapshot: dict, bars: list[dict], as_of_ms: int) -> list[dict]:
    """Validate immutable chronological OHLC, closure, and original seam.

    The source archive remains immutable. Caller must separately establish the
    market-data provenance of these post-source candles before persisting.
    """
    if (not isinstance(snapshot, dict) or
            str(snapshot.get("timeframe")) not in TF_MS or
            not isinstance(snapshot.get("bars"), list) or not snapshot["bars"]):
        raise RetrospectiveBarsError("unsupported_source_timeframe")
    if type(as_of_ms) is not int or as_of_ms < 0:
        raise RetrospectiveBarsError("invalid_retrospective_cutoff")
    period = TF_MS[str(snapshot["timeframe"])]
    original_last = snapshot["bars"][-1]["open_time_ms"]
    if not isinstance(bars, list) or not 1 <= len(bars) <= MAX_EXTENSION_BARS:
        raise RetrospectiveBarsError("invalid_retrospective_window")
    if (as_of_ms <= original_last or as_of_ms != original_last + len(bars) * period):
        raise RetrospectiveBarsError("noncontiguous_retrospective_window")
    normalized = []
    for offset, item in enumerate(bars, 1):
        if not isinstance(item, dict) or set(item) != {
            "open_time_ms", "open", "high", "low", "close",
        }:
            raise RetrospectiveBarsError("invalid_retrospective_ohlc")
        if type(item["open_time_ms"]) is not int or (
            item["open_time_ms"] != original_last + offset * period
        ):
            raise RetrospectiveBarsError("noncontiguous_retrospective_window")
        try:
            prices = [float(item[field]) for field in ("open", "high", "low", "close")]
        except (TypeError, ValueError, OverflowError):
            raise RetrospectiveBarsError("invalid_retrospective_ohlc") from None
        import math
        op, hi, lo, close = prices
        if any(not math.isfinite(v) or v <= 0 for v in prices) or (
            lo > min(op, close) or hi < max(op, close) or lo > hi
        ):
            raise RetrospectiveBarsError("invalid_retrospective_ohlc")
        normalized.append({
            "open_time_ms": item["open_time_ms"], "open": op, "high": hi,
            "low": lo, "close": close,
        })
    extended = {**snapshot, "bars": [*snapshot["bars"], *normalized]}
    try:
        validate_snapshot(
            extended, candidate_id=snapshot["signal_id"],
            symbol=snapshot["symbol"], timeframe=snapshot["timeframe"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RetrospectiveBarsError("invalid_extended_snapshot") from exc
    return normalized


def fetch_closed_extension(
    snapshot: dict, *, as_of_ms: int | None = None, after_ms: int | None = None,
    session=None, now_ms: int | None = None,
) -> tuple[int, list[dict]]:
    """Fetch only closed, contiguous continuation candles from Bybit linear REST.

    Each owner click advances a bounded 20-candle review window. An explicit
    as_of_ms still verifies the saved contiguous snapshot. No gaps or fabricated bars.
    """
    try:
        period = TF_MS[str(snapshot["timeframe"])]
        last = snapshot["bars"][-1]["open_time_ms"]
        validate_snapshot(
            snapshot, candidate_id=snapshot["signal_id"],
            symbol=snapshot["symbol"], timeframe=snapshot["timeframe"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RetrospectiveBarsError("invalid_source_snapshot") from exc
    current = int(time.time() * 1000) if now_ms is None else now_ms
    last_closed_open = (current // period - 1) * period
    if as_of_ms is not None and after_ms is not None:
        raise RetrospectiveBarsError("invalid_retrospective_cutoff")
    if as_of_ms is None:
        previous = last if after_ms is None else after_ms
        if (type(previous) is not int or previous < last
                or (previous - last) % period != 0):
            raise RetrospectiveBarsError("invalid_retrospective_cutoff")
        maximum = min(MAX_EXTENSION_BARS, 2000 - len(snapshot["bars"]))
        if maximum <= 0 or previous >= last + maximum * period:
            raise RetrospectiveBarsError("retrospective_range_too_large")
        cutoff = min(last_closed_open, previous + EDITOR_STEP_BARS * period,
                     last + maximum * period)
        if cutoff <= previous:
            raise RetrospectiveBarsError("no_new_closed_retrospective_bars")
    else:
        cutoff = as_of_ms
    if (type(cutoff) is not int or cutoff > last_closed_open or cutoff <= last
            or (cutoff - last) % period != 0):
        raise RetrospectiveBarsError("invalid_retrospective_cutoff")
    count = (cutoff - last) // period
    if count > MAX_EXTENSION_BARS or len(snapshot["bars"]) + count > 2000:
        raise RetrospectiveBarsError("retrospective_range_too_large")
    try:
        import requests  # only during an explicit server-side market-data fetch
    except ImportError as exc:
        raise RetrospectiveBarsError("retrospective_history_unavailable") from exc
    try:
        http = session or requests
        response = http.get(
            "https://api.bybit.com/v5/market/kline",
            params={
                "category": "linear", "symbol": snapshot["symbol"],
                "interval": str(snapshot["timeframe"]),
                "start": last + period, "end": cutoff,
                "limit": count,
            },
            timeout=8,
        )
        response.raise_for_status()
        value = response.json()
        raw = value.get("result", {}).get("list", [])
        if value.get("retCode") != 0 or len(raw) != count:
            raise RetrospectiveBarsError("retrospective_history_incomplete")
        bars = []
        for item in raw:
            if not isinstance(item, list) or len(item) < 5:
                raise RetrospectiveBarsError("retrospective_history_invalid")
            bars.append({
                "open_time_ms": int(item[0]),
                **{field: float(Decimal(str(item[index])))
                   for index, field in enumerate(("open", "high", "low", "close"), start=1)},
            })
        bars.sort(key=lambda b: b["open_time_ms"])
        return cutoff, validate_extension(snapshot, bars, cutoff)
    except RetrospectiveBarsError:
        raise
    except (requests.RequestException, TypeError, ValueError, KeyError,
            InvalidOperation, OverflowError, AttributeError) as exc:
        raise RetrospectiveBarsError("retrospective_history_unavailable") from exc


def fetch_closed_trade_timeframe(
    snapshot: dict, *, interval: str, after_ms: int,
    session=None, now_ms: int | None = None,
) -> tuple[int, list[dict]]:
    """Bounded read-only historical candles for a verified archived trade signal.

    Uses the editor's public Bybit source and 20-closed-bar step. Unlike the
    immutable detector snapshot, this is a selectable display timeframe only.
    It never manufactures M1 from M5 or modifies the original geometry.
    """
    try:
        validate_snapshot(
            snapshot, candidate_id=snapshot["signal_id"],
            symbol=snapshot["symbol"], timeframe=snapshot["timeframe"],
        )
        first = snapshot["bars"][0]["open_time_ms"]
        last = snapshot["bars"][-1]["open_time_ms"]
        symbol = snapshot["symbol"]
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        raise RetrospectiveBarsError("invalid_source_snapshot") from exc
    intervals = {**TF_MS, "240": 14_400_000}
    if interval not in intervals:
        raise RetrospectiveBarsError("unsupported_trade_timeframe")
    period = intervals[interval]
    current = int(time.time() * 1000) if now_ms is None else now_ms
    if (type(after_ms) is not int or after_ms % period != 0
            or after_ms < (first // period) * period - 40 * period
            or after_ms > current or last > current):
        raise RetrospectiveBarsError("invalid_retrospective_cutoff")
    last_closed = (current // period - 1) * period
    count = min(EDITOR_STEP_BARS, (last_closed - after_ms) // period)
    if count <= 0:
        raise RetrospectiveBarsError("no_new_closed_retrospective_bars")
    cutoff = after_ms + count * period
    try:
        import requests
    except ImportError as exc:
        raise RetrospectiveBarsError("retrospective_history_unavailable") from exc
    try:
        response = (session or requests).get(
            "https://api.bybit.com/v5/market/kline",
            params={
                "category": "linear", "symbol": symbol, "interval": interval,
                "start": after_ms + period, "end": cutoff, "limit": count,
            },
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("result", {}).get("list", [])
        if payload.get("retCode") != 0 or len(raw) != count:
            raise RetrospectiveBarsError("retrospective_history_incomplete")
        parsed = []
        for item in raw:
            if not isinstance(item, list) or len(item) < 5:
                raise RetrospectiveBarsError("retrospective_history_invalid")
            parsed.append({
                "open_time_ms": int(item[0]),
                **{field: float(Decimal(str(item[index])))
                   for index, field in enumerate(("open", "high", "low", "close"), 1)},
            })
        parsed.sort(key=lambda bar: bar["open_time_ms"])
        import math
        for offset, bar in enumerate(parsed, 1):
            op, hi, lo, close = (bar[name] for name in ("open", "high", "low", "close"))
            if (bar["open_time_ms"] != after_ms + offset * period
                    or any(not math.isfinite(v) or v <= 0 for v in (op, hi, lo, close))
                    or lo > min(op, close) or hi < max(op, close) or lo > hi):
                raise RetrospectiveBarsError("invalid_retrospective_ohlc")
        return cutoff, parsed
    except RetrospectiveBarsError:
        raise
    except (requests.RequestException, TypeError, ValueError, KeyError,
            InvalidOperation, OverflowError, AttributeError) as exc:
        raise RetrospectiveBarsError("retrospective_history_unavailable") from exc
