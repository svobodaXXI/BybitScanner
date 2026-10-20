"""Read-only projection of a frozen Scanner signal snapshot into candle-time boundaries.

The Scanner stores wedge geometry in positional indices of its analysis candle
window (``analyzer.core``: ``current_index = len(df) - 1`` and
``scanner_source_candle_time_ms`` = open time of ``df.iloc[current_index]``).
A position is converted to a candle open time only when the snapshot itself
proves the conversion: ``scanner_formation_id`` records the open times of the two
line anchors, and both must be reproduced exactly by
``source_time - (current_index - index) * interval``. Anything else is reported
as unavailable; no geometry is refit, rounded or approximated.
"""

from __future__ import annotations

import math
import re
from typing import Any, Mapping

SIGNAL_ID_PATTERN = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
MINUTE_MS = 60_000
_PRICE_TOLERANCE = 0.01


class SignalGeometryUnavailable(Exception):
    """The frozen snapshot cannot prove a candle-time geometry."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SignalGeometryUnavailable(f"{name}_invalid")
    return value


def _price(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise SignalGeometryUnavailable(f"{name}_invalid")
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        raise SignalGeometryUnavailable(f"{name}_invalid") from None
    if not math.isfinite(parsed) or parsed <= 0:
        raise SignalGeometryUnavailable(f"{name}_invalid")
    return parsed


def build_signal_geometry(
    candidate_id: str, snapshot: Mapping[str, Any], snapshot_sha256: str,
) -> dict[str, Any]:
    """Frozen two-boundary geometry in candle open times (UTC ms), or raise."""
    if not isinstance(snapshot, Mapping):
        raise SignalGeometryUnavailable("snapshot_invalid")
    geometry = snapshot.get("geometry")
    if not isinstance(geometry, Mapping):
        raise SignalGeometryUnavailable("geometry_absent")
    timeframe = str(snapshot.get("scanner_source_timeframe", "")).strip()
    if not timeframe.isdigit() or int(timeframe) <= 0:
        raise SignalGeometryUnavailable("source_timeframe_unsupported")
    interval_ms = int(timeframe) * MINUTE_MS
    source_time = _int(snapshot.get("scanner_source_candle_time_ms"), "source_candle_time")
    current_index = _int(geometry.get("current_index"), "current_index")
    if source_time <= 0 or current_index < 0:
        raise SignalGeometryUnavailable("source_anchor_invalid")

    def open_time(index: int) -> int:
        if index < 0 or index > current_index:
            raise SignalGeometryUnavailable("index_outside_window")
        return source_time - (current_index - index) * interval_ms

    lines = {}
    for name in ("upper_line", "lower_line"):
        line = geometry.get(name)
        if not isinstance(line, Mapping):
            raise SignalGeometryUnavailable(f"{name}_absent")
        first_index = _int(line.get("anchor_index"), f"{name}.anchor_index")
        second_index = _int(line.get("second_index"), f"{name}.second_index")
        if first_index >= second_index:
            raise SignalGeometryUnavailable(f"{name}_anchor_order")
        first_price = _price(line.get("anchor_price"), f"{name}.anchor_price")
        second_price = _price(line.get("second_price"), f"{name}.second_price")
        slope = line.get("slope")
        intercept = line.get("intercept")
        for index, price in ((first_index, first_price), (second_index, second_price)):
            try:
                fitted = float(slope) * index + float(intercept)
            except (TypeError, ValueError, OverflowError):
                raise SignalGeometryUnavailable(f"{name}_model_invalid") from None
            if not math.isfinite(fitted) or abs(fitted - price) > _PRICE_TOLERANCE * price:
                raise SignalGeometryUnavailable(f"{name}_pivot_off_line")
        lines[name] = (first_index, first_price, second_index, second_price)

    formation_id = snapshot.get("scanner_formation_id")
    if not isinstance(formation_id, str) or formation_id.count(":") != 1:
        raise SignalGeometryUnavailable("formation_identity_absent")
    try:
        proven_upper, proven_lower = (int(part) for part in formation_id.split(":"))
    except ValueError:
        raise SignalGeometryUnavailable("formation_identity_invalid") from None
    if (open_time(lines["upper_line"][0]) != proven_upper
            or open_time(lines["lower_line"][0]) != proven_lower):
        raise SignalGeometryUnavailable("index_time_mapping_unproven")

    boundaries = []
    for name, kind in (("upper_line", "upper"), ("lower_line", "lower")):
        first_index, first_price, second_index, second_price = lines[name]
        boundaries.append({
            "boundary_id": f"{candidate_id}:{kind}",
            "kind": kind,
            "anchors": [
                {"bar_open_time_ms": open_time(first_index), "price": first_price},
                {"bar_open_time_ms": open_time(second_index), "price": second_price},
            ],
        })
    symbol = snapshot.get("symbol")
    return {
        "schema_version": 1,
        "signal_id": candidate_id,
        "snapshot_revision": snapshot_sha256,
        "symbol": symbol if isinstance(symbol, str) else None,
        "timeframe": timeframe,
        "pattern_type": snapshot.get("pattern") if isinstance(snapshot.get("pattern"), str) else None,
        "source_candle_time_ms": source_time,
        "interval_ms": interval_ms,
        "boundaries": boundaries,
    }
