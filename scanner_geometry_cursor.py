"""Scanner-owned geometry cursor anchor and restart projection for Robot v0.1.

The Scanner GeometryModel uses a positional candle index inside the analysis window.
That raw index is not durable across a rolling-window reload. This module freezes an
anchor made from the Scanner geometry index plus the source candle timestamp, then
projects later closed 1m candle timestamps back into the same frozen index space.

No geometry is refit here and no trading action is performed.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


CURSOR_VERSION = "1.0"
ONE_MINUTE_MS = 60_000


class ScannerGeometryCursorError(RuntimeError):
    """Raised when a Scanner cursor anchor cannot be trusted."""


def build_scanner_geometry_cursor_anchor(
    *,
    geometry_index: int,
    source_candle_time_ms: int,
    timeframe: str,
) -> dict[str, object]:
    """Freeze the Scanner candle-index/timestamp relationship for one signal."""

    if isinstance(geometry_index, bool) or not isinstance(geometry_index, int) or geometry_index < 0:
        raise ScannerGeometryCursorError("geometry_index must be a non-negative integer")
    if (
        isinstance(source_candle_time_ms, bool)
        or not isinstance(source_candle_time_ms, int)
        or source_candle_time_ms <= 0
    ):
        raise ScannerGeometryCursorError("source_candle_time_ms must be a positive integer")
    normalized_timeframe = str(timeframe).strip()
    if normalized_timeframe != "1":
        raise ScannerGeometryCursorError("Robot v0.1 geometry cursor requires 1m timeframe")

    return {
        "version": CURSOR_VERSION,
        "timeframe": normalized_timeframe,
        "geometry_index": geometry_index,
        "source_candle_time_ms": source_candle_time_ms,
    }


def _anchor_values(signal_snapshot: Mapping[str, Any]) -> tuple[int, int]:
    if not isinstance(signal_snapshot, Mapping):
        raise ScannerGeometryCursorError("signal snapshot must be a mapping")
    anchor = signal_snapshot.get("scanner_geometry_cursor")
    if not isinstance(anchor, Mapping):
        raise ScannerGeometryCursorError("signal snapshot has no Scanner geometry cursor anchor")
    if anchor.get("version") != CURSOR_VERSION:
        raise ScannerGeometryCursorError("unsupported Scanner geometry cursor version")
    if str(anchor.get("timeframe", "")).strip() != "1":
        raise ScannerGeometryCursorError("Scanner geometry cursor timeframe is not 1m")

    geometry_index = anchor.get("geometry_index")
    source_time = anchor.get("source_candle_time_ms")
    if isinstance(geometry_index, bool) or not isinstance(geometry_index, int) or geometry_index < 0:
        raise ScannerGeometryCursorError("Scanner geometry cursor index is invalid")
    if isinstance(source_time, bool) or not isinstance(source_time, int) or source_time <= 0:
        raise ScannerGeometryCursorError("Scanner geometry cursor source time is invalid")
    return geometry_index, source_time


def _frozen_apex_index(signal_snapshot: Mapping[str, Any]) -> float:
    geometry = signal_snapshot.get("geometry") if isinstance(signal_snapshot, Mapping) else None
    apex = geometry.get("apex") if isinstance(geometry, Mapping) else None
    value = apex.get("index") if isinstance(apex, Mapping) else None
    if isinstance(value, bool):
        raise ScannerGeometryCursorError("frozen apex index is invalid")
    try:
        apex_index = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ScannerGeometryCursorError("frozen apex index is invalid") from exc
    if not math.isfinite(apex_index):
        raise ScannerGeometryCursorError("frozen apex index is invalid")
    return apex_index


def project_latest_geometry_index(
    signal_snapshot: Mapping[str, Any],
    *,
    latest_closed_candle_time_ms: int,
) -> int:
    """Map a later closed 1m candle timestamp into frozen Scanner index space."""

    geometry_index, source_time = _anchor_values(signal_snapshot)
    if (
        isinstance(latest_closed_candle_time_ms, bool)
        or not isinstance(latest_closed_candle_time_ms, int)
        or latest_closed_candle_time_ms <= 0
    ):
        raise ScannerGeometryCursorError("latest closed candle time is invalid")
    if latest_closed_candle_time_ms < source_time:
        raise ScannerGeometryCursorError("latest closed candle predates Scanner cursor anchor")

    elapsed = latest_closed_candle_time_ms - source_time
    if elapsed % ONE_MINUTE_MS != 0:
        raise ScannerGeometryCursorError("closed candle time is not aligned to Scanner 1m index space")

    return geometry_index + elapsed // ONE_MINUTE_MS


def latest_scanner_closed_candle_time_ms(symbol: str) -> int:
    """Load Scanner 1m candles and conservatively return the latest proven closed bar.

    Bybit's newest kline may still be forming. The second-newest sorted kline is
    therefore used as the recovery evidence. Any unavailable/invalid evidence
    raises and leaves Robot recovery fail-closed.
    """

    from analyzer.candles import load_candles

    frame = load_candles(symbol, "1", 3, minimum=2)
    if frame is None or len(frame) < 2 or "time" not in frame.columns:
        raise ScannerGeometryCursorError("Scanner closed 1m candle evidence is unavailable")
    try:
        value = int(frame.iloc[-2]["time"])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ScannerGeometryCursorError("Scanner closed 1m candle time is invalid") from exc
    if value <= 0:
        raise ScannerGeometryCursorError("Scanner closed 1m candle time is invalid")
    return value


def latest_scanner_closed_candle(symbol: str) -> dict[str, object] | None:
    """Load Scanner 1m candles and return the latest proven closed OHLC bar.

    Mirrors ``latest_scanner_closed_candle_time_ms``'s conservative
    second-newest-kline evidence, but returns the OHLC values a lifecycle
    consumer needs instead of only the timestamp. Unlike that function this
    returns ``None`` (never raises) on any unavailable/invalid evidence, so a
    periodic caller can simply retry on its next tick.
    """

    from analyzer.candles import load_candles

    frame = load_candles(symbol, "1", 3, minimum=2)
    if frame is None or len(frame) < 2:
        return None
    if not {"time", "high", "low", "close"}.issubset(frame.columns):
        return None
    row = frame.iloc[-2]
    try:
        time_ms = int(row["time"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
    except (TypeError, ValueError, OverflowError):
        return None
    if time_ms <= 0:
        return None
    return {"time_ms": time_ms, "high": high, "low": low, "close": close}


def _state_candle_from_row(
    signal_snapshot: Mapping[str, Any],
    row,
) -> dict[str, object]:
    try:
        time_ms = int(row["time"])
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ScannerGeometryCursorError("catch-up candle evidence is invalid") from exc
    if time_ms <= 0 or not all(math.isfinite(value) for value in (high, low, close)):
        raise ScannerGeometryCursorError("catch-up candle evidence is invalid")
    if low > high:
        raise ScannerGeometryCursorError("catch-up candle low exceeds high")
    geometry_index = project_latest_geometry_index(
        signal_snapshot,
        latest_closed_candle_time_ms=time_ms,
    )
    return {
        "closed": True,
        "timeframe": "1",
        "time_ms": time_ms,
        "geometry_index": geometry_index,
        "high": high,
        "low": low,
        "close": close,
    }


def load_scanner_catchup_closed_candles(
    symbol: str,
    signal_snapshot: Mapping[str, Any],
    *,
    candle_loader=None,
) -> tuple[dict[str, object], ...]:
    """Return the authoritative closed 1m range needed for admission catch-up.

    The immutable Scanner cursor anchor is validated before any market-data read.
    One bounded Scanner candle request is made, sized only far enough to cover the
    frozen apex plus the currently-forming bar.  The newest returned kline is
    conservatively treated as forming, matching the existing Scanner recovery
    convention.

    If the latest proven closed candle already reaches/passes the frozen apex,
    only that candle is returned: replaying older lifecycle events cannot change
    the terminal EXPIRED_AT_APEX outcome.  Otherwise every minute strictly after
    the Scanner anchor through the latest proven closed candle must be present in
    exact chronological order; any gap, duplicate, misalignment, or malformed OHLC
    evidence fails closed.
    """

    symbol_value = str(symbol).strip()
    if not symbol_value:
        raise ScannerGeometryCursorError("symbol is required")

    anchor_index, source_time = _anchor_values(signal_snapshot)
    apex_index = _frozen_apex_index(signal_snapshot)

    if candle_loader is None:
        from analyzer.candles import load_candles

        candle_loader = load_candles

    steps_to_apex = max(0, math.ceil(apex_index - anchor_index))
    limit = max(3, steps_to_apex + 1)
    frame = candle_loader(symbol_value, "1", limit, minimum=2)
    required_columns = {"time", "high", "low", "close"}
    if frame is None or len(frame) < 2 or not required_columns.issubset(frame.columns):
        raise ScannerGeometryCursorError("Scanner catch-up candle evidence is unavailable")

    latest_row = frame.iloc[-2]
    latest_candle = _state_candle_from_row(signal_snapshot, latest_row)
    latest_time = int(latest_candle["time_ms"])
    latest_geometry_index = int(latest_candle["geometry_index"])

    if latest_geometry_index >= apex_index:
        return (latest_candle,)
    if latest_time == source_time:
        return ()

    rows = []
    times = []
    for position in range(len(frame) - 1):
        row = frame.iloc[position]
        try:
            time_ms = int(row["time"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ScannerGeometryCursorError("catch-up candle time is invalid") from exc
        if source_time < time_ms <= latest_time:
            rows.append(row)
            times.append(time_ms)

    expected_times = list(range(source_time + ONE_MINUTE_MS, latest_time + 1, ONE_MINUTE_MS))
    if times != expected_times:
        raise ScannerGeometryCursorError(
            "catch-up closed candle range is incomplete or non-contiguous"
        )

    return tuple(_state_candle_from_row(signal_snapshot, row) for row in rows)


class ScannerGeometryCursorProvider:
    """Translate current closed-candle time into one candidate's frozen index space."""

    def __init__(self, latest_closed_candle_time_provider) -> None:
        self._latest_closed_candle_time_provider = latest_closed_candle_time_provider

    def __call__(self, symbol: str, signal_snapshot: Mapping[str, Any]) -> int:
        symbol_value = str(symbol).strip()
        if not symbol_value:
            raise ScannerGeometryCursorError("symbol is required")
        # Validate the immutable Scanner anchor before any market-data/network read.
        _anchor_values(signal_snapshot)
        latest_time = self._latest_closed_candle_time_provider(symbol_value)
        return project_latest_geometry_index(
            signal_snapshot,
            latest_closed_candle_time_ms=latest_time,
        )


def default_scanner_geometry_cursor_provider() -> ScannerGeometryCursorProvider:
    return ScannerGeometryCursorProvider(latest_scanner_closed_candle_time_ms)
