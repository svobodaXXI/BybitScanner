"""
geometry.candidate

Anchor-Based Candidate Line Generator.

Создаёт возможные structural trendlines
из Pivot точек.

Новая модель:

Primary Pivot Anchor
        ↓
Secondary Pivot Anchor
        ↓
Exact Anchor Trendline
        ↓
Forward Pivot Confirmation
        ↓
Candidate

Каждая линия обязана проходить
через исходную пару реальных Pivot anchors.

Отвечает только за:

- генерацию anchor-пар;
- построение линий;
- проверку forward support;
- подготовку кандидатов.

Не отвечает за:

- определение клина;
- Pattern Classification;
- Geometry Pair Ranking;
- торговый Score;
- сигналы.
"""


from geometry.trendline import (
    fit_anchor_trendline,
    calculate_price
)


DEFAULT_TOLERANCE_PERCENT = 0.6

DEFAULT_MIN_CONFIRMATIONS = 2

DEFAULT_MIN_LINE_SPAN = 30


def _clean_points(
    points
):
    """
    Нормализует Pivot точки
    для Candidate Generator.
    """

    if not points:

        return []

    clean_points = []

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

        try:

            cleaned = {
                "index":
                    int(index),

                "price":
                    float(price)
            }

        except (
            TypeError,
            ValueError
        ):

            continue

        point_type = point.get(
            "type"
        )

        if point_type is not None:

            cleaned["type"] = (
                point_type
            )

        clean_points.append(
            cleaned
        )

    clean_points.sort(
        key=lambda item:
            item["index"]
    )

    return clean_points


def _error_percent(
    actual,
    predicted
):
    """
    Относительная ошибка точки
    относительно линии.
    """

    if predicted == 0:

        return None

    return (
        abs(
            actual
            -
            predicted
        )
        /
        abs(predicted)
        *
        100
    )


def _calculate_absolute_errors(
    line,
    points
):
    """
    Абсолютные ошибки точек
    относительно уже построенной
    anchor-line.

    Важно:

    линия здесь НЕ перестраивается.
    """

    errors = []

    for point in points:

        predicted = calculate_price(
            line,
            point["index"]
        )

        if predicted is None:

            continue

        errors.append(
            abs(
                point["price"]
                -
                predicted
            )
        )

    return errors


def build_candidate_lines(
    points,
    size=4,
    tolerance_percent=DEFAULT_TOLERANCE_PERCENT,
    min_confirmations=DEFAULT_MIN_CONFIRMATIONS,
    min_line_span=DEFAULT_MIN_LINE_SPAN
):
    """
    Создаёт anchor-based кандидаты
    трендовых линий.

    Parameters
    ----------

    points : list[dict]

        Pivot точки:

        {
            "index": int,
            "price": float
        }


    size : int

        Legacy API parameter.

        Сохраняется для совместимости
        со старыми вызовами.

        В anchor-based модели количество
        Pivot точек линии не фиксируется
        заранее.


    tolerance_percent : float

        Максимальное процентное отклонение
        Pivot от линии для подтверждения.


    min_confirmations : int

        Минимальное количество
        подтверждений после primary anchor.

        Secondary anchor является одним
        из реальных подтверждений.


    min_line_span : int

        Минимальное расстояние в барах
        между primary и secondary anchors.


    Returns
    -------

    list[dict]

        Legacy-compatible contract:

        {
            "points": [...],
            "line": {...}
        }

        Дополнительная metadata
        расширяет контракт,
        но не изменяет его основу.
    """

    clean_points = _clean_points(
        points
    )

    if len(clean_points) < 2:

        return []

    candidates = []

    for anchor_position in range(
        len(clean_points) - 1
    ):

        anchor = clean_points[
            anchor_position
        ]

        for second_position in range(
            anchor_position + 1,
            len(clean_points)
        ):

            second = clean_points[
                second_position
            ]

            anchor_span = (
                second["index"]
                -
                anchor["index"]
            )

            if (
                anchor_span
                <
                min_line_span
            ):

                continue

            #
            # Линия создаётся ОДИН РАЗ
            # через исходную пару anchors.
            #

            line = fit_anchor_trendline(
                [
                    anchor,
                    second
                ]
            )

            if line is None:

                continue

            #
            # Проверяем secondary anchor
            # и все последующие Pivot.
            #
            # При этом line больше
            # никогда не перестраивается.
            #

            evaluated_points = (
                clean_points[
                    anchor_position + 1:
                ]
            )

            confirmed_points = []

            errors_percent = []

            for point in evaluated_points:

                predicted = calculate_price(
                    line,
                    point["index"]
                )

                if predicted is None:

                    continue

                error_percent = (
                    _error_percent(
                        point["price"],
                        predicted
                    )
                )

                if error_percent is None:

                    continue

                errors_percent.append(
                    error_percent
                )

                if (
                    error_percent
                    <=
                    tolerance_percent
                ):

                    confirmed_points.append(
                        point
                    )

            confirmations = len(
                confirmed_points
            )

            if (
                confirmations
                <
                min_confirmations
            ):

                continue

            #
            # Primary anchor
            # +
            # фактически подтверждающие
            # эту конкретную линию Pivot.
            #

            candidate_points = [
                anchor
            ]

            candidate_points.extend(
                confirmed_points
            )

            #
            # Пересчитываем error metrics
            # относительно ИСХОДНОЙ линии,
            # не создавая новую линию.
            #

            absolute_errors = (
                _calculate_absolute_errors(
                    line,
                    candidate_points
                )
            )

            if absolute_errors:

                line["error_mean"] = float(
                    sum(absolute_errors)
                    /
                    len(absolute_errors)
                )

                line["error_max"] = float(
                    max(
                        absolute_errors
                    )
                )

            support_ratio = (
                confirmations
                /
                len(evaluated_points)
                if evaluated_points
                else 0.0
            )

            structure_span = (
                candidate_points[-1]["index"]
                -
                anchor["index"]
            )

            mean_confirmation_error = (
                sum(errors_percent)
                /
                len(errors_percent)
                if errors_percent
                else None
            )

            line["points"] = len(
                candidate_points
            )

            line[
                "confirmations"
            ] = confirmations

            line[
                "support_ratio"
            ] = float(
                support_ratio
            )

            line[
                "structure_span"
            ] = int(
                structure_span
            )

            line[
                "confirmation_error_percent"
            ] = (
                float(
                    mean_confirmation_error
                )
                if mean_confirmation_error
                is not None
                else None
            )

            candidates.append(
                {
                    "points":
                        candidate_points,

                    "line":
                        line,

                    "anchor_index":
                        anchor["index"],

                    "second_index":
                        second["index"],

                    "confirmations":
                        confirmations,

                    "support_ratio":
                        float(
                            support_ratio
                        ),

                    "structure_span":
                        int(
                            structure_span
                        )
                }
            )

    return candidates


def generate_candidates(
    points,
    size=4
):
    """
    Совместимость со старым API.

    Старое имя функции.
    """

    return build_candidate_lines(
        points,
        size
    )