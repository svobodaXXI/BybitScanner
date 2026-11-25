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

def propose_control_boundary_from_print(
    *, family, episode_start, first_strict_index, established_pivots,
    candles, timeframe_ms, prefix_as_of_ms, observed_print,
):
    """Evaluate one already-validated publicTrade print in native TF coordinates.

    The caller supplies an event-ordered, gap-free *local candle prefix*
    before this print, including any earlier prints in the active candle.
    This does not certify complete exchange coverage or publish geometry.
    Derive point 2 from that prefix, never from a completed future candle
    or a caller-provided extreme. Process a new candle on its first print;
    process a further extreme in the same candle without waiting for close.
    """
    from numbers import Integral
    import pandas as pd

    unavailable = {"status": "REBUILD_UNAVAILABLE", "lines": []}
    try:
        event_ms = observed_print.timestamp_ms
        receipt_ms = observed_print.received_at_ms
        trade_id = observed_print.trade_id
        price = Decimal(str(observed_print.price))
        if (family not in ("falling", "rising")
                or timeframe_ms not in (60_000, 300_000)
                or type(prefix_as_of_ms) is not int
                or type(event_ms) is not int or type(receipt_ms) is not int
                or not 0 < prefix_as_of_ms <= event_ms
                or receipt_ms <= 0 or not isinstance(trade_id, str) or not trade_id
                or not price.is_finite() or price <= 0
                or type(episode_start) is not int
                or type(first_strict_index) is not int
                or not 0 <= episode_start <= first_strict_index < len(candles)):
            return unavailable
        opens = list(candles["open_time_ms"])
        if any(not isinstance(t, Integral) or isinstance(t, bool)
               or t <= 0 or t % timeframe_ms for t in opens):
            return unavailable
        if any(b - a != timeframe_ms for a, b in zip(opens, opens[1:])):
            return unavailable
        event_open = event_ms // timeframe_ms * timeframe_ms
        last_open = int(opens[-1])
        if (not last_open <= prefix_as_of_ms <= last_open + timeframe_ms
                or event_open not in (last_open, last_open + timeframe_ms)):
            return unavailable
        extreme_column = "low" if family == "falling" else "high"
        prior = [Decimal(str(v)) for v in candles[extreme_column].iloc[episode_start:]]
        if not all(v.is_finite() and v > 0 for v in prior):
            return unavailable
        old = min(prior) if family == "falling" else max(prior)
        if not (price < old if family == "falling" else price > old):
            return {"status": "UNCHANGED", "lines": []}

        # Only the actual prefix plus this print may influence wick tests.
        # Keep the frozen caller-owned candle frame untouched.
        columns = ["open_time_ms", "open", "high", "low", "close"]
        if event_open == last_open:
            row = candles.iloc[-1]
            high, low, opening = (
                Decimal(str(row[name])) for name in ("high", "low", "open")
            )
            if not all(v.is_finite() and v > 0 for v in (high, low, opening)):
                return unavailable
            if not low <= opening <= high:
                return unavailable
            base = candles[columns].iloc[:-1]
            row = [event_open, opening, max(high, price), min(low, price), price]
        else:
            base = candles[columns]
            row = [event_open, price, price, price, price]
        event_prefix = pd.concat(
            [base, pd.DataFrame([row], columns=columns)], ignore_index=True,
        )
        result = propose_control_boundary(
            family=family, episode_start=episode_start,
            first_strict_index=first_strict_index, previous_extreme=old,
            trade_price=price, event_index=len(event_prefix)-1,
            event_time_ms=event_ms, established_pivots=established_pivots,
            candles=event_prefix,
        )
        return dict(result, source_trade_id=trade_id, received_at_ms=receipt_ms,
                    previous_extreme=str(old), source_bar_open_ms=event_open)
    except (AttributeError, KeyError, IndexError, TypeError, ValueError,
            InvalidOperation, OverflowError):
        return unavailable

def load_control_anchor_seed(record, *, directory=None):
    """Restore an observation seed from the exact immutable native signal.

    No substitution of Robot's projected M1 geometry, current chart candles,
    or guessed START. The returned prefix ends at the Scanner decision bar.
    Its pivots are established as of that closed-bar cutoff, not guessed
    historical confirmation times. Missing or inconsistent evidence is not
    a new signal and must not authorize a revision.
    """
    import pandas as pd
    from signal_archive import load_frozen_signal_geometry
    from signal_geometry_snapshot import validate_snapshot
    from pivots import find_pivots
    from .triangle_boundaries import local_alternation_pivots

    try:
        signal = record.signal_snapshot
        candidate_id = record.candidate_id
        symbol = record.symbol.value
        family = {"Falling Wedge": "falling", "Rising Wedge": "rising"}.get(
            signal.get("pattern")
        )
        if family is None or signal.get("symbol") != symbol:
            return None
        timeframe = str(signal.get("timeframe", ""))
        interval = {"1": 60_000, "5": 300_000}.get(timeframe)
        if interval is None:
            return None
        source = load_frozen_signal_geometry(candidate_id, directory=directory)
        if source is None:
            return None
        _, digest = validate_snapshot(
            source, candidate_id=candidate_id, symbol=symbol, timeframe=timeframe,
        )
        geometry = signal["geometry"]
        current, start, end = (geometry[k] for k in
                               ("current_index", "start_index", "end_index"))
        if (any(type(i) is not int for i in (current, start, end))
                or not 0 <= start < end <= current < len(source["bars"])):
            return None
        bars = source["bars"][:current+1]
        times = [bar["open_time_ms"] for bar in bars]
        if (any(t <= 0 or t % interval for t in times)
                or any(b-a != interval for a, b in zip(times, times[1:]))):
            return None
        cutoff = times[-1] + interval
        boundaries = {b["boundary_id"]: b for b in source["boundaries"]}
        first_indices = []
        for side in ("upper", "lower"):
            line = geometry[side+"_line"]
            boundary = boundaries[side]
            first, second = line["anchor_index"], line["second_index"]
            if (line.get("model") != "anchor" or boundary["kind"] != "ray"
                    or type(first) is not int or type(second) is not int
                    or not start <= first < second <= end):
                return None
            wick = "high" if side == "upper" else "low"
            for index, field, point in zip(
                (first, second), ("anchor_price", "second_price"), boundary["anchors"],
            ):
                price = Decimal(str(line[field]))
                if (point["bar_open_time_ms"] != times[index]
                        or price != Decimal(str(point["price"]))
                        or price != Decimal(str(bars[index][wick]))):
                    return None
            first_indices.append(first)
        if min(first_indices) != start:
            return None
        strict_side = "upper" if family == "falling" else "lower"
        strict_index = geometry[strict_side+"_line"]["anchor_index"]
        strict_second = geometry[strict_side+"_line"]["second_index"]
        frame = pd.DataFrame(bars)
        # Same global and local confirmed-pivot sources as wedge construction.
        global_highs, global_lows = find_pivots(frame.copy())
        local_highs, local_lows = local_alternation_pivots(frame, current)
        pivots = (global_highs + local_highs if family == "falling"
                  else global_lows + local_lows)
        established = {
            p["index"]: {"index": p["index"], "price": float(p["price"]),
                         "known_at_ms": cutoff}
            for p in pivots if strict_index <= p["index"] <= current
        }
        if not {strict_index, strict_second}.issubset(established):
            return None
        return {
            "candidate_id": candidate_id, "symbol": symbol, "family": family,
            "timeframe_ms": interval, "source_geometry_sha256": digest,
            "episode_start": start, "first_strict_index": strict_index,
            "prefix_as_of_ms": cutoff, "candles": frame,
            "established_pivots": [established[i] for i in sorted(established)],
            "original_strict_line": dict(geometry[strict_side+"_line"]),
        }
    except (AttributeError, KeyError, TypeError, ValueError, IndexError,
            InvalidOperation, OverflowError):
        return None

