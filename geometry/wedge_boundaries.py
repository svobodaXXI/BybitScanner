"""Additional strict-side wedge supports, using existing local swing pivots.

A short line-contact span is not a short structure: require the same
minimum confirmed support span and confirmation count as the normal
generator. Global structural pivots and first-anchor selection stay intact.
These alternatives are not usable for triangles or the non-strict side.
"""
from .candidate import DEFAULT_MIN_LINE_SPAN, build_candidate_lines
from .triangle_boundaries import anchor_order_possible, local_alternation_pivots
from .envelope_metrics import evaluate_strict_wedge_wicks


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


def build_wedge_hull_support_lines(highs, lows, upper, lower, candles, current_index):
    """Recover a clean non-strict wedge edge with two global confirmed pivots.

    Keep the normal 30-bar contact span. Unlike the local strict-support
    generator, this path adds only a single forward confirmation (the
    second contact), and requires clean candle containment of both paired
    boundaries before evaluation. No new structural pivots or tolerances.
    """
    if candles is None or current_index is None:
        return [], []
    result = []
    for side, points, existing in (("upper", highs, upper), ("lower", lows, lower)):
        seen = {(c["anchor_index"], c["second_index"]) for c in existing
                if isinstance(c, dict) and "second_index" in c}
        extra = []
        for c in build_candidate_lines(points, min_confirmations=1):
            key = (c["anchor_index"], c["second_index"])
            if key in seen or c["confirmations"] != 1:
                continue
            slope = c["line"]["slope"]
            if not (slope > 0 if side == "upper" else slope < 0):
                continue
            if evaluate_strict_wedge_wicks(c["line"], candles, side,
                                           c["second_index"], current_index) != []:
                continue
            c["wedge_hull_support"] = side
            seen.add(key)
            extra.append(c)
        result.append(extra)
    return result[0], result[1]


def wedge_hull_pair_allowed(upper, lower, highs, lows, candles, current_index):
    """Extra two-contact edges may pair only with a regular strict boundary.

    Both boundaries must be wick-clean through the actual pair END, not
    through future breakout candles. The normal pair validator, anchor,
    locality, freshness and selection gates still run unchanged.
    """
    up = upper.get("wedge_hull_support") if isinstance(upper, dict) else None
    low = lower.get("wedge_hull_support") if isinstance(lower, dict) else None
    if not up and not low:
        return True
    if (up and low) or candles is None or current_index is None:
        return False
    counterpart = lower if up else upper
    if (not isinstance(counterpart, dict) or counterpart.get("triangle_only")
            or is_strict_wedge_support(counterpart)):
        return False
    ul, ll = upper["line"], lower["line"]
    us, ls = ul["slope"], ll["slope"]
    if not (0 < us < ls if up else us < ls < 0):
        return False
    if not anchor_order_possible(ul, ll, highs, lows):
        return False
    end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
    return (evaluate_strict_wedge_wicks(ul, candles, "upper", end, current_index) == []
            and evaluate_strict_wedge_wicks(ll, candles, "lower", end, current_index) == [])


def prefer_recovered_wedge_hulls(candidates, candles):
    """Replace only a proven defective competing boundary of the same episode.

    A recovered hull must share both strict contacts, the other second
    contact and END with a regular, equally canonical candidate. Its
    impulse origin must be exactly the old non-strict START, and its
    primary anchor the old secondary anchor. The old non-strict ray
    must actually cross a wick; the corrected pair must enclose both
    sides. Otherwise the recovered alternative cannot change selection.
    """
    def details(candidate):
        g = candidate["geometry"]
        pm = getattr(g, "pair_metrics", {}) or {}
        seq = pm.get("anchor_sequence") or {}
        family = seq.get("family")
        if family not in ("rising", "falling") or not seq.get("valid"):
            return None
        strict, other = ((g.upper_line, g.lower_line) if family == "falling"
                         else (g.lower_line, g.upper_line))
        key = (family, strict.get("anchor_index"), strict.get("second_index"),
               other.get("second_index"), g.end_index, candidate["mode_priority"])
        return g, pm, seq, strict, other, key

    originals = {}
    additions = []
    for i, candidate in enumerate(candidates):
        g = candidate["geometry"]
        pm = getattr(g, "pair_metrics", {}) or {}
        d = details(candidate)
        if pm.get("wedge_hull_support"):
            additions.append((i, candidate, d))
        elif d is not None:
            originals.setdefault(d[-1], []).append((i, candidate, d))
    if not additions:
        return candidates
    drop = {i for i, _, _ in additions}
    if candles is None:
        # No new source-dependent alternative in candle-free replay.
        return [c for i, c in enumerate(candidates) if i not in drop]
    for i, candidate, d in additions:
        if d is None or not candidate["fresh"] or candidate["strict_wick_exception"]:
            continue
        g, pm, seq, strict, other, key = d
        if (seq.get("primary_anchor") != strict.get("anchor_index")
                or seq.get("secondary_anchor") != other.get("anchor_index")):
            continue
        side = pm["wedge_hull_support"]
        if side != ("lower" if key[0] == "falling" else "upper"):
            continue
        if any(evaluate_strict_wedge_wicks(getattr(g, s + "_line"), candles,
                    s, g.end_index, g.current_index) != [] for s in ("upper", "lower")):
            continue
        for j, old, od in originals.get(key, ()):
            og, _, os, _, oo, _ = od
            if (not old["fresh"] or old["strict_wick_exception"]
                    or candidate["body_breaches"] > old["body_breaches"]
                    or os.get("primary_anchor") != oo.get("anchor_index")
                    or os.get("primary_anchor") != seq.get("impulse_origin_index")
                    or os.get("secondary_anchor") != seq.get("primary_anchor")):
                continue
            breaches = evaluate_strict_wedge_wicks(oo, candles, side, og.end_index, og.current_index)
            if breaches:
                drop.discard(i)
                drop.add(j)
    return [c for i, c in enumerate(candidates) if i not in drop]
