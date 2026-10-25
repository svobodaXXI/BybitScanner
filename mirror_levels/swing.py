"""
mirror_levels.swing

M2 of #613: horizontal support/resistance zones from confirmed pivots, with no
recognised chart pattern required.

Reuses the Scanner's own pivot detector (``pivots.find_pivots``, 3/3 bars, the
same settings ``geometry.triangle_boundaries`` uses) and the causal ATR of
``retest_calibration``. A pivot at index ``k`` is only *known* at the close of
candle ``k + PIVOT_RIGHT``; a zone is confirmed at the confirmation time of its
``min_touches``-th pivot and never changes afterwards (anchors, price and id are
frozen), so a level found on a candle prefix is identical to the one found on
the full history (prefix parity, the Freqtrade look-ahead method).

A zone is anchored at its oldest pivot price; a later pivot of the same type
joins it while ``|price - anchor| <= tolerance_atr * ATR`` at that pivot's
confirmation. Highs give resistance (side ``upper``), lows support (``lower``).
"""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from geometry.triangle_boundaries import PIVOT_LEFT, PIVOT_RIGHT
from mirror_levels.levels import (
    SIDE_LOWER, SIDE_UPPER, SOURCE_SWING_ZONE, MirrorLevel, horizontal_level,
)
from pivots import find_pivots
from retest_calibration import causal_atr_series


DEFAULT_ATR_PERIOD = 14


def confirmed_pivots(candles: Sequence[Mapping], *, left: int = PIVOT_LEFT,
                     right: int = PIVOT_RIGHT) -> tuple[list[dict], list[dict]]:
    """Raw pivots of closed candles with ``pivot_at_ms`` and ``confirmed_at_ms``."""

    if len(candles) < left + right + 1:
        return [], []
    frame = pd.DataFrame({"high": [float(c["high"]) for c in candles],
                          "low": [float(c["low"]) for c in candles]})
    highs, lows = find_pivots(frame, left=left, right=right, min_change=0)
    out = []
    for points in (highs, lows):
        out.append([{
            "index": int(p["index"]), "price": float(p["price"]),
            "pivot_at_ms": int(candles[int(p["index"])]["open_time_ms"]),
            "confirmed_index": int(p["index"]) + right,
            "confirmed_at_ms": int(candles[int(p["index"]) + right]["close_time_ms"]),
        } for p in points])
    return out[0], out[1]


def swing_levels(candles: Sequence[Mapping], *, symbol: str, timeframe: str,
                 min_touches: int = 2, tolerance_atr: float = 0.25,
                 atr_period: int = DEFAULT_ATR_PERIOD) -> tuple[MirrorLevel, ...]:
    """Confirmed swing zones from ``candles`` (all closed, chronological)."""

    if min_touches < 1 or tolerance_atr < 0:
        raise ValueError("min_touches must be >= 1 and tolerance_atr >= 0")
    highs, lows = confirmed_pivots(candles)
    atr = causal_atr_series(candles, atr_period) if candles else []
    levels = []
    for side, points in ((SIDE_UPPER, highs), (SIDE_LOWER, lows)):
        zones: list[dict] = []
        for pivot in sorted(points, key=lambda p: p["confirmed_index"]):
            atr_value = atr[pivot["confirmed_index"]]
            if atr_value is None:
                continue
            tolerance = tolerance_atr * atr_value
            home = next((zone for zone in zones
                         if len(zone["pivots"]) < min_touches
                         and abs(pivot["price"] - zone["pivots"][0]["price"]) <= tolerance), None)
            if home is None:
                zones.append({"pivots": [pivot]})
            else:
                home["pivots"].append(pivot)
        for zone in zones:
            members = zone["pivots"]
            if len(members) < min_touches:
                continue
            anchor = members[0]
            levels.append(horizontal_level(
                symbol=symbol, timeframe=timeframe, source=SOURCE_SWING_ZONE, pattern=None,
                side=side, price=anchor["price"], anchor_time_ms=anchor["pivot_at_ms"],
                confirmed_at_ms=members[-1]["confirmed_at_ms"], touches=len(members),
                provenance={"pivots": [[m["pivot_at_ms"], m["price"]] for m in members],
                            "tolerance_atr": tolerance_atr, "atr_period": atr_period},
            ))
    return tuple(sorted(levels, key=lambda x: (x.confirmed_at_ms, x.level_id)))
