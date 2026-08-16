"""
geometry.evaluation

Оценка пары геометрических кандидатов.

Модуль отвечает только за:
- сбор геометрической модели;
- расчёт Apex;
- расчёт Compression;
- анализ Touches;
- Validation;
- создание GeometryModel.

Не отвечает за:
- выбор лучшего кандидата;
- паттерны;
- Score;
- сигналы.
"""


from .apex import calculate_apex
from .compression import calculate_compression
from .touches import analyze_touches
from .validation import validate_geometry
from .model import GeometryModel
from .pair_metrics import calculate_pair_metrics
from .envelope_metrics import calculate_envelope_metrics
from .pre_pattern import detect_pre_pattern_impulse

def evaluate_candidate_pair(
    upper_candidate,
    lower_candidate,
    highs=None,
    lows=None,
    current_index=None,
    candles=None
):
    """
    Оценивает пару линий
    верхнего и нижнего кандидата.

    Возвращает:

    GeometryModel
    """

    if (
        upper_candidate is None
        or lower_candidate is None
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

    upper_points = upper_candidate.get(
        "points",
        []
    )

    lower_points = lower_candidate.get(
        "points",
        []
    )

    if (
        not upper_points
        or not lower_points
    ):

        return None

    start_index = min(
        upper_points[0]["index"],
        lower_points[0]["index"]
    )

    end_index = max(
        upper_points[-1]["index"],
        lower_points[-1]["index"]
    )

    #
    # Apex
    #

    apex = calculate_apex(
        upper_line,
        lower_line
    )

    #
    # Compression
    #

    compression = calculate_compression(
        upper_line,
        lower_line,
        start_index,
        end_index
    )

    #
    # Touches
    #

    touches = analyze_touches(
        upper_line,
        lower_line,
        upper_points,
        lower_points
    )

    #
    # Validation
    #

    validation = validate_geometry(
        upper_line,
        lower_line,
        apex,
        compression,
        touches,
        start_index,
        end_index
    )

    #
    # Pair Metrics
    #

    pair_metrics = calculate_pair_metrics(
        upper_candidate,
        lower_candidate,
        current_index,
        highs=highs or [],
        lows=lows or []
    )

    if pair_metrics is None:
        return None

    pre_pattern_impulse = (
        detect_pre_pattern_impulse(
            candles,
            start_index
        )
    )

    pair_metrics[
        "pre_pattern_impulse"
    ] = pre_pattern_impulse

    anchor_sequence = (
        pair_metrics.get(
            "anchor_sequence"
        )
        or {}
    )

    anchor_family = anchor_sequence.get(
        "family"
    )

    if anchor_family in (
        "rising",
        "falling"
    ):

        geometry_mode = (
            "CANONICAL"
            if anchor_sequence.get(
                "valid",
                False
            )
            else "EXPLORATORY"
        )

    elif anchor_family == "triangle":

        geometry_mode = "EXPLORATORY"

    else:

        geometry_mode = "REJECT"

    pair_metrics[
        "geometry_mode"
    ] = geometry_mode

    envelope_metrics = calculate_envelope_metrics(
        upper_candidate,
        lower_candidate,
        highs or [],
        lows or [],
        current_index,
        candles=candles
    )

    candle_containment = (
        envelope_metrics.get(
            "candle_containment",
            {}
        )
        if envelope_metrics
        else {}
    ) or {}

    early_outside_run = max(
        candle_containment.get(
            "upper_early_max_run",
            0
        ),
        candle_containment.get(
            "lower_early_max_run",
            0
        )
    )

    if (
        geometry_mode == "CANONICAL"
        and early_outside_run >= 3
    ):
        geometry_mode = "EXPLORATORY"

        pair_metrics[
            "geometry_mode"
        ] = geometry_mode

        pair_metrics[
            "canonical_downgrade_reason"
        ] = (
            "early_multicandle_boundary_excursion"
        )

    evaluated_count = candle_containment.get(
        "evaluated_count",
        0
    )

    strict_outside_count = 0

    if anchor_family == "rising":
        strict_outside_count = (
            candle_containment.get(
                "upper_outside_count",
                0
            )
        )

    elif anchor_family == "falling":
        strict_outside_count = (
            candle_containment.get(
                "lower_outside_count",
                0
            )
        )

    strict_outside_ratio = (
        strict_outside_count
        / evaluated_count
        if evaluated_count
        else 0.0
    )

    if (
        geometry_mode == "CANONICAL"
        and anchor_family in (
            "rising",
            "falling"
        )
        and strict_outside_ratio > 0.20
    ):
        geometry_mode = "EXPLORATORY"

        pair_metrics[
            "geometry_mode"
        ] = geometry_mode

        pair_metrics[
            "canonical_downgrade_reason"
        ] = (
            "strict_boundary_outside_ratio"
        )

        pair_metrics[
            "strict_outside_ratio"
        ] = float(
            strict_outside_ratio
        )

    upper_envelope = (
        envelope_metrics.get("upper", {})
        if envelope_metrics
        else {}
    )

    lower_envelope = (
        envelope_metrics.get("lower", {})
        if envelope_metrics
        else {}
    )

    if (
        upper_envelope.get("support_count", 0) < 2
        or lower_envelope.get("support_count", 0) < 2
    ):
        return None

    #
    # Geometry Model Contract
    #

    return GeometryModel(

        upper_line=upper_line,

        lower_line=lower_line,

        apex=apex,

        compression=compression,

        touches=touches,

        validation=validation,

        start_index=start_index,

        end_index=end_index,

        current_index=current_index,

        candidate_points={

            "upper":
                upper_points,

            "lower":
                lower_points

        },

        pair_metrics=pair_metrics,

        envelope_metrics=envelope_metrics

    )
