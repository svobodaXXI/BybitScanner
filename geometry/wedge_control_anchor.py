"""Source-time strict wedge boundary proposals; not trading decisions."""
from decimal import Decimal, InvalidOperation
from .envelope_metrics import evaluate_strict_wedge_wicks
from .trendline import fit_anchor_trendline


def propose_control_boundary(*, family, episode_start, first_strict_index,
                             previous_extreme, trade_price, event_index,
                             event_time_ms, established_pivots, candles):
    """Preserve episode and first strict contact; propose a clean revision.

    Caller supplies established strict-side pivots (index, price, known_at_ms)
    and the actual as-of candle prefix, including the in-progress event bar.
    No inference of intrabar order from completed OHLC. Whole-geometry
    validation and durable revision publication belong to the integration.
    """
    if family not in ("falling", "rising"):
        raise ValueError("invalid family")
    old, price = Decimal(str(previous_extreme)), Decimal(str(trade_price))
    if not all(v.is_finite() and v > 0 for v in (old, price)):
        raise ValueError("invalid price")
    if not (price < old if family == "falling" else price > old):
        return {"status": "UNCHANGED", "lines": []}
    result = {"status": "REBUILD_UNAVAILABLE", "lines": [],
              "episode_start": episode_start, "event_time_ms": event_time_ms,
              "trigger_price": str(price)}
    if (candles is None or any(type(i) is not int for i in
            (episode_start, first_strict_index, event_index, event_time_ms))
            or not 0 <= episode_start <= first_strict_index < event_index < len(candles)
            or event_time_ms <= 0):
        return result
    side = "upper" if family == "falling" else "lower"
    column, opposite = ("high", "low") if side == "upper" else ("low", "high")
    points = {}
    try:
        if Decimal(str(candles[opposite].iloc[event_index])) != price:
            return result
        for p in established_pivots:
            i, known = p["index"], p["known_at_ms"]
            if type(i) is not int or type(known) is not int:
                return result
            if not first_strict_index <= i < event_index or not 0 < known <= event_time_ms:
                continue
            if Decimal(str(p["price"])) != Decimal(str(candles[column].iloc[i])):
                return result
            if i in points and points[i] != p:
                return result
            points[i] = dict(p)
    except (KeyError, TypeError, ValueError, IndexError, InvalidOperation, AttributeError):
        return result
    if first_strict_index not in points or len(points) < 2:
        return result
    first, control = points[first_strict_index], points[max(points)]
    result["control_anchor"] = dict(control)

    def measure(second):
        line = fit_anchor_trendline([first, second])
        if line is None or not (line["slope"] < 0 if side == "upper" else line["slope"] > 0):
            return None, None
        return line, evaluate_strict_wedge_wicks(line, candles, side, event_index, event_index)

    line, breaches = measure(control)
    if breaches == []:
        return dict(result, status="CONTROL_CONTACT", lines=[line])
    # The fallback is permitted only for a measured earlier structural
    # protrusion, not for a subsequent breakout or a failed trading gate.
    earlier = {i for i in points if first_strict_index < i < control["index"]}
    if not breaches or not earlier.intersection(breaches):
        return result
    fallback = []
    for i in sorted(earlier):
        alternative, outside = measure(points[i])
        if outside == []:
            fallback.append(alternative)
    if fallback:
        return dict(result, status="OUTER_ENVELOPE", lines=fallback)
    return result
