"""
geometry.ranking

Geometry Ranking Layer.

Оценивает качество геометрической модели.

Использует:

- Validation;
- Apex;
- Compression;
- Touches;
- Pair Metrics;
- Extremum Envelope Metrics;
- Reference Anchor Metrics.

Важно:

Ranking выбирает лучшую геометрию
ДО окончательной классификации паттерна.

Поэтому здесь пока не применяется
асимметричная логика:

Falling Wedge:
    upper = STRICT

Rising Wedge:
    lower = STRICT

Она должна подключаться только тогда,
когда направление паттерна известно.

Не отвечает за:
- торговый Score;
- сигналы;
- Confirmation.
"""


def _clamp(
    value,
    minimum=0.0,
    maximum=1.0
):
    """
    Ограничивает значение диапазоном.
    """

    try:
        value = float(
            value
        )

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


def _boundary_support_score(
    boundary,
    common_span
):
    """
    Мягкая оценка поддержки boundary
    однонаправленными экстремумами.

    Учитывает:
    - количество подтверждений;
    - распределение подтверждений
      по длине структуры.

    Максимум:
    10 points.
    """

    if not boundary:
        return 0.0

    support_count = boundary.get(
        "support_count",
        0
    )

    support_span = boundary.get(
        "support_span",
        0
    )

    #
    # До 6 points за количество.
    #
    # 3 подтверждающих extrema
    # уже дают максимальный бонус.
    #

    count_score = min(
        max(
            support_count,
            0
        )
        * 2.0,
        6.0
    )

    #
    # До 4 points за распределение.
    #

    if (
        common_span
        and common_span > 0
    ):

        span_ratio = _clamp(
            support_span
            / common_span
        )

    else:

        span_ratio = 0.0

    span_score = (
        span_ratio
        * 4.0
    )

    return (
        count_score
        + span_score
    )


def _boundary_outside_penalty(
    boundary
):
    """
    Мягкий штраф за extrema,
    выступающие наружу.

    Пока обе стороны оцениваются
    симметрично, потому что Ranking
    ещё не знает тип паттерна.

    Максимальный штраф:
    12 points на boundary.
    """

    if not boundary:
        return 0.0

    outside_count = boundary.get(
        "outside_count",
        0
    )

    outside_ratio = boundary.get(
        "outside_ratio",
        0.0
    )

    max_outside_percent = boundary.get(
        "max_outside_percent",
        0.0
    )

    count_penalty = min(
        max(
            outside_count,
            0
        )
        * 1.5,
        6.0
    )

    ratio_penalty = (
        _clamp(
            outside_ratio
        )
        * 3.0
    )

    #
    # Сильный отдельный прокол
    # тоже должен быть заметен.
    #
    # 2%+ наружу дают максимальный
    # компонент этого штрафа.
    #

    excursion_ratio = _clamp(
        max_outside_percent
        / 2.0
        if max_outside_percent
        is not None
        else 0.0
    )

    excursion_penalty = (
        excursion_ratio
        * 3.0
    )

    return min(
        count_penalty
        + ratio_penalty
        + excursion_penalty,
        12.0
    )


def rank_geometry(
    geometry
):
    """
    Возвращает Geometry Ranking Score.

    Это НЕ торговый Score.

    Hard reject здесь не выполняется.
    """

    if geometry is None:

        return -999

    score = 0.0

    validation = getattr(
        geometry,
        "validation",
        {}
    ) or {}

    compression = getattr(
        geometry,
        "compression",
        {}
    ) or {}

    touches = getattr(
        geometry,
        "touches",
        {}
    ) or {}

    pair_metrics = getattr(
        geometry,
        "pair_metrics",
        {}
    ) or {}

    envelope_metrics = getattr(
        geometry,
        "envelope_metrics",
        {}
    ) or {}

    checks = validation.get(
        "checks",
        {}
    ) or {}

    #
    # ==========================================================
    # 1. EXISTING BASE RANKING
    # ==========================================================
    #

    if validation.get(
        "valid",
        False
    ):

        score += 100.0

    if checks.get(
        "apex",
        {}
    ).get(
        "valid",
        False
    ):

        score += 30.0

    if compression.get(
        "is_compressing",
        False
    ):

        score += 25.0

    total_touches = touches.get(
        "total_touches",
        0
    )

    score += min(
        total_touches * 5.0,
        25.0
    )

    failed = validation.get(
        "failed_checks",
        []
    )

    score -= (
        len(failed)
        * 10.0
    )

    #
    # ==========================================================
    # 2. PAIR GEOMETRY
    # ==========================================================
    #

    if pair_metrics:

        #
        # Правильный порядок boundaries.
        #

        if pair_metrics.get(
            "boundary_order_valid",
            False
        ):

            score += 10.0

        else:

            score -= 15.0

        #
        # Реальная сходимость
        # без маскировки пересечения
        # абсолютным расстоянием.
        #

        if pair_metrics.get(
            "true_converging",
            False
        ):

            score += 10.0

        else:

            score -= 10.0

        #
        # Согласованность anchor positions.
        #
        # Maximum:
        # 10 points.
        #

        anchor_balance = _clamp(
            pair_metrics.get(
                "anchor_balance",
                0.0
            )
        )

        score += (
            anchor_balance
            * 10.0
        )

        #
        # Баланс движения boundaries.
        #
        # Maximum:
        # 10 points.
        #

        slope_balance = _clamp(
            pair_metrics.get(
                "slope_balance",
                0.0
            )
        )

        score += (
            slope_balance
            * 10.0
        )

    #
    # ==========================================================
    # 3. EXTREMUM ENVELOPE QUALITY
    # ==========================================================
    #

    if envelope_metrics:

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

        common_span = pair_metrics.get(
            "common_span",
            0
        )

        #
        # Количество и распределение
        # однонаправленных extrema.
        #
        # Maximum:
        # 10 + 10 points.
        #

        score += _boundary_support_score(
            upper,
            common_span
        )

        score += _boundary_support_score(
            lower,
            common_span
        )

        #
        # Наружные проколы.
        #
        # Пока симметрично.
        # Позже Directional Envelope Layer
        # разделит STRICT и EXCURSION side.
        #

        score -= _boundary_outside_penalty(
            upper
        )

        score -= _boundary_outside_penalty(
            lower
        )

        #
        # ======================================================
        # 4. REFERENCE EXTREMUM HYPOTHESIS
        # ======================================================
        #
        # Falling:
        # последний High перед minimum Low.
        #
        # Rising:
        # последний Low перед maximum High.
        #
        # Ranking ещё не знает,
        # какая гипотеза соответствует
        # будущей классификации.
        #
        # Поэтому наличие совпадения
        # хотя бы одной гипотезы даёт
        # небольшой бонус.
        #

        reference_anchor = (
            envelope_metrics.get(
                "reference_anchor"
            )
            or {}
        )

        falling = (
            reference_anchor.get(
                "falling"
            )
            or {}
        )

        rising = (
            reference_anchor.get(
                "rising"
            )
            or {}
        )

        falling_match = falling.get(
            "upper_reference_match",
            False
        )

        rising_match = rising.get(
            "lower_reference_match",
            False
        )

        if (
            falling_match
            or rising_match
        ):

            score += 5.0

    return float(
        score
    )