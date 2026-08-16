"""
geometry.envelope_metrics

Extremum Envelope Metrics.

Оценивает, насколько upper / lower
границы геометрии соответствуют
внешней оболочке Pivot-экстремумов.

Дополнительно собирает reference-anchor
метрики:

Falling Wedge hypothesis:
- последний Pivot High перед
  минимальным Pivot Low.

Rising Wedge hypothesis:
- последний Pivot Low перед
  максимальным Pivot High.

Модуль только собирает диагностику.

Не отвечает за:
- Pattern Classification;
- Arc / Late Excursion recognition;
- Validation Gate;
- Geometry Ranking;
- trading Score;
- signals.
"""


from .candidate import DEFAULT_TOLERANCE_PERCENT


def line_value(
    line,
    index
):
    if line is None:
        return None

    slope = line.get(
        "slope"
    )

    intercept = line.get(
        "intercept"
    )

    if (
        slope is None
        or intercept is None
    ):
        return None

    return (
        float(slope)
        * float(index)
        + float(intercept)
    )


def deviation_percent(
    actual,
    predicted
):
    if (
        actual is None
        or predicted is None
        or predicted == 0
    ):
        return None

    return (
        abs(
            float(actual)
            - float(predicted)
        )
        / abs(float(predicted))
        * 100.0
    )


def outside_percent(
    actual,
    predicted,
    side
):
    if (
        actual is None
        or predicted is None
        or predicted == 0
    ):
        return None

    if side == "upper":

        delta = (
            float(actual)
            - float(predicted)
        )

    elif side == "lower":

        delta = (
            float(predicted)
            - float(actual)
        )

    else:

        return None

    return (
        delta
        / abs(float(predicted))
        * 100.0
    )


def evaluate_boundary(
    line,
    points,
    side,
    start_index,
    current_index,
    tolerance_percent=DEFAULT_TOLERANCE_PERCENT
):
    if (
        line is None
        or not points
        or start_index is None
        or current_index is None
    ):
        return None

    evaluated = []
    support_indices = []
    outside_indices = []
    outside_values = []

    for point in points:

        if not isinstance(
            point,
            dict
        ):
            continue

        index = point.get(
            "index"
        )

        price = point.get(
            "price"
        )

        if (
            index is None
            or price is None
        ):
            continue

        if (
            index < start_index
            or index > current_index
        ):
            continue

        predicted = line_value(
            line,
            index
        )

        if predicted is None:
            continue

        error = deviation_percent(
            price,
            predicted
        )

        directed_outside = outside_percent(
            price,
            predicted,
            side
        )

        if (
            error is None
            or directed_outside is None
        ):
            continue

        evaluated.append(
            index
        )

        if (
            error
            <= tolerance_percent
        ):
            support_indices.append(
                index
            )

        if (
            directed_outside
            > tolerance_percent
        ):
            outside_indices.append(
                index
            )

            outside_values.append(
                directed_outside
            )

    support_count = len(
        support_indices
    )

    outside_count = len(
        outside_indices
    )

    evaluated_count = len(
        evaluated
    )

    if support_count >= 2:

        support_span = (
            max(support_indices)
            - min(support_indices)
        )

    else:

        support_span = 0

    support_ratio = (
        support_count
        / evaluated_count
        if evaluated_count
        else 0.0
    )

    outside_ratio = (
        outside_count
        / evaluated_count
        if evaluated_count
        else 0.0
    )

    max_outside_percent = (
        max(outside_values)
        if outside_values
        else 0.0
    )

    return {
        "evaluated_count":
            evaluated_count,

        "support_count":
            support_count,

        "support_ratio":
            support_ratio,

        "support_span":
            support_span,

        "outside_count":
            outside_count,

        "outside_ratio":
            outside_ratio,

        "max_outside_percent":
            max_outside_percent,

        "support_indices":
            support_indices,

        "outside_indices":
            outside_indices
    }


def find_minimum_low(
    lows,
    start_index,
    current_index
):
    candidates = []

    for point in lows or []:

        if not isinstance(
            point,
            dict
        ):
            continue

        index = point.get(
            "index"
        )

        price = point.get(
            "price"
        )

        if (
            index is None
            or price is None
        ):
            continue

        if (
            index < start_index
            or index > current_index
        ):
            continue

        candidates.append(
            point
        )

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda point: point["price"]
    )


def find_maximum_high(
    highs,
    start_index,
    current_index
):
    candidates = []

    for point in highs or []:

        if not isinstance(
            point,
            dict
        ):
            continue

        index = point.get(
            "index"
        )

        price = point.get(
            "price"
        )

        if (
            index is None
            or price is None
        ):
            continue

        if (
            index < start_index
            or index > current_index
        ):
            continue

        candidates.append(
            point
        )

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda point: point["price"]
    )


def find_last_point_before(
    points,
    target_index,
    start_index
):
    candidates = []

    for point in points or []:

        if not isinstance(
            point,
            dict
        ):
            continue

        index = point.get(
            "index"
        )

        if index is None:
            continue

        if (
            index < start_index
            or index >= target_index
        ):
            continue

        candidates.append(
            point
        )

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda point: point["index"]
    )


def calculate_reference_anchor_metrics(
    upper_line,
    lower_line,
    highs,
    lows,
    common_start,
    current_index,
    tolerance_percent
):
    """
    Диагностические reference-anchor метрики.

    Falling hypothesis:
    последний High перед минимальным Low.

    Rising hypothesis:
    последний Low перед максимальным High.
    """

    minimum_low = find_minimum_low(
        lows,
        common_start,
        current_index
    )

    maximum_high = find_maximum_high(
        highs,
        common_start,
        current_index
    )

    falling_reference_high = None
    rising_reference_low = None

    if minimum_low is not None:

        falling_reference_high = (
            find_last_point_before(
                highs,
                minimum_low["index"],
                common_start
            )
        )

    if maximum_high is not None:

        rising_reference_low = (
            find_last_point_before(
                lows,
                maximum_high["index"],
                common_start
            )
        )

    falling_metrics = {
        "minimum_low_index":
            (
                minimum_low.get("index")
                if minimum_low
                else None
            ),

        "reference_high_index":
            (
                falling_reference_high.get(
                    "index"
                )
                if falling_reference_high
                else None
            ),

        "upper_anchor_distance":
            None,

        "upper_reference_error_percent":
            None,

        "upper_reference_match":
            False
    }

    if falling_reference_high is not None:

        reference_index = (
            falling_reference_high[
                "index"
            ]
        )

        reference_price = (
            falling_reference_high[
                "price"
            ]
        )

        predicted = line_value(
            upper_line,
            reference_index
        )

        error = deviation_percent(
            reference_price,
            predicted
        )

        anchor_index = upper_line.get(
            "anchor_index"
        )

        if anchor_index is not None:

            falling_metrics[
                "upper_anchor_distance"
            ] = abs(
                anchor_index
                - reference_index
            )

        falling_metrics[
            "upper_reference_error_percent"
        ] = error

        falling_metrics[
            "upper_reference_match"
        ] = (
            error is not None
            and error
            <= tolerance_percent
        )

    rising_metrics = {
        "maximum_high_index":
            (
                maximum_high.get("index")
                if maximum_high
                else None
            ),

        "reference_low_index":
            (
                rising_reference_low.get(
                    "index"
                )
                if rising_reference_low
                else None
            ),

        "lower_anchor_distance":
            None,

        "lower_reference_error_percent":
            None,

        "lower_reference_match":
            False
    }

    if rising_reference_low is not None:

        reference_index = (
            rising_reference_low[
                "index"
            ]
        )

        reference_price = (
            rising_reference_low[
                "price"
            ]
        )

        predicted = line_value(
            lower_line,
            reference_index
        )

        error = deviation_percent(
            reference_price,
            predicted
        )

        anchor_index = lower_line.get(
            "anchor_index"
        )

        if anchor_index is not None:

            rising_metrics[
                "lower_anchor_distance"
            ] = abs(
                anchor_index
                - reference_index
            )

        rising_metrics[
            "lower_reference_error_percent"
        ] = error

        rising_metrics[
            "lower_reference_match"
        ] = (
            error is not None
            and error
            <= tolerance_percent
        )

    return {
        "falling":
            falling_metrics,

        "rising":
            rising_metrics
    }


def evaluate_candle_containment(
    upper_line,
    lower_line,
    candles,
    start_index,
    current_index,
    tolerance_percent=0.15
):
    """
    ????????? ???????? ????? ???????????? envelope ?????.

    Pivot envelope ? candle containment ????????
    ???????????? ?????????.

    ??????? ???????:
        high ?? ?????? ??????????? ?????????? ???? upper_line.

    ?????? ???????:
        low ?? ?????? ??????????? ?????????? ???? lower_line.
    """

    if (
        candles is None
        or upper_line is None
        or lower_line is None
        or start_index is None
        or current_index is None
    ):
        return None

    try:
        candle_count = len(candles)
    except Exception:
        return None

    if candle_count <= 0:
        return None

    start = max(
        0,
        int(start_index)
    )

    end = min(
        int(current_index),
        candle_count - 1
    )

    if end < start:
        return None

    evaluated_indices = []

    upper_outside_indices = []
    lower_outside_indices = []

    upper_outside_values = []
    lower_outside_values = []

    fully_below_lower_indices = []
    fully_above_upper_indices = []

    for index in range(
        start,
        end + 1
    ):

        try:
            row = candles.iloc[index]

            high = float(
                row["high"]
            )

            low = float(
                row["low"]
            )

        except Exception:
            continue

        upper_value = line_value(
            upper_line,
            index
        )

        lower_value = line_value(
            lower_line,
            index
        )

        if (
            upper_value is None
            or lower_value is None
        ):
            continue

        evaluated_indices.append(
            index
        )

        upper_outside = outside_percent(
            high,
            upper_value,
            "upper"
        )

        lower_outside = outside_percent(
            low,
            lower_value,
            "lower"
        )

        if (
            upper_outside is not None
            and upper_outside
            > tolerance_percent
        ):
            upper_outside_indices.append(
                index
            )

            upper_outside_values.append(
                upper_outside
            )

        if (
            lower_outside is not None
            and lower_outside
            > tolerance_percent
        ):
            lower_outside_indices.append(
                index
            )

            lower_outside_values.append(
                lower_outside
            )

        # ??? ????? ????????? ???? ?????? ???????.
        high_below_lower = outside_percent(
            high,
            lower_value,
            "lower"
        )

        if (
            high_below_lower is not None
            and high_below_lower
            > tolerance_percent
        ):
            fully_below_lower_indices.append(
                index
            )

        # ??? ????? ????????? ???? ??????? ???????.
        low_above_upper = outside_percent(
            low,
            upper_value,
            "upper"
        )

        if (
            low_above_upper is not None
            and low_above_upper
            > tolerance_percent
        ):
            fully_above_upper_indices.append(
                index
            )

    evaluated_count = len(
        evaluated_indices
    )

    outside_union = sorted(
        set(
            upper_outside_indices
            +
            lower_outside_indices
        )
    )

    severe_union = sorted(
        set(
            fully_below_lower_indices
            +
            fully_above_upper_indices
        )
    )

    midpoint = start + ((end - start) // 2)

    upper_early_indices = [
        index
        for index in upper_outside_indices
        if index <= midpoint
    ]

    lower_early_indices = [
        index
        for index in lower_outside_indices
        if index <= midpoint
    ]

    upper_late_indices = [
        index
        for index in upper_outside_indices
        if index > midpoint
    ]

    lower_late_indices = [
        index
        for index in lower_outside_indices
        if index > midpoint
    ]

    def _max_consecutive_run(indices):
        if not indices:
            return 0

        ordered = sorted(set(indices))
        best = 1
        current = 1

        for previous, current_index in zip(
            ordered,
            ordered[1:]
        ):
            if current_index == previous + 1:
                current += 1
                best = max(best, current)
            else:
                current = 1

        return best

    return {
        "tolerance_percent":
            tolerance_percent,

        "evaluated_count":
            evaluated_count,

        "outside_count":
            len(outside_union),

        "outside_ratio":
            (
                len(outside_union)
                / evaluated_count
                if evaluated_count
                else 0.0
            ),

        "outside_indices":
            outside_union,

        "upper_outside_count":
            len(upper_outside_indices),

        "upper_outside_indices":
            upper_outside_indices,

        "upper_max_outside_percent":
            (
                max(upper_outside_values)
                if upper_outside_values
                else 0.0
            ),

        "lower_outside_count":
            len(lower_outside_indices),

        "lower_outside_indices":
            lower_outside_indices,

        "lower_max_outside_percent":
            (
                max(lower_outside_values)
                if lower_outside_values
                else 0.0
            ),

        "fully_below_lower_count":
            len(fully_below_lower_indices),

        "fully_below_lower_indices":
            fully_below_lower_indices,

        "fully_above_upper_count":
            len(fully_above_upper_indices),

        "fully_above_upper_indices":
            fully_above_upper_indices,

        "severe_outside_count":
            len(severe_union),

        "severe_outside_indices":
            severe_union,

        "severe_outside_ratio":
            (
                len(severe_union)
                / evaluated_count
                if evaluated_count
                else 0.0
            ),

        "midpoint_index":
            midpoint,

        "upper_early_outside_count":
            len(upper_early_indices),

        "lower_early_outside_count":
            len(lower_early_indices),

        "upper_early_max_run":
            _max_consecutive_run(
                upper_early_indices
            ),

        "lower_early_max_run":
            _max_consecutive_run(
                lower_early_indices
            ),

        "upper_late_max_run":
            _max_consecutive_run(
                upper_late_indices
            ),

        "lower_late_max_run":
            _max_consecutive_run(
                lower_late_indices
            )
    }


def calculate_envelope_metrics(
    upper_candidate,
    lower_candidate,
    highs,
    lows,
    current_index,
    tolerance_percent=DEFAULT_TOLERANCE_PERCENT,
    candles=None
):
    if (
        upper_candidate is None
        or lower_candidate is None
        or current_index is None
    ):
        return None

    upper_line = upper_candidate.get(
        "line"
    )

    lower_line = lower_candidate.get(
        "line"
    )

    if (
        upper_line is None
        or lower_line is None
    ):
        return None

    upper_anchor = upper_line.get(
        "anchor_index"
    )

    lower_anchor = lower_line.get(
        "anchor_index"
    )

    if (
        upper_anchor is None
        or lower_anchor is None
    ):
        return None

    common_start = max(
        upper_anchor,
        lower_anchor
    )

    if current_index <= common_start:
        return None

    upper = evaluate_boundary(
        upper_line,
        highs,
        "upper",
        common_start,
        current_index,
        tolerance_percent
    )

    lower = evaluate_boundary(
        lower_line,
        lows,
        "lower",
        common_start,
        current_index,
        tolerance_percent
    )

    if (
        upper is None
        or lower is None
    ):
        return None

    reference_anchor = (
        calculate_reference_anchor_metrics(
            upper_line,
            lower_line,
            highs,
            lows,
            common_start,
            current_index,
            tolerance_percent
        )
    )

    candle_containment = (
        evaluate_candle_containment(
            upper_line,
            lower_line,
            candles,
            common_start,
            current_index
        )
    )

    return {
        "common_start":
            common_start,

        "current_index":
            current_index,

        "tolerance_percent":
            tolerance_percent,

        "upper":
            upper,

        "lower":
            lower,

        "candle_containment":
            candle_containment,

        "reference_anchor":
            reference_anchor
    }