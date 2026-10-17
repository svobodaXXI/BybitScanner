"""
geometry.broadening

HORN-2: autonomous offline detector for a forming symmetric Broadening
Formation («рупор»), per DOCUMENTS/SCANNER_BROADENING_FORMATION_HORN_1.md
(HORN-1B owner decisions).

    rising upper boundary through >= 2 higher HIGHs,
    falling lower boundary through >= 2 lower LOWs,
    adjacent alternating confirmed pivots, every wave longer than the previous.

Four confirmed alternating pivots (2 HIGH, 2 LOW) are a valid PRELIMINARY
formation with both boundaries projected; every further expanding pivot raises
it to MATURE. A 5th pivot is never required.

START comes from the local structure of confirmed waves: the expanding run is
built backward from the latest confirmed pivot and stops at the first pivot that
breaks alternation, HH/LL or wave growth, or that would exceed the existing
locality bound (engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO). It is never derived
from the backward intersection of the boundaries. When a later confirmed pivot
breaks the expansion, the run from that pivot is too short and the formation is
invalidated (None); its anchors are never silently replaced.

Reused, no new numeric threshold:
- pivots.find_pivots (confirmed 3/3 pivots, min_change filter);
- two-point boundaries through the first and last same-side anchor;
- hull property (no confirmed same-side pivot beyond a boundary);
- envelope_metrics.evaluate_formation_body_fit with
  engine.GEOMETRY_MAX_BODY_BREACH_RUN (isolated wicks tolerated);
- engine.GEOMETRY_MAX_STRUCTURE_SPAN_RATIO locality;
- confirmation.calculate_atr and triangle_boundaries.local_alternation_pivots
  as diagnostics only.

Not responsible for: direction (no LONG/SHORT, reversal or continuation),
Wedge/Triangle interaction (never consulted, never suppressed), Scanner,
Telegram, Robot, orders or any trading decision.

Only candles 0..as_of_index are read, so later bars cannot change a verdict.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from confirmation import calculate_atr
from pivots import find_pivots

from .engine import (
    GEOMETRY_MAX_BODY_BREACH_RUN,
    GEOMETRY_MAX_STRUCTURE_SPAN_RATIO,
)
from .envelope_metrics import evaluate_formation_body_fit
from .triangle_boundaries import local_alternation_pivots

STAGE_PRELIMINARY = "PRELIMINARY"
STAGE_MATURE = "MATURE"

HIGH = "H"
LOW = "L"

# Owner definition: two HIGH and two LOW anchors (HORN-1B decision 1).
MIN_ANCHORS = 4


@dataclass(frozen=True)
class BroadeningFormation:
    stage: str
    start_index: int
    as_of_index: int
    anchors: tuple  # ((index, "H"|"L", price), ...) chronological
    upper_line: dict
    lower_line: dict
    waves: int
    diagnostics: dict = field(default_factory=dict)

    def project(self, index):
        """Projected (upper, lower) boundary prices at `index` (forward or back)."""
        return _value(self.upper_line, index), _value(self.lower_line, index)


def _value(line, index):
    return line["slope"] * index + line["intercept"]


def _line(first, last):
    slope = (last[2] - first[2]) / (last[0] - first[0])
    return {
        "slope": slope,
        "intercept": first[2] - slope * first[0],
        "anchor_index": first[0],
        "anchor_price": first[2],
        "second_index": last[0],
        "second_price": last[2],
    }


def _rounding_bound(*prices):
    """Floating-point rounding bound for a boundary value built from `prices`.

    A projected boundary price comes from a handful of float operations on the
    anchor prices, so its absolute rounding error is a few ulps of the largest
    magnitude involved. This is a numeric-precision bound, not a market
    threshold: it only stops a zero width from passing as positive.
    """
    return 8 * math.ulp(max(abs(price) for price in prices))


def _positive_width(upper, lower, first_index, last_index):
    """upper(t) > lower(t) for every t in [first_index, last_index].

    Both boundaries are straight lines, so their difference is linear and its
    minimum on a closed interval is at one of the ends: checking both ends
    proves the whole interval. Touching (zero width within rounding) and
    crossed boundaries are rejected.
    """
    for index in (first_index, last_index):
        upper_value, lower_value = _value(upper, index), _value(lower, index)
        bound = _rounding_bound(
            upper_value, lower_value,
            upper["anchor_price"], upper["second_price"],
            lower["anchor_price"], lower["second_price"],
        )
        if not upper_value - lower_value > bound:
            return False
    return True


def _sequence(highs, lows):
    return sorted(
        [(int(p["index"]), HIGH, float(p["price"])) for p in highs]
        + [(int(p["index"]), LOW, float(p["price"])) for p in lows]
    )


def _beyond(pivot, other):
    """pivot is a strictly higher HIGH / strictly lower LOW than other (same side)."""
    return pivot[2] > other[2] if pivot[1] == HIGH else pivot[2] < other[2]


def _expanding_run(sequence, as_of_index):
    """Adjacent expanding run ending at the latest confirmed pivot, built backward."""
    if not sequence:
        return []

    max_span = round((as_of_index + 1) * GEOMETRY_MAX_STRUCTURE_SPAN_RATIO)
    run = [sequence[-1]]

    for pivot in reversed(sequence[:-1]):
        first = run[0]
        if pivot[1] == first[1] or pivot[0] == first[0]:
            break  # split wave: two same-side pivots are adjacent
        if as_of_index - pivot[0] > max_span:
            break  # locality bound for START
        if len(run) >= 2:
            second = run[1]
            # pivot -> first must be shorter than first -> second (waves grow),
            # and the later same-side pivot (second) must lie beyond pivot.
            if not abs(first[2] - pivot[2]) < abs(second[2] - first[2]):
                break
            if not _beyond(second, pivot):
                break
        run.insert(0, pivot)

    return run


def _wick_body(candles, index, side):
    row = candles.iloc[index]
    body_top = max(float(row["open"]), float(row["close"]))
    body_bottom = min(float(row["open"]), float(row["close"]))
    wick = float(row["high"]) - body_top if side == HIGH else body_bottom - float(row["low"])
    body = body_top - body_bottom
    return None if body == 0 else wick / body


def detect_broadening(candles, as_of_index=None):
    """Return the forming broadening at `as_of_index` (default: last bar) or None."""

    if candles is None or len(candles) == 0:
        return None

    if as_of_index is None:
        as_of_index = len(candles) - 1

    if not 0 <= as_of_index < len(candles):
        return None

    prefix = candles.iloc[: as_of_index + 1].reset_index(drop=True)
    highs, lows = find_pivots(prefix.copy())
    run = _expanding_run(_sequence(highs, lows), as_of_index)

    if len(run) < MIN_ANCHORS:
        return None

    run_highs = [p for p in run if p[1] == HIGH]
    run_lows = [p for p in run if p[1] == LOW]
    upper = _line(run_highs[0], run_highs[-1])
    lower = _line(run_lows[0], run_lows[-1])

    if not (upper["slope"] > 0 and lower["slope"] < 0):
        return None

    start_index = run[0][0]
    width_start = _value(upper, start_index) - _value(lower, start_index)
    width_end = _value(upper, as_of_index) - _value(lower, as_of_index)

    if not (width_end > width_start):
        return None

    # The channel must be open over the whole formation: from START through
    # the last anchor and on to the decision bar the upper boundary stays
    # strictly above the lower one. Without it the two-point lines can cross
    # between P1 and P2, so at START the upper line is below the lower one
    # (UNIUSDT 5m, 2026-10-16) while the width still "grows".
    last_index = max(run[-1][0], as_of_index)
    if not _positive_width(upper, lower, start_index, last_index):
        return None

    # Hull: no confirmed same-side pivot from START to the decision bar lies
    # beyond its boundary.
    for points, line, side in ((highs, upper, HIGH), (lows, lower, LOW)):
        for point in points:
            index = int(point["index"])
            if index < start_index:
                continue
            boundary = _value(line, index)
            price = float(point["price"])
            if (side == HIGH and price > boundary) or (side == LOW and price < boundary):
                return None

    body_fit = evaluate_formation_body_fit(upper, lower, prefix, as_of_index)
    if body_fit is not None and not all(
        body_fit[side]["max_consecutive_breaches"] < GEOMETRY_MAX_BODY_BREACH_RUN
        for side in ("upper", "lower")
    ):
        return None

    atr = calculate_atr(prefix)
    atr_start, atr_end = (float(atr.iloc[i]) for i in (start_index, as_of_index))
    local_highs, local_lows = local_alternation_pivots(prefix, as_of_index)
    global_indices = {p[0] for p in _sequence(highs, lows)}
    close = float(prefix["close"].iloc[as_of_index])
    upper_now, lower_now = _value(upper, as_of_index), _value(lower, as_of_index)

    diagnostics = {
        "width_start": width_start,
        "width_end": width_end,
        "width_ratio": width_end / width_start if width_start > 0 else None,
        "width_atr_start": width_start / atr_start if atr_start == atr_start and atr_start > 0 else None,
        "width_atr_end": width_end / atr_end if atr_end == atr_end and atr_end > 0 else None,
        "anchor_wick_body": [(p[0], _wick_body(prefix, p[0], p[1])) for p in run],
        "local_only_pivots": sorted(
            int(p["index"])
            for p in local_highs + local_lows
            if int(p["index"]) >= start_index and int(p["index"]) not in global_indices
        ),
        "close_outside_boundary": not (lower_now <= close <= upper_now),
        "body_max_consecutive_breaches": (
            None if body_fit is None else {
                side: body_fit[side]["max_consecutive_breaches"] for side in ("upper", "lower")
            }
        ),
    }

    return BroadeningFormation(
        stage=STAGE_MATURE if len(run) > MIN_ANCHORS else STAGE_PRELIMINARY,
        start_index=start_index,
        as_of_index=as_of_index,
        anchors=tuple(run),
        upper_line=upper,
        lower_line=lower,
        waves=len(run) - 1,
        diagnostics=diagnostics,
    )
