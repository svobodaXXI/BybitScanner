"""#415: strictly offline, closed-candle evidence of a naked breakout and return.

This is NOT Scanner delivery, a strategy, a trade plan, a Robot candidate, or
permission to trade. Owner has not specified numerical excursion thresholds:
the offline caller MUST supply min_excursion_fraction and min_impulse_bars.
The source pattern boundary is frozen before breakout, never retrofitted.
This deliberately conservative first slice rejects ambiguous/choppy impulses.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


@dataclass(frozen=True)
class NakedBreakoutObservation:
    source_identity: tuple[str, int, int, float, float]
    breakout_side: str
    breakout_index: int
    impulse_extreme_index: int
    reversal_close_index: int
    reversal_close_time_ms: int
    excursion_fraction: float
    boundary_at_breakout: float
    boundary_at_reversal_close: float
    observed_return_side: str
    strategy_confirmed: bool = False
    stage: str = "OFFLINE_OBSERVATION"


def _closed_prefix(candles: Sequence[Mapping], as_of_index: int):
    """Reject holes, provisional bars, invalid OHLC and unknown time ordering."""
    if not isinstance(candles, (list, tuple)) or not 0 <= as_of_index < len(candles):
        return None
    result = []
    width = None
    previous_end = None
    for row in candles[:as_of_index + 1]:
        if not isinstance(row, Mapping) or row.get("closed") is not True:
            return None
        try:
            start, end = row["open_time_ms"], row["close_time_ms"]
            if type(start) is not int or type(end) is not int or start < 0 or end <= start:
                return None
            if previous_end is not None and start != previous_end:
                return None
            if width is not None and end - start != width:
                return None
            o, h, lo, c = (float(row[key]) for key in ("open", "high", "low", "close"))
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
        if (not all(math.isfinite(x) and x > 0 for x in (o, h, lo, c))
                or lo >= h or lo > min(o, c) or h < max(o, c)):
            return None
        result.append((o, h, lo, c, end))
        previous_end, width = end, end - start
    return tuple(result)


def observe_naked_breakout_return(
    candles: Sequence[Mapping], *,
    boundary: Mapping, breakout_index: int, as_of_index: int,
    min_excursion_fraction: float, min_impulse_bars: int,
) -> NakedBreakoutObservation | None:
    """Observe a body breakout, clean impulse and following body reversal.

    The breakout body must cross an authoritative, previously frozen moving
    boundary; the preceding close must have been on the opposite side.
    Every impulse bar extends both the close and wick extreme in the breakout
    direction, with no body retest/consolidation. The very NEXT closed candle
    must close beyond the preceding impulse candle's real body in the opposite
    direction. That is candle *evidence*, not strategy entry confirmation.

    The projected boundary at reversal-close is a moving REFERENCE, NOT a
    predicted target/exit time or an order price. No lookahead after as_of.
    """
    if (type(breakout_index) is not int or type(as_of_index) is not int
            or type(min_impulse_bars) is not int or min_impulse_bars < 2
            or breakout_index < 1 or as_of_index < breakout_index + min_impulse_bars
            or type(min_excursion_fraction) not in (int, float)
            or not isinstance(boundary, Mapping)):
        return None
    try:
        minimum = float(min_excursion_fraction)
        source_id = boundary["source_id"]
        frozen = boundary["frozen_at_index"]
        anchor = boundary["anchor_index"]
        anchor_price = float(boundary["anchor_price"])
        slope = float(boundary["slope_per_bar"])
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    if (not math.isfinite(minimum) or minimum <= 0
            or not isinstance(source_id, str) or not source_id.strip()
            or type(frozen) is not int or type(anchor) is not int
            or frozen < 0 or anchor < 0 or anchor > frozen
            or frozen >= breakout_index
            or not all(math.isfinite(x) for x in (anchor_price, slope))
            or anchor_price <= 0):
        return None
    prices = _closed_prefix(candles, as_of_index)
    if prices is None:
        return None

    def level(index):
        return anchor_price + slope * (index - anchor)

    if any(not math.isfinite(level(i)) or level(i) <= 0
           for i in range(breakout_index - 1, as_of_index + 1)):
        return None

    prior, first = prices[breakout_index - 1], prices[breakout_index]
    at_prior, at_break = level(breakout_index - 1), level(breakout_index)
    # The previous close must be strictly on the unbroken side.
    # A close touching the exact boundary is not a proved body breakout.
    downside = (prior[3] > at_prior and first[0] >= at_break
                and first[3] < at_break)
    upside = (prior[3] < at_prior and first[0] <= at_break
              and first[3] > at_break)
    if not (downside or upside):
        return None

    impulse_end = as_of_index - 1
    for i in range(breakout_index + 1, impulse_end + 1):
        before, current = prices[i - 1], prices[i]
        # Any close back through the moving source line invalidates the naked
        # impulse. Strict successive lows/highs and closes exclude chop.
        if downside:
            if not (current[2] < before[2] and current[3] < before[3]
                    and current[0] < level(i) and current[3] < level(i)):
                return None
        elif not (current[1] > before[1] and current[3] > before[3]
                  and current[0] > level(i) and current[3] > level(i)):
            return None

    impulse = prices[breakout_index:impulse_end + 1]
    extreme_price = min(row[2] for row in impulse) if downside else max(row[1] for row in impulse)
    excursion = (at_break - extreme_price) / at_break if downside else (extreme_price - at_break) / at_break
    if not math.isfinite(excursion) or excursion < minimum:
        return None

    last, reversal = prices[impulse_end], prices[as_of_index]
    if downside:
        reversed_body = reversal[3] > reversal[0] and reversal[3] > max(last[0], last[3])
    else:
        reversed_body = reversal[3] < reversal[0] and reversal[3] < min(last[0], last[3])
    if not reversed_body:
        return None

    return NakedBreakoutObservation(
        source_identity=(source_id, frozen, anchor, anchor_price, slope),
        breakout_side="DOWN" if downside else "UP",
        breakout_index=breakout_index,
        impulse_extreme_index=impulse_end,
        reversal_close_index=as_of_index,
        reversal_close_time_ms=reversal[4],
        excursion_fraction=excursion,
        boundary_at_breakout=at_break,
        boundary_at_reversal_close=level(as_of_index),
        observed_return_side="LONG" if downside else "SHORT",
    )
