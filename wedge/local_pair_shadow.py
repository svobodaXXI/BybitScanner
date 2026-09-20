"""Uncalled, research-only inspection of an explicitly supplied local wedge pair.

The caller supplies an already closed, original-index OHLC prefix, an as-of-confirmed
raw ledger, an episode start, and four anchors. This is NOT episode discovery,
production admission, breakout detection, a scorer, or a Robot decision.
"""

from __future__ import annotations

import math

from geometry.trendline import calculate_price, fit_anchor_trendline


SUPPORT_TOLERANCE_PERCENT = 0.6  # Existing geometry candidate tolerance; evidence only.
RIGHT_CONFIRMATION_BARS = 3  # Existing raw-pivot detector default.


def _scan_boundary(frame, line, side, start, end):
    """Measure strict body crossings and outer wick excursions; no ATR allowance."""
    if start > end:
        return {"empty": True, "body_indices": [], "wick_indices": [], "body_count": 0,
                "wick_count": 0, "max_body_depth": 0.0, "max_wick_depth": 0.0,
                "max_wick_run": 0}
    body, wick = [], []
    body_depth, wick_depth = [], []
    for i in range(start, end + 1):
        candle = frame.iloc[i]
        boundary = calculate_price(line, i)
        # Floating-point noise guard, NOT an exchange tick or ATR allowance.
        epsilon = 1e-12 * max(1.0, abs(boundary))
        if side == "upper":
            bd = max(float(candle["open"]), float(candle["close"])) - boundary
            wd = float(candle["high"]) - boundary
        else:
            bd = boundary - min(float(candle["open"]), float(candle["close"]))
            wd = boundary - float(candle["low"])
        if bd > epsilon:
            body.append(i)
            body_depth.append(bd)
        elif wd > epsilon:
            wick.append(i)
            wick_depth.append(wd)
    longest, current, previous = 0, 0, None
    for i in wick:
        current = current + 1 if previous is not None and i == previous + 1 else 1
        longest = max(longest, current)
        previous = i
    return {"empty": False, "body_indices": body, "wick_indices": wick,
            "body_count": len(body), "wick_count": len(wick),
            "max_body_depth": max(body_depth, default=0.0),
            "max_wick_depth": max(wick_depth, default=0.0),
            "max_wick_run": longest}


def evaluate_local_pair(frame, confirmed_points, *, as_of_index, timeframe,
                        episode_start, anchors):
    """Inspect one caller-proposed pair; NEVER choose a winner or admit a signal.

    anchors: {'h1': source_index, 'h2': source_index, 'l1': ..., 'l2': ...}.
    confirmed_points: S3-1c ledger_adapter shape with side/index/price,
    event_time_ms, confirm_index, confirm_time_ms and confirmation_contiguous.
    Every index is a source row position in the already-closed OHLC prefix.
    The caller, not this function, must establish chronological episode membership.
    """
    result = {"status": "UNKNOWN", "reasons": [], "family": None,
              "completion_status": "UNKNOWN", "episode_membership": "CALLER_PROPOSED",
              "as_of_index": as_of_index, "anchors": dict(anchors), "strict": {}}
    reasons = result["reasons"]
    if str(timeframe) != "5":
        reasons.append("UNSUPPORTED_TIMEFRAME: only researched 5m is covered")
        return result
    if frame is None or as_of_index is None or len(frame) != as_of_index + 1:
        reasons.append("CLOSED_AS_OF_PREFIX_REQUIRED")
        return result
    try:
        times = [int(v) for v in frame["time"].tolist()]
        if (not times or any(t < 1_000_000_000_000 or t >= 10_000_000_000_000 for t in times)
                or any(b - a != 300_000 for a, b in zip(times, times[1:]))):
            reasons.append("NONCONTIGUOUS_OR_UNPROVEN_SOURCE_BARS")
            return result
        for column in ("open", "high", "low", "close"):
            if any(not math.isfinite(float(v)) for v in frame[column]):
                reasons.append("INVALID_SOURCE_OHLC")
                return result
        for candle in frame.itertuples(index=False):
            if not (float(candle.low) <= min(float(candle.open), float(candle.close))
                    <= max(float(candle.open), float(candle.close)) <= float(candle.high)):
                reasons.append("INCONSISTENT_SOURCE_OHLC")
                return result
    except (TypeError, ValueError, KeyError, OverflowError):
        reasons.append("INVALID_SOURCE_FRAME")
        return result
    try:
        start = int(episode_start)
        a = {k: int(anchors[k]) for k in ("h1", "h2", "l1", "l2")}
    except (KeyError, ValueError, TypeError):
        reasons.append("MISSING_ANCHOR_COORDINATES")
        return result
    last = max(a.values())
    if not (0 <= start <= min(a.values()) and a["h1"] < a["h2"]
            and a["l1"] < a["l2"] and last <= as_of_index):
        reasons.append("ANCHORS_OUTSIDE_PROPOSED_EPISODE_OR_AS_OF")
        return result
    by_key = {}
    ambiguous_indices = set()
    for p in confirmed_points:
        try:
            index, confirm = int(p["index"]), int(p["confirm_index"])
            side = p["side"]
            if side not in ("HIGH", "LOW") or not (0 <= index < len(times)):
                raise ValueError("side/index")
            if (confirm != index + RIGHT_CONFIRMATION_BARS or confirm > as_of_index
                    or not p.get("confirmation_contiguous", False)
                    or int(p["event_time_ms"]) != times[index]
                    or int(p["confirm_time_ms"]) != times[confirm] + 300_000
                    or not math.isfinite(float(p["price"]))
                    or abs(float(p["price"]) - float(frame.iloc[index]["high" if side == "HIGH" else "low"]))
                       > 1e-12 * max(1.0, abs(float(p["price"])))):
                raise ValueError("not confirmed on source-time closed prefix")
            key = (index, side)
            if key in by_key:
                raise ValueError("duplicate source pivot")
            by_key[key] = p
            if p.get("ambiguous_same_candle", False):
                ambiguous_indices.add(index)
        except (KeyError, IndexError, ValueError, TypeError, OverflowError):
            reasons.append("UNPROVEN_PIVOT_PROVENANCE")
            return result
    for index in range(start, last + 1):
        if (index, "HIGH") in by_key and (index, "LOW") in by_key:
            ambiguous_indices.add(index)
    required = [(a["h1"], "HIGH"), (a["h2"], "HIGH"),
                (a["l1"], "LOW"), (a["l2"], "LOW")]
    if any(k not in by_key for k in required):
        reasons.append("MISSING_CONFIRMED_ANCHOR")
        return result
    if any(index in ambiguous_indices for index in range(start, last + 1)):
        result["status"] = "AMBIGUOUS"
        reasons.append("SAME_CANDLE_HIGH_LOW_ORDER_UNPROVEN")
        return result
    points = [p for p in by_key.values() if start <= p["index"] <= last]
    h1, h2, l1, l2 = [by_key[k] for k in required]
    upper = fit_anchor_trendline([h1, h2])
    lower = fit_anchor_trendline([l1, l2])
    if upper is None or lower is None:
        result["status"] = "INVALID"
        reasons.append("ANCHOR_FIT_FAILED")
        return result
    du, dl = upper["slope"], lower["slope"]
    family = "FALLING" if du < 0 and dl < 0 else "RISING" if du > 0 and dl > 0 else None
    result["family"] = family
    if family is None:
        reasons.append("NOT_A_WEDGE_SLOPE_FAMILY")
    width_start = calculate_price(upper, start) - calculate_price(lower, start)
    width_last = calculate_price(upper, last) - calculate_price(lower, last)
    result["geometry"] = {"upper_slope": du, "lower_slope": dl,
                          "width_start": width_start, "width_last_anchor": width_last,
                          "converging": width_last < width_start}
    if not (width_start > 0 and width_last > 0 and width_last < width_start):
        reasons.append("WIDTH_OR_CONVERGENCE_INVALID")
    supports, breaches = {}, []
    for side, line, first, second in (("HIGH", upper, a["h1"], a["h2"]),
                                      ("LOW", lower, a["l1"], a["l2"])):
        same = [p for p in points if p["side"] == side]
        matched = [p for p in same if abs(float(p["price"]) - calculate_price(line, p["index"]))
                   / max(abs(calculate_price(line, p["index"])), 1e-30) * 100
                   <= SUPPORT_TOLERANCE_PERCENT]
        supports[side] = {"indices": sorted(p["index"] for p in matched),
                          "additional": sum(p["index"] not in (first, second) for p in matched)}
        if supports[side]["additional"] == 0:
            result.setdefault("open_questions", []).append("NO_ADDITIONAL_LOCAL_" + side + "_SUPPORT")
        for p in same:
            bound = calculate_price(line, p["index"])
            depth = float(p["price"]) - bound if side == "HIGH" else bound - float(p["price"])
            if depth > 1e-12 * max(1.0, abs(bound)):
                breaches.append({"index": p["index"], "side": side, "depth": depth})
    result["support"] = supports
    result["envelope_breaches"] = breaches
    if breaches:
        reasons.append("LOCAL_PIVOT_OUTSIDE_ANCHORED_ENVELOPE")
    if family:
        strict_side, strict_line = ("upper", upper) if family == "FALLING" else ("lower", lower)
        first_strict = a["h1"] if family == "FALLING" else a["l1"]
        windows = {"A": (start, first_strict - 1), "B": (first_strict, last),
                   "E": (last + 1, as_of_index), "FULL": (start, as_of_index)}
        result["strict"] = {name: _scan_boundary(frame, strict_line, strict_side, s, e)
                            for name, (s, e) in windows.items()}
        b = result["strict"]["B"]
        if b["body_count"] or b["max_wick_run"] >= 2:
            reasons.append("STRICT_BOUNDARY_VIOLATED_WITHIN_ANCHORED_EXTENT")
    if reasons:
        result["status"] = "INVALID"
    elif result.get("open_questions"):
        result["status"] = "UNKNOWN"
    elif (result["strict"]["A"]["body_count"]
          or result["strict"]["E"]["body_count"]
          or any(zone["wick_count"] for zone in result["strict"].values() if not zone["empty"])):
        result["status"] = "UNKNOWN"
        reasons.append("UNRESOLVED_PRE_OR_POST_ANCHOR_BREACH_OR_UNCALIBRATED_WICKS")
    else:
        result["status"] = "VALID_RESEARCH_PAIR"
    return result
