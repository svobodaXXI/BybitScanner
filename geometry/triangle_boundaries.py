"""
geometry.triangle_boundaries

RSR-ANCHORS-4: extra boundary lines admitted ONLY for Triangle Compression.

Two sources, both added after the regular candidate filter and both marked
`triangle_only`; the engine drops any pair containing one of them unless the
pair's anchor-sequence family is "triangle". All other gates (validation,
locality, boundary validity, anchor sequence, freshness) stay unchanged.

T - two-point hull edge:
    a line through two confirmed same-side pivots (span >= DEFAULT_MIN_LINE_SPAN,
    at least the second anchor as confirmation) that no confirmed same-side pivot
    after the first anchor (up to current_index) lies beyond. Recovers a triangle
    edge the regular generator misses because only one pivot lies on it.

Q - local alternation-aware pivots:
    a raw 3/3 pivot that the global min_change filter drops is still a boundary
    point when a raw opposite pivot between it and the last kept same-side pivot
    moved price by >= min_change (a new swing, not noise). The list feeds only
    the extra Triangle lines below; the global pivot lists passed to evaluation
    are unchanged, so no other pattern or metric sees it.

Owner case: RSRUSDT 5m G-TRI-1 (H192 dropped by the global filter, L148->L178
with a single confirmation); see tests/test_geometry_triangle_rsr_anchors.py.
"""

from pivots import find_pivots

from .candidate import (
    DEFAULT_MIN_LINE_SPAN,
    build_candidate_lines
)
from .trendline import calculate_price


# Same pivot definition and noise filter the Scanner passes to Geometry
# (pivots.find_pivots defaults); NOT a new threshold.
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
PIVOT_MIN_CHANGE = 0.003


def is_triangle_only(candidate):
    return isinstance(candidate, dict) and bool(candidate.get("triangle_only"))


def _line_key(candidate):
    return (
        candidate["anchor_index"],
        candidate["second_index"]
    )


def _triangle_side_slope(candidate, side):
    # A Triangle needs a falling upper and a rising lower boundary; other
    # slopes can never form a triangle pair, so they are not generated.
    slope = candidate["line"].get("slope", 0)
    return slope < 0 if side == "high" else slope > 0


def _is_hull_edge(candidate, points, side, current_index):
    line = candidate["line"]
    second_index = candidate["second_index"]

    for point in points:
        index = point["index"]
        if (
            index <= candidate["anchor_index"]
            or index == second_index
            or index > current_index
        ):
            continue
        predicted = calculate_price(line, index)
        if predicted is None:
            return False
        price = float(point["price"])
        if side == "high" and price > predicted:
            return False
        if side == "low" and price < predicted:
            return False

    return True


def _two_point_lines(points, side, current_index):
    return [
        candidate
        for candidate in build_candidate_lines(points, min_confirmations=1)
        if _is_hull_edge(candidate, points, side, current_index)
    ]


def _alternation_filter(points, opposite_raw, min_change=PIVOT_MIN_CHANGE):
    if not points:
        return []

    kept = [points[0]]

    for point in points[1:]:
        last = kept[-1]
        last_price = float(last["price"])
        if last_price == 0:
            continue
        if abs(float(point["price"]) - last_price) / last_price >= min_change:
            kept.append(point)
            continue
        new_swing = any(
            last["index"] < opposite["index"] < point["index"]
            and abs(float(opposite["price"]) - last_price) / last_price >= min_change
            for opposite in opposite_raw
        )
        if new_swing:
            kept.append(point)

    return kept


def local_alternation_pivots(candles, current_index):
    """Q pivot lists from candles up to current_index (never beyond it)."""

    if candles is None or current_index is None:
        return [], []

    frame = candles.iloc[: current_index + 1].reset_index(drop=True).copy()
    # min_change=0 keeps every raw 3/3 pivot (same detector as the Scanner).
    raw_highs, raw_lows = find_pivots(
        frame,
        left=PIVOT_LEFT,
        right=PIVOT_RIGHT,
        min_change=0
    )

    return (
        _alternation_filter(raw_highs, raw_lows),
        _alternation_filter(raw_lows, raw_highs)
    )


def build_triangle_only_lines(
    highs,
    lows,
    existing_upper,
    existing_lower,
    current_index,
    candles=None,
    max_span=None
):
    """Return (upper, lower) extra Triangle-only candidates (T, then Q).

    A line whose own span already exceeds `max_span` (the engine locality
    limit) can only form non-local pairs, so it is not generated.

    Candle-free calls keep the previous behavior: no extra lines.
    """

    if candles is None or current_index is None:
        return [], []

    local_highs, local_lows = local_alternation_pivots(candles, current_index)

    result = []

    for side, points, local_points, existing in (
        ("high", highs, local_highs, existing_upper),
        ("low", lows, local_lows, existing_lower),
    ):
        seen = {
            _line_key(candidate)
            for candidate in existing
            if isinstance(candidate, dict) and "second_index" in candidate
        }
        extra = []
        generated = (
            _two_point_lines(points, side, current_index)
            + build_candidate_lines(local_points)
            + _two_point_lines(local_points, side, current_index)
        )
        for candidate in generated:
            key = _line_key(candidate)
            if key in seen or not _triangle_side_slope(candidate, side):
                continue
            if max_span is not None and candidate["structure_span"] > max_span:
                continue
            seen.add(key)
            candidate["triangle_only"] = True
            extra.append(candidate)
        result.append(extra)

    return result[0], result[1]
