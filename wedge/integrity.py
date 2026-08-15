"""
wedge.integrity

Structure Integrity Layer.

Оценивает целостность уже найденной
и валидированной геометрической структуры.

Отвечает только за:
- распределение подтверждений границ;
- протяжённость подтверждений;
- наружные проколы;
- согласованность anchors;
- согласованность движения boundaries.

Не содержит:
- поиска линий;
- Validation;
- классификации паттерна;
- торговых сигналов;
- hard reject.

Version 1:
диагностический soft-score 0..20.
"""


def _clamp(
    value,
    minimum=0.0,
    maximum=1.0
):
    try:
        value = float(value)
    except (
        TypeError,
        ValueError
    ):
        return minimum

    return max(
        minimum,
        min(
            value,
            maximum
        )
    )


def evaluate_integrity(
    geometry
):
    """
    Оценивает целостность структуры.

    Максимум:
        boundary support : 6
        support span     : 6
        outside control  : 3
        anchor balance   : 3
        slope balance    : 2

    Total:
        20

    Hard reject не выполняется.
    """

    if not geometry:

        return {
            "status": "WEAK",
            "score": 0.0,
            "details": {},
            "warnings": [
                "Missing geometry data"
            ]
        }

    pair_metrics = (
        geometry.get(
            "pair_metrics"
        )
        or {}
    )

    envelope_metrics = (
        geometry.get(
            "envelope_metrics"
        )
        or {}
    )

    upper = (
        envelope_metrics.get(
            "upper"
        )
        or {}
    )

    lower = (
        envelope_metrics.get(
            "lower"
        )
        or {}
    )

    common_span = float(
        pair_metrics.get(
            "common_span",
            0
        )
        or 0
    )

    upper_support = int(
        upper.get(
            "support_count",
            0
        )
        or 0
    )

    lower_support = int(
        lower.get(
            "support_count",
            0
        )
        or 0
    )

    upper_span = float(
        upper.get(
            "support_span",
            0
        )
        or 0
    )

    lower_span = float(
        lower.get(
            "support_span",
            0
        )
        or 0
    )

    upper_outside = int(
        upper.get(
            "outside_count",
            0
        )
        or 0
    )

    lower_outside = int(
        lower.get(
            "outside_count",
            0
        )
        or 0
    )

    #
    # 1. Boundary support
    #
    # 2+2 = минимальная структура.
    # Дополнительные подтверждения
    # повышают уверенность постепенно.
    #

    support_score = 0.0

    support_score += min(
        upper_support,
        3
    )

    support_score += min(
        lower_support,
        3
    )

    #
    # 2. Support span
    #
    # Важно не только количество,
    # но и распределение контактов
    # по длине структуры.
    #

    if common_span > 0:

        upper_span_ratio = _clamp(
            upper_span
            /
            common_span
        )

        lower_span_ratio = _clamp(
            lower_span
            /
            common_span
        )

    else:

        upper_span_ratio = 0.0
        lower_span_ratio = 0.0

    span_score = (
        upper_span_ratio
        +
        lower_span_ratio
    ) * 3.0

    #
    # 3. Outside control
    #

    total_outside = (
        upper_outside
        +
        lower_outside
    )

    if total_outside == 0:

        outside_score = 3.0

    elif total_outside == 1:

        outside_score = 2.0

    elif total_outside == 2:

        outside_score = 1.0

    else:

        outside_score = 0.0

    #
    # 4. Anchor balance
    #

    anchor_balance = _clamp(
        pair_metrics.get(
            "anchor_balance",
            0.0
        )
    )

    anchor_score = (
        anchor_balance
        *
        3.0
    )

    #
    # 5. Slope balance
    #

    slope_balance = _clamp(
        pair_metrics.get(
            "slope_balance",
            0.0
        )
    )

    slope_score = (
        slope_balance
        *
        2.0
    )

    total = (
        support_score
        +
        span_score
        +
        outside_score
        +
        anchor_score
        +
        slope_score
    )

    total = round(
        min(
            total,
            20.0
        ),
        2
    )

    warnings = []

    if upper_support <= 2:
        warnings.append(
            "Upper boundary has minimal support"
        )

    if lower_support <= 2:
        warnings.append(
            "Lower boundary has minimal support"
        )

    if upper_span_ratio < 0.35:
        warnings.append(
            "Upper support is poorly distributed"
        )

    if lower_span_ratio < 0.35:
        warnings.append(
            "Lower support is poorly distributed"
        )

    if total_outside >= 3:
        warnings.append(
            "Too many boundary excursions"
        )

    if anchor_balance < 0.40:
        warnings.append(
            "Anchor positions are poorly balanced"
        )

    if total >= 15:

        status = "STRONG"

    elif total >= 10:

        status = "ACCEPTABLE"

    else:

        status = "WEAK"

    return {
        "status":
            status,

        "score":
            total,

        "details":
            {
                "support_score":
                    round(
                        support_score,
                        2
                    ),

                "span_score":
                    round(
                        span_score,
                        2
                    ),

                "outside_score":
                    round(
                        outside_score,
                        2
                    ),

                "anchor_score":
                    round(
                        anchor_score,
                        2
                    ),

                "slope_score":
                    round(
                        slope_score,
                        2
                    ),

                "upper_support":
                    upper_support,

                "lower_support":
                    lower_support,

                "upper_span_ratio":
                    round(
                        upper_span_ratio,
                        3
                    ),

                "lower_span_ratio":
                    round(
                        lower_span_ratio,
                        3
                    ),

                "total_outside":
                    total_outside,

                "anchor_balance":
                    round(
                        anchor_balance,
                        3
                    ),

                "slope_balance":
                    round(
                        slope_balance,
                        3
                    )
            },

        "warnings":
            warnings
    }