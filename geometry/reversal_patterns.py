"""
geometry.reversal_patterns

Bullish reversal-candle recognizers used only as an exception to an
otherwise-counted body breach of the lower boundary in the Falling
Wedge flexible zone (see DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md,
Section 4).

Scope:
- Falling Wedge lower-boundary flexible zone only.
- Recognizes: Bullish Engulfing, Morning Star, Arc (rounding bottom).
- A future Rising Wedge mirror would need the bearish equivalents; not
  implemented here (explicit non-goal of the decision).

Does not:
- classify the overall pattern;
- compute Score/Quality;
- decide whether a breach counts as a violation (that is the caller's
  job; this module only answers "is a recognized reversal pattern
  present at/around this candle index").

All thresholds below are explicit, named, initial working defaults.
They are not calibrated against historical data yet and are expected
to be recalibrated later (see CR authority: this decision's own
"Restrictions"/"Unresolved" notes).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Named constants (no magic numbers) — initial working defaults, subject to
# later calibration against historical data / Paper Trader evidence.
# ---------------------------------------------------------------------------

# A candle body is "large" relative to its own high-low range at/above this
# ratio, and "small" at/below SMALL_BODY_RATIO. Values strictly between the
# two are neither large nor small for the purposes of Morning Star.
LARGE_BODY_RATIO = 0.5
SMALL_BODY_RATIO = 0.3

# Arc (rounding-bottom) recognition window: a run of consecutive local lows,
# length bounded to this inclusive range, as specified by the decision.
ARC_MIN_RUN = 4
ARC_MAX_RUN = 6

# An Arc must not contain a single step (candle-to-candle low change) larger
# than this multiple of ATR; a bigger single step reads as a sharp V-shaped
# reversal rather than a smooth rounding bottom.
ARC_MAX_SINGLE_STEP_ATR_MULTIPLIER = 2.0


def _row(candles, index):
    """Return the candle row at index, or None if unavailable."""

    if candles is None or index is None:
        return None

    try:
        if index < 0 or index >= len(candles):
            return None
        return candles.iloc[index]
    except Exception:
        return None


def _body(row):
    if row is None:
        return None
    try:
        return abs(float(row["close"]) - float(row["open"]))
    except Exception:
        return None


def _range(row):
    if row is None:
        return None
    try:
        return float(row["high"]) - float(row["low"])
    except Exception:
        return None


def _is_bearish(row):
    try:
        return float(row["close"]) < float(row["open"])
    except Exception:
        return False


def _is_bullish(row):
    try:
        return float(row["close"]) > float(row["open"])
    except Exception:
        return False


def _body_ratio(row):
    body = _body(row)
    candle_range = _range(row)
    if body is None or not candle_range:
        return None
    return body / candle_range


def is_bullish_engulfing(candles, index):
    """Previous candle bearish, current bullish, current body fully covers
    the previous body (open_current <= close_previous and
    close_current >= open_previous)."""

    current = _row(candles, index)
    previous = _row(candles, index - 1)

    if current is None or previous is None:
        return False

    if not (_is_bearish(previous) and _is_bullish(current)):
        return False

    try:
        return (
            float(current["open"]) <= float(previous["close"])
            and float(current["close"]) >= float(previous["open"])
        )
    except Exception:
        return False


def is_morning_star(candles, index):
    """Three candles ending at index: first bearish with a large body,
    second with a small body gapping down from the first, third bullish
    with a large body closing above the midpoint of the first candle's
    body."""

    first = _row(candles, index - 2)
    second = _row(candles, index - 1)
    third = _row(candles, index)

    if first is None or second is None or third is None:
        return False

    if not _is_bearish(first):
        return False

    first_ratio = _body_ratio(first)
    if first_ratio is None or first_ratio < LARGE_BODY_RATIO:
        return False

    second_ratio = _body_ratio(second)
    if second_ratio is None or second_ratio > SMALL_BODY_RATIO:
        return False

    try:
        first_body_low = min(float(first["open"]), float(first["close"]))
        gapped_down = max(float(second["open"]), float(second["close"])) < first_body_low
    except Exception:
        return False

    if not gapped_down:
        return False

    if not _is_bullish(third):
        return False

    third_ratio = _body_ratio(third)
    if third_ratio is None or third_ratio < LARGE_BODY_RATIO:
        return False

    try:
        first_body_midpoint = (float(first["open"]) + float(first["close"])) / 2.0
        return float(third["close"]) > first_body_midpoint
    except Exception:
        return False


def is_smooth_arc(candles, index, atr_value=None):
    """A run of ARC_MIN_RUN..ARC_MAX_RUN consecutive lows ending at index
    that declines, flattens, and turns up (at most one down-to-up turn),
    without a single-step change larger than
    ARC_MAX_SINGLE_STEP_ATR_MULTIPLIER * ATR (which would read as a sharp
    V-shaped reversal instead of a smooth rounding bottom)."""

    if candles is None or index is None:
        return False

    for run_length in range(ARC_MIN_RUN, ARC_MAX_RUN + 1):

        start = index - run_length + 1

        if start < 0:
            continue

        rows = [_row(candles, i) for i in range(start, index + 1)]

        if any(row is None for row in rows):
            continue

        try:
            lows = [float(row["low"]) for row in rows]
        except Exception:
            continue

        diffs = [lows[i + 1] - lows[i] for i in range(len(lows) - 1)]

        if not diffs:
            continue

        turned_up = False
        valid_shape = True

        for diff in diffs:

            if diff == 0:
                continue

            if diff < 0:
                if turned_up:
                    valid_shape = False
                    break
            else:
                turned_up = True

        if not valid_shape or not turned_up:
            continue

        if atr_value:
            max_step = max(abs(diff) for diff in diffs)
            if max_step > ARC_MAX_SINGLE_STEP_ATR_MULTIPLIER * atr_value:
                continue

        return True

    return False


def has_reversal_exception(candles, index, atr_value=None):
    """True if any recognized bullish reversal pattern excuses a lower-
    boundary body breach at this candle index."""

    if is_bullish_engulfing(candles, index):
        return True

    if is_morning_star(candles, index):
        return True

    if is_smooth_arc(candles, index, atr_value):
        return True

    return False
