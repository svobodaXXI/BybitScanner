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

# Shared observation-only primitives for fully CLOSED Mirror M1/M5 candles.
# Existing Falling-Wedge exceptions above retain their separate semantics.
# A recognition result does not authorize entry; each pattern still owns its
# next-close confirmation, stop geometry and Robot admission.
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence


def directional_engulfing(previous: Mapping[str, Any], current: Mapping[str, Any],
                          direction: str) -> bool:
    """Exactly the pre-existing MIRROR Engulfing parity, both directions.

    The caller owns candle-close/timeframe gating. The SHORT transformation
    intentionally mirrors the historic price-negation algorithm; thresholds
    and classification are not recalibrated by this extraction.
    """
    if direction not in ("LONG", "SHORT"):
        return False
    import pandas as pd

    def view(row: Mapping[str, Any]) -> dict[str, object]:
        if direction == "LONG":
            return {k: row[k] for k in ("open", "high", "low", "close")}
        return {
            "open": -row["open"], "high": -row["low"],
            "low": -row["high"], "close": -row["close"],
        }

    return bool(is_bullish_engulfing(pd.DataFrame([view(previous), view(current)]), 1))


def closed_candle_numbers(row: Mapping[str, Any]):
    """Positive finite OHLC of an explicitly closed, physically valid candle."""
    if row.get("closed") is not True:
        return None
    try:
        o, h, lo, c = (Decimal(str(row[k])) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    if (not all(x.is_finite() and x > 0 for x in (o, h, lo, c))
            or lo > min(o, c) or h < max(o, c) or h <= lo):
        return None
    return o, h, lo, c


def is_nison_lower_wick(
    candle: Mapping[str, Any], direction: str,
    preceding: Sequence[Mapping[str, Any]], *,
    upper_to_body: object,
) -> bool:
    """Exact existing MIRROR Hammer LONG / Hanging-Man SHORT recognition.

    Two prior consecutive close trends and the upper-wick tolerance belong to
    MIRROR policy; another caller must provide its own policy input.
    Doji is deliberately NOT a trade trigger.
    """
    if direction not in ("LONG", "SHORT") or len(preceding) < 2:
        return False
    values = closed_candle_numbers(candle)
    before = [closed_candle_numbers(x) for x in preceding[-2:]]
    if values is None or any(x is None for x in before):
        return False
    older, newer = before
    try:
        duration = int(candle["close_time_ms"]) - int(candle["open_time_ms"])
        if (duration <= 0
                or any(int(row["close_time_ms"]) - int(row["open_time_ms"]) != duration
                       for row in preceding[-2:])
                or int(preceding[-2]["close_time_ms"]) != int(preceding[-1]["open_time_ms"])
                or int(preceding[-1]["close_time_ms"]) != int(candle["open_time_ms"])):
            return False
    except (KeyError, TypeError, ValueError):
        return False
    if direction == "LONG" and not older[3] > newer[3]:
        return False
    if direction == "SHORT" and not older[3] < newer[3]:
        return False
    o, h, lo, c = values
    body = abs(c - o)
    if body == 0:
        return False
    lower_wick = min(o, c) - lo
    upper_wick = h - max(o, c)
    return (lower_wick >= 2 * body
            and upper_wick <= Decimal(upper_to_body) * body)


def confirms_next_body_close(
    formation: Sequence[Mapping[str, Any]],
    following: Mapping[str, Any], direction: str, step: int,
) -> bool:
    """Existing MIRROR next full candle closes past the REAL BODY, not wick.

    This shared check returns evidence, not admission or an order signal.
    """
    candles = [*formation, following]
    values = [closed_candle_numbers(x) for x in candles]
    if direction not in ("LONG", "SHORT") or not formation or any(x is None for x in values):
        return False
    try:
        if any(int(right["open_time_ms"]) != int(left["close_time_ms"])
               or int(left["close_time_ms"]) - int(left["open_time_ms"]) != step
               for left, right in zip(candles, candles[1:])):
            return False
        if int(following["close_time_ms"]) - int(following["open_time_ms"]) != step:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    real_body_top = max(max(o, c) for o, _, _, c in values[:-1])
    real_body_bottom = min(min(o, c) for o, _, _, c in values[:-1])
    return (values[-1][3] > real_body_top if direction == "LONG"
            else values[-1][3] < real_body_bottom)


def observe_closed_engulfing(
    previous: Mapping[str, Any], current: Mapping[str, Any], direction: str,
) -> dict[str, object] | None:
    """Observation-only engulfing on TWO adjacent, finished candles.

    This stricter public observation API does not replace MIRROR's historical
    directional_engulfing or any strategy's confirmation/admission policy.
    It rejects incomplete/invalid OHLC, missing timestamps and time gaps.
    """
    if (direction not in ("LONG", "SHORT")
            or not isinstance(previous, Mapping)
            or not isinstance(current, Mapping)):
        return None
    before = closed_candle_numbers(previous)
    now = closed_candle_numbers(current)
    if before is None or now is None:
        return None
    try:
        # Exact candle boundaries must be integer milliseconds: int() would
        # silently truncate fractional floats and accept booleans/strings.
        timestamps = (
            previous["open_time_ms"], previous["close_time_ms"],
            current["open_time_ms"], current["close_time_ms"],
        )
        if any(type(value) is not int for value in timestamps):
            return None
        start_before, end_before, start_now, end_now = timestamps
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    step = end_before - start_before
    if step <= 0 or start_before < 0 or end_before != start_now or end_now - start_now != step:
        return None

    # Keep the validated Decimal prices exact. A Decimal -> float conversion
    # can round near-equal body boundaries together or overflow to infinity,
    # creating a false engulfing observation. This new API is observational;
    # the legacy MIRROR directional_engulfing policy remains unchanged.
    prior_open, _, _, prior_close = before
    open_now, _, _, close_now = now
    if direction == "LONG":
        engulfed = (prior_close < prior_open and close_now > open_now
                    and open_now <= prior_close and close_now >= prior_open)
    else:
        engulfed = (prior_close > prior_open and close_now < open_now
                    and open_now >= prior_close and close_now <= prior_open)
    if not engulfed:
        return None
    return {
        "formation_type": "ENGULFING",
        "direction": direction,
        "formation_candle_ids": (start_before, start_now),
        "confirmation_close_time": None,
        "confirmed": False,
        "evidence": {"formation_close_time_ms": end_now},
    }


# Nison-style classical candle formations (observation-only).
# Nison defines qualitative relationships; ratios below are deliberately
# transparent ENGINEERING thresholds, not numbers attributed to the author.
# Classical star/piercing/cloud gaps remain mandatory, including on 24/7 crypto.
# No use by Scanner, MIRROR, Robot or PAPER admission until separately approved.
_NISON_SMALL_BODY = Decimal("0.30")
_NISON_LARGE_BODY = Decimal("0.50")
_NISON_DOJI_BODY = Decimal("0.10")
_NISON_SHORT_WICK_TO_BODY = Decimal("0.25")
# "Near the high/low" is qualitative in Nison: 15% is an explicit
# conservative engineering approximation, not a book-specified constant.
_NISON_END_WICK_TO_RANGE = Decimal("0.15")


def _nison_closed_window(rows: Sequence[Mapping[str, Any]]):
    """Validate consecutive closed OHLC and exact equal-duration time intervals."""
    if not rows or any(not isinstance(row, Mapping) for row in rows):
        return None
    try:
        prices = tuple(closed_candle_numbers(row) for row in rows)
        if any(price is None for price in prices):
            return None
        spans = tuple((row["open_time_ms"], row["close_time_ms"]) for row in rows)
        if any(type(start) is not int or type(end) is not int for start, end in spans):
            return None
        step = spans[0][1] - spans[0][0]
        if step <= 0 or spans[0][0] < 0:
            return None
        if any(end - start != step or (i and start != spans[i - 1][1])
               for i, (start, end) in enumerate(spans)):
            return None
        return prices
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        return None


def observe_nison_reversals(
    candles: Sequence[Mapping[str, Any]], *, trend_lookback: int = 3,
) -> tuple[dict[str, object], ...]:
    """Recognize classical Japanese reversal candle formations at the latest close.

    Looks only at contiguous, fully CLOSED candles. Each 1/2/3-bar pattern must
    have an independently established prior UP/DOWN close trend. A strictly
    monotonic run of 3 preceding closes is a conservative *implementation
    proxy*, NOT a universal Nison rule. It can be relaxed only after research.
    Classic gaps are not silently dropped just because crypto trades 24/7.

    Returns observations, not entry signals: even a completed three-candle
    pattern is NOT strategy-confirmed; confirmation/TF/admission belong to the
    caller, so every result explicitly has confirmed=False.
    """
    if type(trend_lookback) is not int or not 3 <= trend_lookback <= 8:
        return ()
    if not isinstance(candles, Sequence) or len(candles) < trend_lookback + 1:
        return ()

    observations: list[dict[str, object]] = []
    for count in (1, 2, 3):
        if len(candles) < trend_lookback + count:
            continue
        rows = candles[-(trend_lookback + count):]
        prices = _nison_closed_window(rows)
        if prices is None:
            continue
        closes = tuple(row[3] for row in prices[:trend_lookback])
        if all(b > a for a, b in zip(closes, closes[1:])):
            trend = "UP"
        elif all(b < a for a, b in zip(closes, closes[1:])):
            trend = "DOWN"
        else:
            continue
        formation = prices[-count:]
        opens = tuple(row["open_time_ms"] for row in rows[-count:])
        closed_at = rows[-1]["close_time_ms"]

        def record(name: str, direction: str) -> None:
            observations.append({
                "formation_type": name, "direction": direction,
                "formation_candle_ids": opens,
                "confirmation_close_time": None, "confirmed": False,
                "evidence": {
                    "prior_trend": trend, "formation_close_time_ms": closed_at,
                    "classical_gap_required": name in (
                        "PIERCING", "DARK_CLOUD_COVER", "MORNING_STAR",
                        "MORNING_DOJI_STAR", "EVENING_STAR", "EVENING_DOJI_STAR",
                    ),
                },
            })

        def body(x):
            return abs(x[3] - x[0])

        def ratio(x):
            return body(x) / (x[1] - x[2])

        def bullish(x):
            return x[3] > x[0]

        def bearish(x):
            return x[3] < x[0]

        if count == 1:
            x = formation[0]
            if ratio(x) <= _NISON_DOJI_BODY:
                record("DOJI", "NEUTRAL")  # Indecision, never directional entry.
            # A near-zero real body is a DOJI, not also a directional
            # Hammer/Hanging-Man or inverted-wick signal.
            if ratio(x) <= _NISON_DOJI_BODY or ratio(x) > _NISON_SMALL_BODY:
                continue
            lower = min(x[0], x[3]) - x[2]
            upper = x[1] - max(x[0], x[3])
            if lower >= 2 * body(x) and upper <= _NISON_SHORT_WICK_TO_BODY * body(x):
                record("HAMMER" if trend == "DOWN" else "HANGING_MAN",
                       "LONG" if trend == "DOWN" else "SHORT")
            elif upper >= 2 * body(x) and lower <= _NISON_SHORT_WICK_TO_BODY * body(x):
                record("INVERTED_HAMMER" if trend == "DOWN" else "SHOOTING_STAR",
                       "LONG" if trend == "DOWN" else "SHORT")

        elif count == 2:
            first, second = formation
            direction = "LONG" if trend == "DOWN" else "SHORT"
            if ((direction == "LONG" and bearish(first) and bullish(second)
                 and second[0] <= first[3] and second[3] >= first[0])
                or (direction == "SHORT" and bullish(first) and bearish(second)
                    and second[0] >= first[3] and second[3] <= first[0])):
                record("ENGULFING", direction)

            if ratio(first) >= _NISON_LARGE_BODY and ratio(second) <= _NISON_SMALL_BODY:
                lower_body = min(first[0], first[3])
                upper_body = max(first[0], first[3])
                inside = (lower_body <= min(second[0], second[3])
                          and max(second[0], second[3]) <= upper_body)
                opposite = ((direction == "LONG" and bearish(first) and bullish(second))
                            or (direction == "SHORT" and bullish(first) and bearish(second)))
                if inside and ((ratio(second) <= _NISON_DOJI_BODY) or opposite):
                    record("HARAMI_CROSS" if ratio(second) <= _NISON_DOJI_BODY else "HARAMI",
                           direction)

            midpoint = (first[0] + first[3]) / 2
            if ratio(first) >= _NISON_LARGE_BODY:
                if (trend == "DOWN" and bearish(first) and bullish(second)
                        and second[0] < first[2] and midpoint < second[3] < first[0]):
                    record("PIERCING", "LONG")
                elif (trend == "UP" and bullish(first) and bearish(second)
                      and second[0] > first[1] and first[0] < second[3] < midpoint):
                    record("DARK_CLOUD_COVER", "SHORT")

        else:
            first, star, last = formation
            # Nison: Three Advancing White Soldiers / Three Black Crows.
            # They have three sizeable same-direction real bodies, each of
            # the latter two OPENING INSIDE the preceding body and closing
            # progressively nearer the session high/low. Unlike the stars,
            # no gap is required. Separate prior-trend context is mandatory.
            def near_close_end(x, side):
                wick = x[1] - x[3] if side == "LONG" else x[3] - x[2]
                return wick <= _NISON_END_WICK_TO_RANGE * (x[1] - x[2])

            if (trend == "DOWN"
                    and all(bullish(x) and ratio(x) >= _NISON_LARGE_BODY
                            and near_close_end(x, "LONG") for x in formation)
                    and all(previous[0] <= following[0] <= previous[3]
                            and following[3] > previous[3]
                            for previous, following in zip(formation, formation[1:]))):
                record("THREE_WHITE_SOLDIERS", "LONG")
            elif (trend == "UP"
                  and all(bearish(x) and ratio(x) >= _NISON_LARGE_BODY
                          and near_close_end(x, "SHORT") for x in formation)
                  and all(previous[3] <= following[0] <= previous[0]
                          and following[3] < previous[3]
                          for previous, following in zip(formation, formation[1:]))):
                record("THREE_BLACK_CROWS", "SHORT")

            if (ratio(first) < _NISON_LARGE_BODY
                    or ratio(star) > _NISON_SMALL_BODY
                    or ratio(last) < _NISON_LARGE_BODY):
                continue
            midpoint = (first[0] + first[3]) / 2
            is_doji_star = ratio(star) <= _NISON_DOJI_BODY
            if (trend == "DOWN" and bearish(first)
                    and max(star[0], star[3]) < min(first[0], first[3])
                    and bullish(last) and last[3] > midpoint):
                record("MORNING_DOJI_STAR" if is_doji_star else "MORNING_STAR", "LONG")
            elif (trend == "UP" and bullish(first)
                  and min(star[0], star[3]) > max(first[0], first[3])
                  and bearish(last) and last[3] < midpoint):
                record("EVENING_DOJI_STAR" if is_doji_star else "EVENING_STAR", "SHORT")

    return tuple(observations)
