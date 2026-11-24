"""Additional strict-side wedge supports, using existing local swing pivots.

A short line-contact span is not a short structure: require the same
minimum confirmed support span and confirmation count as the normal
generator. Global structural pivots and first-anchor selection stay intact.
These alternatives are not usable for triangles or the non-strict side.
"""
from .candidate import DEFAULT_MIN_LINE_SPAN, build_candidate_lines
from .triangle_boundaries import local_alternation_pivots


def build_strict_wedge_support_lines(highs, lows, upper, lower, candles, current_index):
    if candles is None or current_index is None:
        return [], []
    local_highs, local_lows = local_alternation_pivots(candles, current_index)
    result = []
    for side, pivots, local, existing in (
        ("upper", highs, local_highs, upper),
        ("lower", lows, local_lows, lower),
    ):
        structural = {p["index"] for p in pivots}
        seen = {(c["anchor_index"], c["second_index"]) for c in existing
                if isinstance(c, dict) and "anchor_index" in c and "second_index" in c}
        # Only consider the missing geometric support, not a new START.
        # Short contacts still need the normal full support span.
        extra = []
        for c in build_candidate_lines(local, min_line_span=1):
            key = (c["anchor_index"], c["second_index"])
            if key in seen or key[0] not in structural:
                continue
            if key[1] in structural and key[1] - key[0] >= DEFAULT_MIN_LINE_SPAN:
                continue
            if c["structure_span"] < DEFAULT_MIN_LINE_SPAN:
                continue
            slope = c["line"]["slope"]
            if not (slope < 0 if side == "upper" else slope > 0):
                continue
            c["strict_wedge_support"] = side
            seen.add(key)
            extra.append(c)
        result.append(extra)
    return result[0], result[1]


def is_strict_wedge_support(candidate):
    return isinstance(candidate, dict) and bool(candidate.get("strict_wedge_support"))


def strict_support_pair_allowed(upper, lower):
    if is_strict_wedge_support(lower) and is_strict_wedge_support(upper):
        return False
    if is_strict_wedge_support(upper):
        return isinstance(lower, dict) and not lower.get("triangle_only") and lower.get("line", {}).get("slope", 0) < 0
    if is_strict_wedge_support(lower):
        return isinstance(upper, dict) and not upper.get("triangle_only") and upper.get("line", {}).get("slope", 0) > 0
    return True
