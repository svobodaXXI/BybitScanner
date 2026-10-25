"""
mirror_levels.breakout

M3 of #613: evidence about how one closed candle crossed a level.

The tradeable naked breakout stays exactly ``geometry.naked_retest``'s rule
(real body fully crosses the boundary at its own open/close times). This module
only *describes* every crossing so weak and false breaks are visible and
countable, never promoted:

- ``FULL_BODY``  -- ``naked_breakout_direction`` is not None (the MIRROR rule);
- ``CLOSE_ONLY`` -- closed beyond the level without a body crossing: the candle
                    opened exactly on the level, or (with ``previous_close``)
                    gapped over it from the old side;
- ``WICK_ONLY``  -- only a shadow crossed, the close stayed on the old side.

Size facts (body/ATR, close distance in ATR, wick shares) are recorded for later
Gold calibration; no threshold is applied here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from geometry.naked_retest import BREAKOUT_DOWN, BREAKOUT_UP, Boundary, naked_breakout_direction


KIND_FULL_BODY = "FULL_BODY"
KIND_CLOSE_ONLY = "CLOSE_ONLY"
KIND_WICK_ONLY = "WICK_ONLY"


@dataclass(frozen=True)
class BreakoutEvidence:
    kind: str
    direction: str
    open_time_ms: int
    close_time_ms: int
    level_at_open: float
    level_at_close: float
    body: float
    range: float
    body_atr: float | None
    close_beyond_atr: float | None
    upper_wick_share: float
    lower_wick_share: float

    @property
    def is_naked(self) -> bool:
        return self.kind == KIND_FULL_BODY


def _kind(o: float, h: float, l: float, c: float, at_open: float, at_close: float,
          previous_close: float | None) -> tuple[str, str] | None:
    if o < at_open:
        if c > at_close:
            return KIND_FULL_BODY, BREAKOUT_UP
        if h > max(at_open, at_close):
            return KIND_WICK_ONLY, BREAKOUT_UP
        return None
    if o > at_open:
        if c < at_close:
            return KIND_FULL_BODY, BREAKOUT_DOWN
        if l < min(at_open, at_close):
            return KIND_WICK_ONLY, BREAKOUT_DOWN
        if previous_close is not None and previous_close < at_open and c > at_close:
            return KIND_CLOSE_ONLY, BREAKOUT_UP  # gapped over the level from below
        return None
    if c > at_close:
        return KIND_CLOSE_ONLY, BREAKOUT_UP
    if c < at_close:
        return KIND_CLOSE_ONLY, BREAKOUT_DOWN
    return None


def classify_crossing(boundary: Boundary, candle: Mapping, *, atr: float | None = None,
                      previous_close: float | None = None) -> BreakoutEvidence | None:
    """Describe how closed ``candle`` crossed ``boundary``; None when it did not."""

    o, h, l, c = (float(candle[k]) for k in ("open", "high", "low", "close"))
    t_open, t_close = int(candle["open_time_ms"]), int(candle["close_time_ms"])
    at_open, at_close = boundary.price_at(t_open), boundary.price_at(t_close)
    if (previous_close is not None and o < at_open and previous_close > at_open
            and c < at_close):
        found = (KIND_CLOSE_ONLY, BREAKOUT_DOWN)  # gapped under the level from above
    else:
        found = _kind(o, h, l, c, at_open, at_close, previous_close)
    if found is None:
        return None
    kind, direction = found
    if kind == KIND_FULL_BODY:
        # The tradeable class is decided by the existing MIRROR rule, never re-derived.
        direction = naked_breakout_direction(boundary, dict(candle, closed=True))
        if direction is None:
            return None
    span, body = h - l, abs(c - o)
    usable_atr = atr if atr is not None and atr > 0 else None
    beyond = (c - at_close) if direction == BREAKOUT_UP else (at_close - c)
    return BreakoutEvidence(
        kind=kind, direction=direction, open_time_ms=t_open, close_time_ms=t_close,
        level_at_open=at_open, level_at_close=at_close, body=body, range=span,
        body_atr=None if usable_atr is None else body / usable_atr,
        close_beyond_atr=None if usable_atr is None else beyond / usable_atr,
        upper_wick_share=0.0 if span == 0 else (h - max(o, c)) / span,
        lower_wick_share=0.0 if span == 0 else (min(o, c) - l) / span,
    )
