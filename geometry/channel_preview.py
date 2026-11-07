"""Four-confirmed-pivot channel projection for offline observation (#490).

This is NOT a new Scanner detector, geometry winner, trading trigger, or
permission to submit a Robot/PAPER order. Every preview is an unconfirmed
snapshot whose complete pivot identity must be compared by any future caller
before carrying it forward; a new pivot set is a NEW observation, never a
silent reanchoring of the original candidate.

Reuse HORN's existing 3/3 pivot confirmation, two-point line construction,
positive-width check, and locality bound. Parallel means mathematically equal
slopes, NOT an invented owner-approved 'roughly parallel' market tolerance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pivots import find_pivots

from .broadening import HIGH, LOW, _line, _positive_width, _sequence, _value
from .engine import GEOMETRY_MAX_STRUCTURE_SPAN_RATIO


@dataclass(frozen=True)
class ChannelPreview:
    as_of_index: int
    start_index: int
    anchor_identity: tuple[tuple[int, str, float], ...]
    upper_line: dict
    lower_line: dict
    geometry_relation: str
    slope_upper: float
    slope_lower: float
    stage: str = "PROVISIONAL_OBSERVATION"

    def project(self, index: int) -> tuple[float, float]:
        """Project (upper, lower) only; future price action is not predicted."""
        return _value(self.upper_line, index), _value(self.lower_line, index)


def observe_four_pivot_channel(candles, as_of_index: int | None = None) -> ChannelPreview | None:
    """Observe the last four adjacent 3/3-confirmed alternating highs/lows.

    Four confirmed pivots (two per side) permit a *provisional* projection.
    Confirmation is temporal: pivots are calculated ONLY from the closed
    caller-supplied prefix ending at as_of_index. No additional 5th pivot,
    future bar, trade direction, trend context, or undocumented market-specific
    threshold is needed. Consumers MUST keep anchor_identity for future
    comparison and resolve any new candidate with an explicit policy.
    """
    if candles is None or not hasattr(candles, "iloc"):
        return None
    try:
        total = len(candles)
    except (TypeError, ValueError):
        return None
    if not total:
        return None
    if as_of_index is None:
        as_of_index = total - 1
    if type(as_of_index) is not int or not 0 <= as_of_index < total:
        return None

    prefix = candles.iloc[:as_of_index + 1].reset_index(drop=True)
    if any(col not in prefix.columns for col in ("open", "high", "low", "close")):
        return None
    # Invalid/unclosed historical data is not repaired or guessed. The caller
    # owns the decision-time closed-bar cutoff, as for the HORN detector.
    for row in prefix[["open", "high", "low", "close"]].itertuples(index=False, name=None):
        try:
            opening, high, low, close = (float(value) for value in row)
        except (TypeError, ValueError, OverflowError):
            return None
        if (not all(math.isfinite(x) for x in (opening, high, low, close))
                or low <= 0 or low > min(opening, close)
                or high < max(opening, close)):
            return None

    try:
        # The shared pivot finder normally filters repeated same-side prices
        # by 0.3%. That intentionally removes flat ranges from active detectors.
        # For this OBSERVATION-ONLY channel preview retain true 3/3 pivots
        # even at exactly equal prices, so horizontal boxes can be described.
        # Do not change the production pivot-finder default or active callers.
        highs, lows = find_pivots(prefix.copy(), min_change=0)
        sequence = _sequence(highs, lows)
    except (TypeError, KeyError, ValueError, IndexError, ArithmeticError, OverflowError):
        return None
    if len(sequence) < 4:
        return None

    anchors = tuple(sequence[-4:])
    if any(not math.isfinite(price) or price <= 0 for _, _, price in anchors):
        return None
    if (any(a[0] >= b[0] or a[1] == b[1] for a, b in zip(anchors, anchors[1:]))
            or len([a for a in anchors if a[1] == HIGH]) != 2
            or len([a for a in anchors if a[1] == LOW]) != 2):
        return None
    if as_of_index - anchors[-1][0] < 3:
        return None  # Never use a pivot before its three right bars have closed.
    if as_of_index - anchors[0][0] > round((as_of_index + 1) * GEOMETRY_MAX_STRUCTURE_SPAN_RATIO):
        return None

    high_points = [point for point in anchors if point[1] == HIGH]
    low_points = [point for point in anchors if point[1] == LOW]
    upper = _line(high_points[0], high_points[1])
    lower = _line(low_points[0], low_points[1])
    if not _positive_width(upper, lower, anchors[0][0], as_of_index):
        return None

    spread_slope = upper["slope"] - lower["slope"]
    if spread_slope > 0:
        relation = "DIVERGING"
    elif spread_slope < 0:
        relation = "CONVERGING"
    elif upper["slope"] == 0:
        relation = "PARALLEL_HORIZONTAL"
    else:
        relation = "PARALLEL_TILTED"

    return ChannelPreview(
        as_of_index=as_of_index,
        start_index=anchors[0][0],
        anchor_identity=anchors,
        upper_line=upper,
        lower_line=lower,
        geometry_relation=relation,
        slope_upper=upper["slope"],
        slope_lower=lower["slope"],
    )
