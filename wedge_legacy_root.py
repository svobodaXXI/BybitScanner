import numpy as np


MODE = "sniper"

MIN_SCORE = 75


def analyze_wedge(highs, lows):

    if len(highs) < 3 or len(lows) < 3:
        return None


    high_x = np.array(
        [p["index"] for p in highs],
        dtype=float
    )

    high_y = np.array(
        [p["price"] for p in highs],
        dtype=float
    )

    low_x = np.array(
        [p["index"] for p in lows],
        dtype=float
    )

    low_y = np.array(
        [p["price"] for p in lows],
        dtype=float
    )


    try:

        high_line = np.polyfit(
            high_x,
            high_y,
            1
        )

        low_line = np.polyfit(
            low_x,
            low_y,
            1
        )

    except Exception:

        return None


    if (
        high_line is None
        or low_line is None
    ):
        return None


    high_slope = high_line[0]
    low_slope = low_line[0]

    high_intercept = high_line[1]
    low_intercept = low_line[1]


    values = [
        high_slope,
        low_slope,
        high_intercept,
        low_intercept
    ]


    if not all(
        np.isfinite(v)
        for v in values
    ):
        return None



    start = max(
        high_y[0],
        low_y[0]
    ) - min(
        high_y[0],
        low_y[0]
    )


    end = max(
        high_y[-1],
        low_y[-1]
    ) - min(
        high_y[-1],
        low_y[-1]
    )


    if start > 0:

        compression = (
            1 - end / start
        ) * 100

    else:

        compression = 0



    score_breakdown = {

        "structure": 0,
        "touches": 0,
        "compression": 0,
        "trend_quality": 0,
        "bonus": 0

    }



    if len(highs) >= 5:
        score_breakdown["touches"] += 10

    elif len(highs) >= 4:
        score_breakdown["touches"] += 8

    else:
        score_breakdown["touches"] += 6



    if len(lows) >= 5:
        score_breakdown["touches"] += 10

    elif len(lows) >= 4:
        score_breakdown["touches"] += 8

    else:
        score_breakdown["touches"] += 6



    if compression > 30:

        score_breakdown["compression"] = 25

    elif compression > 15:

        score_breakdown["compression"] = 18

    elif compression > 0:

        score_breakdown["compression"] = 10



    slope_difference = abs(
        high_slope - low_slope
    )


    if slope_difference > 3:

        score_breakdown["trend_quality"] = 15

    elif slope_difference > 1:

        score_breakdown["trend_quality"] = 10

    elif slope_difference > 0:

        score_breakdown["trend_quality"] = 5



    pattern = "No wedge"

    reason = (
        "Trendlines do not form wedge structure"
    )


    if (
        high_slope < 0
        and low_slope < 0
        and low_slope > high_slope
    ):

        pattern = "Falling Wedge"

        reason = (
            "Descending trendlines with converging structure"
        )

        score_breakdown["structure"] = 30



    elif (
        high_slope > 0
        and low_slope > 0
        and low_slope > high_slope
    ):

        pattern = "Rising Wedge"

        reason = (
            "Ascending trendlines with converging structure"
        )

        score_breakdown["structure"] = 30



    elif (
        high_slope < 0
        and low_slope > 0
    ):

        pattern = "Triangle Compression"

        reason = (
            "Opposing trendlines creating compression"
        )

        score_breakdown["structure"] = 15



    total_score = sum(
        score_breakdown.values()
    )


    return {

        "pattern": pattern,

        "reason": reason,

        "score": min(
            round(total_score),
            100
        ),

        "score_breakdown":
            score_breakdown,

        "high_slope":
            round(float(high_slope), 4),

        "high_intercept":
            round(float(high_intercept), 4),

        "low_slope":
            round(float(low_slope), 4),

        "low_intercept":
            round(float(low_intercept), 4),

        "compression":
            round(float(compression), 1),

        "high_touches":
            len(highs),

        "low_touches":
            len(lows)

    }