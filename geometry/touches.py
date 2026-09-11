"""
geometry.touches

Анализ качества касаний
трендовых линий.

Отвечает только за геометрию
контакта цены с линией.

Не содержит логики:
- паттернов;
- сигналов;
- скоринга.

CR-SCANNER-GEOMETRY-002 (DOCUMENTS/CHANGE_REQUESTS/CR-SCANNER-GEOMETRY-002.md):
touch_tolerance / violation_tolerance are ATR(14)-normalized (reusing
confirmation.py:calculate_atr(), the same computation already used by
DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md — no separate
structure-span ATR window is introduced here), each Pivot point receives a
graduated distance/score instead of a binary touch/no-touch flag, and a
bounded number of outlier contacts per line (RANSAC-inlier-ratio-style) no
longer disqualifies that line. Upper and lower boundaries share this one
code path; there is no per-side branching. When ATR cannot be computed for
a point (no candles supplied, or insufficient warm-up data at that index),
that point falls back to the pre-CR-SCANNER-GEOMETRY-002 fixed-percentage
tolerance, preserving prior behavior for callers that do not supply
candles.
"""

from confirmation import calculate_atr


ATR_PERIOD = 14

# CR-SCANNER-GEOMETRY-002 resolved numeric defaults (2026-09-11, revised
# same day after live-data review) — starting values, explicitly subject to
# later calibration against historical data, not finalized.
#
# Revision note: the original proposal (0.10 / 0.25) was taken by analogy
# with DOCUMENTS/SCANNER_GEOMETRY_ATR_CONTAINMENT_DECISION.md, but that
# decision compares ATR against a candle's body inside the structure,
# whereas here ATR is compared directly against price (the same basis the
# old fixed 0.6%-of-price cutoff used) — a different comparison base and a
# different order of magnitude. Live-data review on 1-minute candles
# (GRVTUSDT, DOGEUSDT) showed 0.10/0.25 made touch_tolerance ~25x and
# violation_tolerance ~17x tighter than the old 0.6% cutoff, systematically
# collapsing touch counts. 4.0 / 10.0 keeps the same 2.5x touch:violation
# ratio while landing in the old cutoff's order of magnitude.
TOUCH_TOLERANCE_ATR_MULTIPLIER = 4.0
VIOLATION_TOLERANCE_ATR_MULTIPLIER = 10.0
OUTLIER_ALLOWANCE_PER_LINE = 1

# Fallback tolerance (fraction of predicted line price) used only when ATR
# is unavailable for a point. This is the pre-CR-SCANNER-GEOMETRY-002
# fixed cutoff, kept solely for backward compatibility with callers that do
# not supply candles.
LEGACY_TOUCH_TOLERANCE_PERCENT = 0.006


def calculate_line_error(
    line,
    points
):
    """
    Рассчитывает отклонение Pivot точек
    от трендовой линии.
    """

    if (
        line is None
        or not points
    ):
        return None


    errors = []


    for point in points:

        predicted = (
            line["slope"]
            *
            point["index"]
            +
            line["intercept"]
        )


        error = abs(
            point["price"]
            -
            predicted
        )


        errors.append(
            error
        )


    return {

        "mean_error":
            sum(errors) / len(errors),

        "max_error":
            max(errors),

        "errors":
            errors

    }


def _atr_series(
    candles,
    period=ATR_PERIOD
):
    if candles is None:
        return None

    try:
        return calculate_atr(
            candles,
            period=period
        )
    except Exception:
        return None


def _atr_value_at(
    atr_series,
    index
):
    if atr_series is None:
        return None

    try:
        value = atr_series.iloc[index]
    except Exception:
        return None

    if value != value:
        # NaN check without importing math/numpy — insufficient warm-up
        # data for ATR at this index.
        return None

    return float(value)


def count_touches(
    line,
    points,
    candles=None,
    touch_atr_multiplier=TOUCH_TOLERANCE_ATR_MULTIPLIER,
    violation_atr_multiplier=VIOLATION_TOLERANCE_ATR_MULTIPLIER,
    outlier_allowance=OUTLIER_ALLOWANCE_PER_LINE,
    legacy_tolerance_percent=LEGACY_TOUCH_TOLERANCE_PERCENT,
    atr_period=ATR_PERIOD
):
    """
    Graduated, ATR-normalized touch evaluation for one trendline.

    Shared by both boundaries — the caller passes the high-wick (upper) or
    low-wick (lower) line/points; there is no per-side branching here.

    For each point, distance = abs(point.price - predicted_line_price):

    - distance <= touch_tolerance:
        clean touch. Always counted. Graduated score
        max(0, 1 - distance / touch_tolerance).

    - touch_tolerance < distance <= violation_tolerance:
        outlier. Counted (score 0) only while this line's outlier budget
        (outlier_allowance) is not yet used; further outliers beyond the
        budget are excluded from the count. Analogous to a RANSAC inlier
        ratio: a single noisy wick does not disqualify an otherwise valid
        line.

    - distance > violation_tolerance:
        violation. Never counted toward touches. Diagnostic only — per
        CR-SCANNER-GEOMETRY-002's explicit non-goal, this does not by
        itself introduce any new hard rejection.

    Returns
    -------
    {
        "count": int,                 # touches counted (touch_tolerance
                                       # hits plus budget-tolerated outliers)
        "points": [ {index, price, predicted, distance, score,
                     touch_tolerance, violation_tolerance, classification,
                     counted}, ... ],
        "outlier_count": int,         # points landing in the outlier band
                                       # (tolerated or excluded)
        "violation_count": int,       # points beyond violation_tolerance
    }
    """

    if (
        line is None
        or not points
    ):
        return {
            "count": 0,
            "points": [],
            "outlier_count": 0,
            "violation_count": 0,
        }

    atr_series = _atr_series(
        candles,
        period=atr_period
    )

    details = []
    count = 0
    outlier_count = 0
    violation_count = 0

    for point in points:

        index = point["index"]

        predicted = (
            line["slope"]
            *
            index
            +
            line["intercept"]
        )

        distance = abs(
            point["price"]
            -
            predicted
        )

        atr_value = _atr_value_at(
            atr_series,
            index
        )

        if atr_value is not None:

            touch_tolerance = (
                touch_atr_multiplier
                *
                atr_value
            )

            violation_tolerance = (
                violation_atr_multiplier
                *
                atr_value
            )

        elif predicted > 0:

            # ATR unavailable for this point (no candles, or insufficient
            # warm-up data) — fall back to the legacy fixed-percentage
            # tolerance so callers that do not supply candles keep their
            # prior behavior.
            touch_tolerance = (
                legacy_tolerance_percent
                *
                predicted
            )

            violation_tolerance = touch_tolerance

        else:

            # Degenerate line value at this index and no ATR fallback
            # available either — mirrors the pre-CR-SCANNER-GEOMETRY-002
            # behavior of skipping such points entirely.
            details.append(
                {
                    "index": index,
                    "price": point["price"],
                    "predicted": predicted,
                    "distance": distance,
                    "score": 0.0,
                    "touch_tolerance": None,
                    "violation_tolerance": None,
                    "classification": "unclassifiable",
                    "counted": False,
                }
            )
            continue

        if touch_tolerance > 0:
            score = max(
                0.0,
                1.0 - (distance / touch_tolerance)
            )
        else:
            score = 0.0

        if distance <= touch_tolerance:

            classification = "touch"
            counted = True
            count += 1

        elif distance <= violation_tolerance:

            outlier_count += 1

            if outlier_count <= outlier_allowance:

                classification = "outlier_tolerated"
                counted = True
                count += 1

            else:

                classification = "outlier_excluded"
                counted = False

        else:

            classification = "violation"
            counted = False
            violation_count += 1

        details.append(
            {
                "index": index,
                "price": point["price"],
                "predicted": predicted,
                "distance": distance,
                "score": round(score, 6),
                "touch_tolerance": touch_tolerance,
                "violation_tolerance": violation_tolerance,
                "classification": classification,
                "counted": counted,
            }
        )

    return {
        "count": count,
        "points": details,
        "outlier_count": outlier_count,
        "violation_count": violation_count,
    }



def analyze_touches(
    upper_line,
    lower_line,
    highs,
    lows,
    candles=None
):
    """
    Полный анализ касаний
    верхней и нижней границы.

    Contract (preserved for existing consumers): upper_touches,
    lower_touches, total_touches, and valid keep their pre-existing
    meaning — a graduated per-point score and outlier/violation
    diagnostics are additive fields only (CR-SCANNER-GEOMETRY-002).
    """


    upper_result = count_touches(
        upper_line,
        highs,
        candles=candles
    )


    lower_result = count_touches(
        lower_line,
        lows,
        candles=candles
    )


    upper_touches = upper_result["count"]
    lower_touches = lower_result["count"]


    total = (
        upper_touches
        +
        lower_touches
    )


    return {

        "upper_touches":
            upper_touches,

        "lower_touches":
            lower_touches,

        "total_touches":
            total,

        "valid":
            (
                upper_touches >= 2
                and
                lower_touches >= 2
            ),

        # Additive (CR-SCANNER-GEOMETRY-002): per-point graduated
        # distance/score diagnostics and outlier/violation counts.
        # Consumers reading only the four keys above are unaffected.

        "upper_touch_points":
            upper_result["points"],

        "lower_touch_points":
            lower_result["points"],

        "upper_outlier_count":
            upper_result["outlier_count"],

        "lower_outlier_count":
            lower_result["outlier_count"],

        "upper_violation_count":
            upper_result["violation_count"],

        "lower_violation_count":
            lower_result["violation_count"],

    }
