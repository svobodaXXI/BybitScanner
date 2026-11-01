"""Freeze the exact MIRROR lines already persisted for one Telegram event.

No new detector, no latest-candle reconstruction, no inference from the PNG.
Only the selected level and any same-origin source levels from the frozen event.
"""
from __future__ import annotations

import math

from signal_geometry_snapshot import validate_snapshot


def build_mirror_geometry_snapshot(signal_id, frozen):
    if not isinstance(frozen, dict):
        return None
    try:
        bars = frozen.get("geometry_candles") or frozen["candles"]
        symbol, timeframe = str(frozen["symbol"]), str(frozen["timeframe"])
        if not isinstance(bars, list) or not bars:
            return None
        bar_times = {bar["open_time_ms"] for bar in bars}
        result = []
        selected_count = 0
        seen = set()
        for level in frozen["levels"]:
            name = level["level_id"]
            if name in seen:
                return None
            seen.add(name)
            is_selected = level.get("selected") is True
            if is_selected:
                selected_count += 1
            # The source level might predate the bounded frozen candle chart.
            # Do not shift its true anchor to a different candle.
            anchors = level["anchors"]
            boundary = level["boundary"]
            if not isinstance(anchors, list) or len(anchors) not in (1, 2):
                if is_selected:
                    return None
                continue
            if not all(type(pair[0]) is int and pair[0] in bar_times
                       and type(pair[1]) in (float, int)
                       and math.isfinite(pair[1]) and pair[1] > 0
                       for pair in anchors):
                if is_selected:
                    return None
                continue
            slope = float(boundary["slope_per_ms"])
            if not math.isfinite(slope) or (len(anchors) == 1 and slope != 0):
                if is_selected:
                    return None
                continue
            # Confirm that serialized source anchors are on the same frozen
            # straight boundary. Do not silently substitute a guessed price.
            base_time = int(boundary["anchor_time_ms"])
            base_price = float(boundary["anchor_price"])
            for t, price in anchors:
                expected = base_price + slope * (t - base_time)
                if not math.isclose(expected, price, rel_tol=1e-8, abs_tol=1e-10):
                    if is_selected:
                        return None
                    break
            else:
                result.append({
                    "boundary_id": name,
                    "kind": "horizontal-ray" if len(anchors) == 1 else "ray",
                    "anchors": [
                        {"bar_open_time_ms": t, "price": price}
                        for t, price in anchors
                    ],
                })
        if selected_count != 1 or not any(
            item["boundary_id"] == frozen["level_id"] for item in result
        ):
            return None
        snapshot = {
            "schema_version": 1,
            "signal_id": str(signal_id),
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "boundaries": result,
        }
        validate_snapshot(
            snapshot, candidate_id=str(signal_id),
            symbol=symbol, timeframe=timeframe,
        )
        return snapshot
    except (ValueError, KeyError, TypeError, OverflowError, IndexError):
        return None
