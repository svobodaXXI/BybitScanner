"""Contact-first strict boundary construction for a dynamic wedge request.

The existing detector owns the episode and the opposite line. This module
returns *candidates*, never a revised signal, a trade or a journal event.
The candle frame must be an as-of prefix including the triggering print
(if the current candle is open). It must not contain later OHLC values.
"""
from dataclasses import dataclass
import math

from .candidate import DEFAULT_MIN_LINE_SPAN, build_candidate_lines
from .control_anchor import ConfirmedAnchor, RebuildRequest
from .envelope_metrics import evaluate_strict_wedge_wicks, line_value
from .trendline import fit_anchor_trendline


@dataclass(frozen=True)
class BoundarySelection:
    status: str
    candidates: tuple[dict, ...] = ()


def _roundoff_equal(a, b):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b) <= 4*(math.ulp(a)+math.ulp(b))


def select_strict_boundary(request, confirmed_anchors, candles, *,
                           episode_start, current_index, opposite_line):
    """Choose only the contact class allowed by the owner.

    First try all same-side earlier confirmed contacts with the control
    anchor. Both lines must converge and retain positive width throughout
    the owned episode. Test strict containment across the WHOLE episode
    (not only the new line's first contact). A clean contact ray without
    enough existing native support is not permission to bypass the anchor.

    Only when no otherwise feasible contact ray encloses the episode and
    at least one such ray fails solely on preceding extrema, consider
    supported pairs of earlier extrema. Never choose a shifted ray or
    apply the isolated-wick exception to this canonical reference line.
    No final wedge admission or selection by score here.
    """
    unavailable = BoundarySelection("EVIDENCE_UNAVAILABLE")
    if (not isinstance(request, RebuildRequest) or request.control_anchor is None
            or request.family not in ("falling", "rising")
            or type(episode_start) is not int or type(current_index) is not int
            or not 0 <= episode_start < current_index):
        return unavailable
    control = request.control_anchor
    side = "upper" if request.family == "falling" else "lower"
    column = "high" if side == "upper" else "low"
    try:
        if len(candles) != current_index+1:
            return unavailable
        if not episode_start <= control.index < current_index:
            return unavailable
        if not control.pivot_at_ms <= control.known_at_ms < request.timestamp_ms:
            return unavailable
        # Verify the triggering print is represented in the as-of frame.
        extreme = float(request.new_extreme)
        observed = float(candles.iloc[current_index]["low" if side == "upper" else "high"])
        if not _roundoff_equal(extreme, observed):
            return unavailable
        anchors = {}
        for a in confirmed_anchors:
            if not isinstance(a, ConfirmedAnchor):
                return unavailable
            if not episode_start <= a.index < current_index:
                continue
            if not a.pivot_at_ms <= a.known_at_ms < request.timestamp_ms:
                continue
            if a.pivot_at_ms > control.pivot_at_ms or a.index > control.index:
                # A newer eligible same-side pivot contradicts the request.
                return unavailable
            if a.index in anchors and anchors[a.index] != a:
                return unavailable
            price = float(a.price)
            if price <= 0 or not _roundoff_equal(price, float(candles.iloc[a.index][column])):
                return unavailable
            anchors[a.index] = a
        if anchors.get(control.index) != control:
            return unavailable
        points = [{"index": i, "price": float(a.price)} for i,a in sorted(anchors.items())]
        earlier = [p for p in points if p["index"] < control.index]
        if not earlier:
            return unavailable
        control_point = points[-1]
        opposite_slope = float(opposite_line["slope"])
        if not math.isfinite(opposite_slope):
            return unavailable

        def feasible(line):
            if line is None:
                return False
            slope = line["slope"]
            if not (slope < opposite_slope < 0 if side == "upper"
                    else slope > opposite_slope > 0):
                return False
            # Linear width positive at both endpoints implies positive
            # width everywhere between. No fictitious intersection.
            for i in (episode_start, current_index):
                a, b = line_value(line, i), line_value(opposite_line, i)
                if a is None or b is None or not all(math.isfinite(x) and x > 0 for x in (a,b)):
                    return False
                if not (a > b if side == "upper" else a < b):
                    return False
            return True

        def breaches(line):
            return evaluate_strict_wedge_wicks(
                {**line, "anchor_index": episode_start}, candles, side,
                current_index, current_index,
            )

        clean_contact_keys = set()
        prior_obstruction = False
        for point in earlier:
            line = fit_anchor_trendline([point, control_point])
            if not feasible(line):
                continue
            outside = breaches(line)
            if outside is None:
                return unavailable
            if not outside:
                clean_contact_keys.add((point["index"], control.index))
            elif all(i < control.index for i in outside):
                prior_obstruction = True

        # Reuse the established generator/confirmation rules. A short
        # contact span is allowed only with the same full support span,
        # as in geometry.wedge_boundaries (PR #1330).
        supported = [c for c in build_candidate_lines(points, min_line_span=1)
                     if c["structure_span"] >= DEFAULT_MIN_LINE_SPAN]
        if clean_contact_keys:
            candidates = tuple(c for c in supported
                               if (c["anchor_index"],c["second_index"]) in clean_contact_keys)
            return BoundarySelection("CONTROL_CONTACT" if candidates else "CONTACT_UNSUPPORTED", candidates)
        if not prior_obstruction:
            return BoundarySelection("NO_VALID_CONTACT")

        fallback = []
        for c in supported:
            if c["second_index"] >= control.index:
                continue
            line = c["line"]
            if not feasible(line):
                continue
            outside = breaches(line)
            if outside is None:
                return unavailable
            if not outside:
                fallback.append(c)
        return BoundarySelection("EARLIER_ENVELOPE" if fallback else "NO_VALID_ENVELOPE", tuple(fallback))
    except (KeyError, AttributeError, TypeError, ValueError, OverflowError, IndexError):
        return unavailable
