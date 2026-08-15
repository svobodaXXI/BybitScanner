"""
geometry.pair_metrics

Диагностические метрики пары
upper / lower geometry candidates.

Модуль только измеряет свойства пары.

Не отвечает за:
- Validation Gate;
- Geometry Ranking;
- Pattern classification;
- trading Score;
- signals.
"""


from .compression import calculate_compression


def line_value(
    line,
    index
):
    """
    Возвращает значение линии
    в указанном индексе.
    """

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


def calculate_convergence_metrics(
    upper,
    lower,
    common_start,
    current_index
):
    """
    Измеряет движение upper/lower линий
    на общем наблюдаемом участке.

    Все движения нормализуются
    относительно цены инструмента.

    Никаких reject или ranking
    здесь не выполняется.
    """

    common_span = (
        current_index
        - common_start
    )

    if common_span <= 0:
        return None

    upper_start_price = line_value(
        upper,
        common_start
    )

    lower_start_price = line_value(
        lower,
        common_start
    )

    if (
        upper_start_price is None
        or lower_start_price is None
    ):
        return None

    reference_price = (
        upper_start_price
        + lower_start_price
    ) / 2.0

    if reference_price == 0:
        return None

    upper_move_absolute = (
        abs(
            upper["slope"]
        )
        * common_span
    )

    lower_move_absolute = (
        abs(
            lower["slope"]
        )
        * common_span
    )

    upper_move_percent = (
        upper_move_absolute
        / abs(reference_price)
        * 100
    )

    lower_move_percent = (
        lower_move_absolute
        / abs(reference_price)
        * 100
    )

    smaller_move = min(
        upper_move_percent,
        lower_move_percent
    )

    larger_move = max(
        upper_move_percent,
        lower_move_percent
    )

    if smaller_move > 0:

        slope_ratio = (
            larger_move
            / smaller_move
        )

    else:

        slope_ratio = float("inf")

    convergence_delta_percent = (
        upper_move_percent
        - lower_move_percent
    )

    if larger_move > 0:

        slope_balance = (
            smaller_move
            / larger_move
        )

    else:

        slope_balance = 0.0

    convergence_strength = (
        max(
            convergence_delta_percent,
            0.0
        )
        * slope_balance
    )

    return {
        "reference_price":
            reference_price,

        "upper_move_percent":
            upper_move_percent,

        "lower_move_percent":
            lower_move_percent,

        "slope_ratio":
            slope_ratio,

        "slope_balance":
            slope_balance,

        "convergence_delta_percent":
            convergence_delta_percent,

        "convergence_strength":
            convergence_strength
    }


def calculate_pair_metrics(
    upper_candidate,
    lower_candidate,
    current_index,
    highs=None,
    lows=None
):
    """
    Собирает диагностические
    pair-level метрики.

    Метрики сходимости берутся
    из production compression engine.

    Не выполняет hard reject,
    кроме невозможности корректно
    вычислить сам набор метрик.
    """

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

    common_span = (
        current_index
        - common_start
    )

    if common_span <= 0:
        return None

    anchor_distance = abs(
        upper_anchor
        - lower_anchor
    )

    anchor_balance = (
        1.0
        - min(
            anchor_distance
            / max(
                common_span,
                1
            ),
            1.0
        )
    )

    upper_structure_span = (
        upper_line.get(
            "structure_span",
            0
        )
    )

    lower_structure_span = (
        lower_line.get(
            "structure_span",
            0
        )
    )

    shared_structure_span = min(
        upper_structure_span,
        lower_structure_span
    )

    pair_compression = calculate_compression(
        upper_line,
        lower_line,
        common_start,
        current_index
    )

    if pair_compression is None:
        return None

    signed_start_width = (
        line_value(
            upper_line,
            common_start
        )
        -
        line_value(
            lower_line,
            common_start
        )
    )

    signed_current_width = (
        line_value(
            upper_line,
            current_index
        )
        -
        line_value(
            lower_line,
            current_index
        )
    )

    boundary_order_valid = (
        signed_start_width > 0
        and signed_current_width > 0
    )

    boundary_crossed = (
        signed_start_width > 0
        and signed_current_width <= 0
    )

    true_converging = (
        boundary_order_valid
        and signed_current_width
        < signed_start_width
    )

    convergence_metrics = (
        calculate_convergence_metrics(
            upper_line,
            lower_line,
            common_start,
            current_index
        )
    )

    if convergence_metrics is None:
        return None

    #
    # Anchor Sequence
    #

    upper_slope = upper_line.get(
        "slope",
        0
    )

    lower_slope = lower_line.get(
        "slope",
        0
    )

    anchor_family = "unknown"
    primary_anchor = None
    secondary_anchor = None
    expected_secondary_index = None
    sequence_valid = False

    if (
        upper_slope > 0
        and lower_slope > 0
    ):

        anchor_family = "rising"

        primary_anchor = lower_anchor
        secondary_anchor = upper_anchor

        next_highs = sorted(
            point["index"]
            for point in (highs or [])
            if (
                isinstance(point, dict)
                and point.get("index") is not None
                and point["index"] > primary_anchor
            )
        )

        expected_secondary_index = (
            next_highs[0]
            if next_highs
            else None
        )

        sequence_valid = (
            secondary_anchor
            == expected_secondary_index
        )

    elif (
        upper_slope < 0
        and lower_slope < 0
    ):

        anchor_family = "falling"

        primary_anchor = upper_anchor
        secondary_anchor = lower_anchor

        next_lows = sorted(
            point["index"]
            for point in (lows or [])
            if (
                isinstance(point, dict)
                and point.get("index") is not None
                and point["index"] > primary_anchor
            )
        )

        expected_secondary_index = (
            next_lows[0]
            if next_lows
            else None
        )

        sequence_valid = (
            secondary_anchor
            == expected_secondary_index
        )

    elif (
        upper_slope < 0
        and lower_slope > 0
    ):

        anchor_family = "triangle"

        sequence_valid = True

    anchor_sequence = {
        "family":
            anchor_family,

        "primary_anchor":
            primary_anchor,

        "secondary_anchor":
            secondary_anchor,

        "expected_secondary_index":
            expected_secondary_index,

        "valid":
            sequence_valid
    }

    return {
        "common_start":
            common_start,

        "common_span":
            common_span,

        "anchor_distance":
            anchor_distance,

        "anchor_balance":
            anchor_balance,

        "shared_structure_span":
            shared_structure_span,

        "start_width":
            pair_compression.get(
                "start_width"
            ),

        "current_width":
            pair_compression.get(
                "end_width"
            ),

        "compression_percent":
            pair_compression.get(
                "compression_percent"
            ),

        "is_converging":
            pair_compression.get(
                "is_compressing",
                False
            ),

        "signed_start_width":
            signed_start_width,

        "signed_current_width":
            signed_current_width,

        "boundary_order_valid":
            boundary_order_valid,

        "boundary_crossed":
            boundary_crossed,

        "true_converging":
            true_converging,

        "anchor_sequence":
            anchor_sequence,

        **convergence_metrics
    }