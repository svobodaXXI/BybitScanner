"""Scanner-owned geometry cursor anchor and restart projection for Robot v0.1.

The Scanner GeometryModel uses a positional candle index inside the analysis window.
That raw index is not durable across a rolling-window reload.  This module freezes an
anchor made from the Scanner geometry index plus the source candle timestamp, then
projects later closed 1m candle timestamps back into the same frozen index space.

No geometry is refit here and no trading action is performed.
"""

from __future__ import annotations

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


def project_latest_geometry_index(
    signal_snapshot: Mapping[str, Any],
    *,
    latest_closed_candle_time_ms: int,
) -> int:
    """Map a later closed 1m candle timestamp into frozen Scanner index space."""

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


class ScannerGeometryCursorProvider:
    """Translate current closed-candle time into one candidate's frozen index space."""

    def __init__(self, latest_closed_candle_time_provider) -> None:
        self._latest_closed_candle_time_provider = latest_closed_candle_time_provider

    def __call__(self, symbol: str, signal_snapshot: Mapping[str, Any]) -> int:
        symbol_value = str(symbol).strip()
        if not symbol_value:
            raise ScannerGeometryCursorError("symbol is required")
        latest_time = self._latest_closed_candle_time_provider(symbol_value)
        return project_latest_geometry_index(
            signal_snapshot,
            latest_closed_candle_time_ms=latest_time,
        )
