"""Offline Diamond Formation candidate: one expanding-then-contracting pivot episode.

Owner issue #500. Observation only: NOT a trading pattern, chart/Scanner signal,
Robot candidate, entry or exit rule. No direction is inferred. Six alternating
confirmed pivots (three highs, three lows) are the minimum to establish both
sides of both regimes; real Gold/owner calibration remains pending.

Uses the same causal 3/3 confirmed pivots, locality and numeric line
primitives as the existing HORN detector, without changing HORN itself.
The caller owns the CLOSED as-of candle cutoff; bars after it are ignored.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pivots import find_pivots
from .broadening import HIGH, LOW, _line, _positive_width, _sequence
from .engine import (
    GEOMETRY_MAX_BODY_BREACH_RUN,
    GEOMETRY_MAX_STRUCTURE_SPAN_RATIO,
)
from .envelope_metrics import evaluate_formation_body_fit


@dataclass(frozen=True)
class DiamondCandidate:
    start_index: int
    as_of_index: int
    anchors: tuple[tuple[int, str, float], ...]
    expansion_upper: dict
    expansion_lower: dict
    contraction_upper: dict
    contraction_lower: dict
    turn_indices: tuple[int, int]
    width_first: float
    width_widest_anchor_pair: float
    width_last: float
    stage: str = "OFFLINE_CANDIDATE"


def detect_diamond_candidate(candles, as_of_index=None) -> DiamondCandidate | None:
    """Return provisional geometry, or None if a single confirmed episode is unproved.

    The six *latest adjacent* pivots must alternate, first widen in both
    extrema and subsequent wave lengths, then contract in both extrema and
    wave lengths. Two crossed/zero-width regimes cannot form a diamond.
    This deliberately does not claim full chart fit or real Gold acceptance.
    """
    if candles is None or len(candles) == 0:
        return None
    if as_of_index is None:
        as_of_index = len(candles) - 1
    if type(as_of_index) is not int or not 0 <= as_of_index < len(candles):
        return None
    prefix = candles.iloc[:as_of_index + 1].reset_index(drop=True)
    try:
        highs, lows = find_pivots(prefix.copy())
        pivots = _sequence(highs, lows)
    except (TypeError, KeyError, ValueError, IndexError, ArithmeticError):
        return None
    if len(pivots) < 6:
        return None
    run = pivots[-6:]
    if any(left[1] == right[1] or left[0] >= right[0]
           for left, right in zip(run, run[1:])):
        return None
    if any(not math.isfinite(price) or price <= 0 for _, _, price in run):
        return None
    if as_of_index - run[0][0] > round((as_of_index + 1) * GEOMETRY_MAX_STRUCTURE_SPAN_RATIO):
        return None

    highs_run = [point for point in run if point[1] == HIGH]
    lows_run = [point for point in run if point[1] == LOW]
    if len(highs_run) != 3 or len(lows_run) != 3:
        return None
    h1, h2, h3 = highs_run
    l1, l2, l3 = lows_run
    if not (h2[2] > h1[2] and h2[2] > h3[2]
            and l2[2] < l1[2] and l2[2] < l3[2]):
        return None

    waves = [abs(b[2] - a[2]) for a, b in zip(run, run[1:])]
    if not (waves[0] < waves[1] < waves[2] > waves[3] > waves[4]):
        return None
    width_first, width_peak, width_last = (
        h1[2] - l1[2], h2[2] - l2[2], h3[2] - l3[2]
    )
    if not (0 < width_first < width_peak and 0 < width_last < width_peak):
        return None

    expanding_upper, expanding_lower = _line(h1, h2), _line(l1, l2)
    contracting_upper, contracting_lower = _line(h2, h3), _line(l2, l3)
    turn_start, turn_end = min(h2[0], l2[0]), max(h2[0], l2[0])
    if not (
        expanding_upper["slope"] > 0
        and expanding_lower["slope"] < 0
        and contracting_upper["slope"] < 0
        and contracting_lower["slope"] > 0
        and _positive_width(expanding_upper, expanding_lower, run[0][0], turn_end)
        and _positive_width(contracting_upper, contracting_lower, turn_start, run[-1][0])
    ):
        return None

    # The six pivots prove only the extremal skeleton. A false Diamond can
    # still have malformed source bars or a sustained run of real candle bodies
    # outside either regime. Match HORN's existing body-fit tolerance and
    # max-consecutive-breach rule, separately for expansion and contraction.
    # Never use the contraction bars to score expansion or future data at as-of.
    for index in range(run[0][0], as_of_index + 1):
        row = prefix.iloc[index]
        try:
            opening, high, low, close = (float(row[name])
                                        for name in ("open", "high", "low", "close"))
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
        if (not all(math.isfinite(x) and x > 0 for x in (opening, high, low, close))
                or high <= low or low > min(opening, close)
                or high < max(opening, close)):
            return None

    for upper, lower, end in (
        (expanding_upper, expanding_lower, turn_end),
        (contracting_upper, contracting_lower, run[-1][0]),
    ):
        fit = evaluate_formation_body_fit(upper, lower, prefix, end)
        if fit is None or any(
            fit[side]["max_consecutive_breaches"] >= GEOMETRY_MAX_BODY_BREACH_RUN
            for side in ("upper", "lower")
        ):
            return None

    return DiamondCandidate(
        start_index=run[0][0],
        as_of_index=as_of_index,
        anchors=tuple(run),
        expansion_upper=expanding_upper,
        expansion_lower=expanding_lower,
        contraction_upper=contracting_upper,
        contraction_lower=contracting_lower,
        turn_indices=(h2[0], l2[0]),
        width_first=width_first,
        width_widest_anchor_pair=width_peak,
        width_last=width_last,
    )
