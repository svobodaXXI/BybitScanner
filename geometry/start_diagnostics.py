"""G2b0 research-only comparison of historical START and frozen line anchors.

This module has no Scanner/Robot callers. It reports confirmed, bounded
pre-pattern pivot alternatives without choosing a new START or modifying lines.
"""

from math import isfinite
from numbers import Integral

from .pre_pattern import collect_impulse_terminal_evidence


def compare_start_anchor_evidence(
    candles,
    highs,
    lows,
    baseline_start_index,
    upper_anchor_index,
    lower_anchor_index,
    *,
    as_of_index,
    right,
    lookback=20,
    max_candidates=4,
):
    """Compare distinct anchor times with past-only pivot evidence.

    Indices are positions in the same source-timeframe frame. as_of_index
    must identify its last available CLOSED candle. This first observational
    slice searches no later than the earliest line anchor; the gap between
    unequal anchors is explicitly not evaluated.
    """
    result = {
        "status": "INVALID_INPUT",
        "reason": "invalid_start_anchor_evidence",
        "baseline_start": None,
        "upper_anchor": None,
        "lower_anchor": None,
        "window": None,
        "candidates": [],
        "coverage_limitations": [],
    }
    indexes = (
        baseline_start_index, upper_anchor_index, lower_anchor_index,
        as_of_index, right, lookback, max_candidates,
    )
    if any(isinstance(value, bool) or not isinstance(value, Integral)
           for value in indexes):
        return result
    if (min(baseline_start_index, upper_anchor_index, lower_anchor_index) < 0
            or baseline_start_index != min(upper_anchor_index, lower_anchor_index)
            or max(upper_anchor_index, lower_anchor_index) > as_of_index
            or right < 0 or lookback <= 0 or max_candidates <= 0):
        return result
    try:
        if candles is None or as_of_index >= len(candles):
            return result

        def anchor(index):
            # Never index rows after the explicit signal-time cutoff.
            time = float(candles.iloc[index]["time"])
            if not isfinite(time) or time < 0 or not time.is_integer():
                return None
            return {"index": int(index), "time_ms": int(time)}

        baseline = anchor(baseline_start_index)
        upper = anchor(upper_anchor_index)
        lower = anchor(lower_anchor_index)
        if any(item is None for item in (baseline, upper, lower)):
            return result
        distinct = {item["index"]: item["time_ms"]
                    for item in (baseline, upper, lower)}
        ordered_times = [distinct[index] for index in sorted(distinct)]
        if any(a >= b for a, b in zip(ordered_times, ordered_times[1:])):
            return result

        evidence = collect_impulse_terminal_evidence(
            candles, highs, lows, baseline_start_index,
            as_of_index=as_of_index, right=right,
            lookback=lookback, max_candidates=max_candidates,
        )
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return result
    if evidence["status"] == "INVALID_INPUT":
        return result

    limitations = []
    if upper_anchor_index != lower_anchor_index:
        limitations.append("BETWEEN_ANCHORS_NOT_EVALUATED")
    if evidence["window"]["left_truncated"]:
        limitations.append("LEFT_HISTORY_TRUNCATED")
    if evidence["candidates_truncated"]:
        limitations.append("CANDIDATE_SHORTLIST_TRUNCATED")

    candidates = []
    for candidate in evidence["candidates"]:
        # Do not turn an observed swing into a final START or subtype.
        candidates.append({
            **candidate,
            "bars_before_baseline": int(
                baseline_start_index - candidate["index"]
            ),
            "relative_to_baseline": (
                "EARLIER" if candidate["index"] < baseline_start_index
                else "AT_BASELINE"
            ),
        })
    result.update(
        status=evidence["status"],
        reason=evidence["reason"],
        baseline_start=baseline,
        upper_anchor=upper,
        lower_anchor=lower,
        window=evidence["window"],
        candidates=candidates,
        coverage_limitations=limitations,
    )
    return result
