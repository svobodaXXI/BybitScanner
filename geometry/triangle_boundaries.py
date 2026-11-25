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


def anchor_order_possible(upper_line, lower_line, highs, lows):
    """TRI-PERF-1: necessary condition of anchor_sequence.valid, checked
    before the expensive pair evaluation.

    Same rule as pair_metrics.calculate_pair_metrics: the later anchor must
    be the first confirmed opposite-side pivot after the earlier anchor;
    equal anchor indices never form a valid sequence. A pair failing it can
    never be admitted, so skipping it changes no result.
    """

    upper_anchor = upper_line.get("anchor_index")
    lower_anchor = lower_line.get("anchor_index")

    if upper_anchor is None or lower_anchor is None or upper_anchor == lower_anchor:
        return False

    if upper_anchor < lower_anchor:
        primary, secondary, opposite = upper_anchor, lower_anchor, lows
    else:
        primary, secondary, opposite = lower_anchor, upper_anchor, highs

    following = [
        point["index"]
        for point in (opposite or [])
        if (
            isinstance(point, dict)
            and point.get("index") is not None
            and point["index"] > primary
        )
    ]

    return bool(following) and min(following) == secondary


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


def build_closed_wick_triangle_pairs(highs, lows, candles, current_index, max_span=None):
    """Recover paired outer contacts without promoting candle wicks to pivots.

    A/B/C remain confirmed by the native pair evaluator. Each side requires
    independent confirmed forward support and a later actual enclosing wick.
    Only one exact outer ray per first anchor; no fit tolerance or new span.
    The two rays are paired only within their original adjacent A/B episode.
    """
    import math
    if (candles is None or current_index is None or current_index < 0
            or current_index >= len(candles) or not {"high", "low"}.issubset(candles.columns)):
        return []
    from .candidate import DEFAULT_TOLERANCE_PERCENT, _error_percent, _calculate_absolute_errors
    from .trendline import fit_anchor_trendline
    from .envelope_metrics import evaluate_strict_wedge_wicks

    prefix = candles.iloc[:current_index+1]
    def confirmed(points, side):
        return sorted((p for p in points or [] if
            type(p.get("index")) is int and 0 <= p["index"] <= current_index-PIVOT_RIGHT
            and math.isfinite(float(p["price"])) and float(p["price"]) > 0
            and float(prefix.iloc[p["index"]][side]) == float(p["price"])),
            key=lambda p:p["index"])
    hs, ls = confirmed(highs, "high"), confirmed(lows, "low")
    def ray(anchor, points, side, sign):
        a, price = anchor["index"], float(anchor["price"])
        if current_index-a < DEFAULT_MIN_LINE_SPAN:
            return None
        values = prefix[side].iloc[a+1:].to_numpy(dtype=float)
        if not all(math.isfinite(x) and x > 0 for x in values):
            return None
        # Tightest enclosing slope through the immutable first contact.
        # Tie: earliest real contact; never extend END merely to refresh age.
        offset = max(range(1,len(values)+1),
                     key=lambda k: sign*(values[k-1]-price)/k)
        contact_index = a+offset
        slope = (values[offset-1]-price)/offset
        if (sign*slope >= 0 or offset < DEFAULT_MIN_LINE_SPAN
                or (max_span is not None and offset > max_span)):
            return None
        prior = [p for p in points if a < p["index"] < contact_index]
        if not prior or any(p["index"] >= contact_index for p in points):
            return None
        contact = {"index":contact_index, "price":float(values[offset-1]),
                   "type":side, "contact_kind":"CLOSED_WICK_NOT_CONFIRMED_PIVOT"}
        line = fit_anchor_trendline([anchor,contact])
        if line is None:
            return None
        errors = [(p, _error_percent(float(p["price"]), calculate_price(line,p["index"])))
                  for p in prior]
        if any(error is None for _,error in errors):
            return None
        support = [p for p,error in errors if error <= DEFAULT_TOLERANCE_PERCENT]
        if not support:
            return None
        candidate_points = [anchor,*support,contact]
        confirmations = len(support)  # do not count the wick as a confirmed pivot
        absolute_errors = _calculate_absolute_errors(line,candidate_points)
        line.update(points=len(candidate_points), confirmations=confirmations,
                    error_mean=sum(absolute_errors)/len(absolute_errors),
                    error_max=max(absolute_errors),
                    structure_span=offset, support_ratio=confirmations/len(prior),
                    confirmation_error_percent=sum(error for _,error in errors)/len(errors),
                    contact_kind=contact["contact_kind"])
        if evaluate_strict_wedge_wicks(line,prefix,
                "upper" if side=="high" else "lower",current_index,current_index) != []:
            return None
        return {"points":candidate_points,"line":line,"anchor_index":a,
                "second_index":contact_index,"confirmations":confirmations,
                "structure_span":offset,"support_ratio":confirmations/len(prior),
                "triangle_only":True,"triangle_closed_wick":True}
    pairs = []
    for high in hs:
        for low in ls:
            a,b = high["index"],low["index"]
            if not anchor_order_possible({"anchor_index":a},{"anchor_index":b},hs,ls):
                continue
            if max_span is not None and current_index-min(a,b)>max_span:
                continue
            upper,lower = ray(high,hs,"high",1),ray(low,ls,"low",-1)
            if upper is None or lower is None:
                continue
            if max_span is not None and max(upper["second_index"],lower["second_index"])-min(a,b)>max_span:
                continue
            upper["triangle_wick_episode"] = lower["triangle_wick_episode"] = (a,b)
            pairs.append((upper,lower))
    return pairs
