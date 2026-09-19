"""
geometry.pre_pattern

??????????? ???????? ???? ????? ??????? ?????????????? ?????????.

?? ??????? ?????:
- ?? ?????? ?? Validation;
- ?? ?????? ?? Ranking;
- ?? ?????? anchors;
- ?????? ???????? pre-pattern context.
"""


from collections import deque
from itertools import groupby
from math import isfinite
from numbers import Integral


def detect_pre_pattern_impulse(
    candles,
    start_index,
    lookback=20
):
    if (
        candles is None
        or start_index is None
        or start_index <= 0
    ):
        return None

    window_start = max(
        0,
        int(start_index) - int(lookback)
    )

    window_end = int(start_index)

    if window_end <= window_start:
        return None

    try:
        first_close = float(
            candles.iloc[window_start]["close"]
        )

        last_close = float(
            candles.iloc[window_end]["close"]
        )
    except Exception:
        return None

    if first_close <= 0:
        return None

    change_percent = (
        (last_close - first_close)
        / first_close
        * 100.0
    )

    if change_percent > 0:
        direction = "UP"
    elif change_percent < 0:
        direction = "DOWN"
    else:
        direction = "FLAT"

    return {
        "window_start": window_start,
        "window_end": window_end,
        "lookback": window_end - window_start,
        "first_close": first_close,
        "last_close": last_close,
        "change_percent": float(
            change_percent
        ),
        "direction": direction
    }


def collect_impulse_terminal_evidence(
    candles, highs, lows, start_index, *, as_of_index, right,
    lookback=20, max_candidates=4,
):
    """Pure research evidence; never selects a START, subtype or geometry.

    Indices are positions in the same closed source frame used by Scanner.
    Inspect pivots in [start_index - lookback, start_index], inclusive, and
    only their available right-confirmation candles. Keep the most recent
    max_candidates confirmed diagnostics chronologically.
    These bounds control observation cost, not impulse-strength admission.

    A supplied pivot qualifies only when index + right <= as_of_index.
    Before then even its membership in a full-history pivot list is future
    evidence, so it is excluded from candidates, pending diagnostics, swing
    measurements and aggregate status.
    confirmed_at_time_ms identifies that confirmation candle using OHLC time
    (normally its OPEN timestamp); the caller certifies its CLOSE via as_of.
    Inputs must use the actual scan's right window and aligned pivot lists;
    filtered Scanner pivots are not assumed exhaustive or rediscovered here.

    Each swing uses the nearest strictly earlier opposing supplied pivot.
    EVIDENCE_AVAILABLE means exactly one measurable terminal alternative,
    not a strong impulse. Multiple alternatives, flat/inconsistent swings,
    simultaneous HIGH/LOW pivots or a clipped shortlist remain AMBIGUOUS.
    Missing swing origins remain INSUFFICIENT_HISTORY; a boundary candle is
    never substituted as an origin.
    """
    result = {
        "status": "INVALID_INPUT", "reason": "invalid_source_evidence",
        "window": None, "candidates": [], "pending_candidates": [],
        "candidates_truncated": False, "endpoint_context": None,
    }
    integers = (start_index, as_of_index, right, lookback, max_candidates)
    if any(isinstance(x, bool) or not isinstance(x, Integral) for x in integers):
        return result
    if not (0 <= start_index <= as_of_index and right >= 0
            and lookback > 0 and max_candidates > 0):
        return result
    try:
        candle_count = 0 if candles is None else len(candles)
    except TypeError:
        return result
    if candle_count == 0:
        result.update(status="INSUFFICIENT_HISTORY", reason="no_closed_candles")
        return result
    if as_of_index >= candle_count:
        return result

    first = max(0, start_index - lookback)
    last = min(as_of_index, start_index + right)
    try:
        # Slice BEFORE examining values: future appended rows cannot affect this.
        rows = candles.iloc[first:last + 1].to_dict("records")
        previous_time = None
        for row in rows:
            timestamp = float(row["time"])
            prices = [float(row[key]) for key in ("open", "high", "low", "close")]
            if (not isfinite(timestamp) or timestamp < 0 or not timestamp.is_integer()
                    or (previous_time is not None and timestamp <= previous_time)
                    or any(not isfinite(p) or p <= 0 for p in prices)):
                return result
            open_price, high, low, close = prices
            if not low <= min(open_price, close) <= max(open_price, close) <= high:
                return result
            row.update(time=int(timestamp), open=open_price, high=high, low=low, close=close)
            previous_time = timestamp

        points = {}
        for side, pivots in (("HIGH", highs), ("LOW", lows)):
            for pivot in pivots:
                index = pivot["index"]
                if isinstance(index, bool) or not isinstance(index, Integral) or index < 0:
                    return result
                if not first <= index <= start_index:
                    continue  # Do not even read prices of future/out-of-window pivots.
                if index + right > as_of_index:
                    # Seeing this pivot in a full-history list is itself lookahead.
                    continue
                row = rows[index - first]
                price = float(pivot["price"])
                if pivot["type"] != side.lower() or price != row[side.lower()]:
                    return result
                points[index, side] = {
                    "index": int(index), "time_ms": row["time"],
                    "side": side, "price": price,
                }
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return result

    result["window"] = {
        "start_index": int(first), "end_index": int(last),
        "start_time_ms": rows[0]["time"], "end_time_ms": rows[-1]["time"],
        "terminal_end_index": int(start_index), "as_of_index": int(as_of_index),
        "right": int(right), "lookback": int(lookback),
        "left_truncated": start_index < lookback,
        "max_candidates": int(max_candidates),
    }
    result["endpoint_context"] = detect_pre_pattern_impulse(
        candles.iloc[:as_of_index + 1], start_index, lookback=lookback,
    )
    recent = deque(maxlen=int(max_candidates))
    opposing = {}
    ordered = [points[key] for key in sorted(points)]
    for index, group in groupby(ordered, key=lambda point: point["index"]):
        group = list(group)
        for point in group:
            confirmation = index + right
            candidate = dict(
                point, status="INSUFFICIENT_HISTORY",
                confirmed_at_index=int(confirmation),
                confirmed_at_time_ms=rows[confirmation - first]["time"],
                previous_opposing_index=None, previous_opposing_time_ms=None,
                displacement_percent=None, duration_bars=None, direction="UNKNOWN",
            )
            previous = opposing.get("LOW" if point["side"] == "HIGH" else "HIGH")
            if previous is not None:
                displacement = (point["price"] / previous["price"] - 1) * 100
                candidate.update(
                    previous_opposing_index=previous["index"],
                    previous_opposing_time_ms=previous["time_ms"],
                    displacement_percent=displacement,
                    duration_bars=index - previous["index"],
                    status="AMBIGUOUS",
                )
                if len(group) == 1 and not previous["ambiguous"]:
                    if point["side"] == "HIGH" and displacement > 0:
                        candidate.update(status="EVIDENCE_AVAILABLE", direction="UP")
                    elif point["side"] == "LOW" and displacement < 0:
                        candidate.update(status="EVIDENCE_AVAILABLE", direction="DOWN")
            if len(group) > 1:
                candidate["status"] = "AMBIGUOUS"
            recent.append(candidate)
        # Same-candle HIGH/LOW cannot establish an intra-candle swing order.
        for point in group:
            opposing[point["side"]] = dict(point, ambiguous=len(group) > 1)

    result["candidates"] = list(recent)
    result["pending_candidates"] = []
    result["candidates_truncated"] = len(points) > max_candidates
    measured = sum(p["status"] == "EVIDENCE_AVAILABLE" for p in recent)
    if (result["candidates_truncated"] or measured > 1
          or any(p["status"] == "AMBIGUOUS" for p in recent)):
        result.update(status="AMBIGUOUS", reason="terminal_alternatives_unresolved")
    elif measured == 1:
        result.update(status="EVIDENCE_AVAILABLE", reason="one_measured_swing")
    else:
        result.update(status="INSUFFICIENT_HISTORY", reason="no_confirmed_opposing_swing")
    return result
