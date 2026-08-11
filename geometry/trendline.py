"""
geometry.trendline

Построение трендовых линий
на основе Pivot точек.

Модуль отвечает только за математику линии.

Поддерживает:

- legacy regression trendline;
- anchor-based structural trendline.

Не содержит логики:

- клиньев;
- сигналов;
- торгового скоринга;
- фильтрации pattern type.
"""

import numpy as np

from .debug.logger import debug


def _clean_points(points):
    """
    Нормализует Pivot точки.

    Возвращает только корректные:

    {
        "index": int,
        "price": float
    }
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

            clean_points.append(
                {
                    "index":
                        int(index),

                    "price":
                        float(price)
                }
            )

        except (
            TypeError,
            ValueError
        ):

            continue

    clean_points.sort(
        key=lambda item:
            item["index"]
    )

    return clean_points


def _calculate_errors(
    points,
    slope,
    intercept
):
    """
    Рассчитывает абсолютные ошибки
    Pivot точек относительно линии.
    """

    errors = []

    for point in points:

        predicted = (
            slope
            *
            point["index"]
            +
            intercept
        )

        errors.append(
            abs(
                point["price"]
                -
                predicted
            )
        )

    return errors


def fit_trendline(points):
    """
    Legacy regression trendline.

    Сохраняется для совместимости
    с существующим API и тестами.

    Строит линейную регрессию
    по всем переданным Pivot точкам.

    Новая Geometry Candidate Layer
    должна использовать
    fit_anchor_trendline().
    """

    clean_points = _clean_points(
        points
    )

    if len(clean_points) < 2:

        return None

    x = np.array(
        [
            point["index"]
            for point in clean_points
        ],
        dtype=float
    )

    y = np.array(
        [
            point["price"]
            for point in clean_points
        ],
        dtype=float
    )

    try:

        slope, intercept = np.polyfit(
            x,
            y,
            1
        )

    except Exception:

        return None

    predictions = (
        slope
        *
        x
        +
        intercept
    )

    errors = abs(
        y
        -
        predictions
    )

    return {
        "slope":
            float(slope),

        "intercept":
            float(intercept),

        "points":
            len(clean_points),

        "error_mean":
            float(
                errors.mean()
            ),

        "error_max":
            float(
                errors.max()
            ),

        "model":
            "regression"
    }


def fit_anchor_trendline(
    points
):
    """
    Строит structural trendline
    через два реальных Pivot anchors.

    Первые две точки являются
    обязательными anchors линии.

    Остальные переданные точки
    используются только для измерения
    качества линии.

    Линия физически проходит
    через оба anchor Pivot.

    Parameters
    ----------

    points : list[dict]

        Минимум две точки.

        points[0]
            primary anchor

        points[1]
            secondary anchor

        points[2:]
            дополнительные точки
            для оценки качества.

    Returns
    -------

    dict | None

        Контракт совместим
        с fit_trendline().
    """

    clean_points = _clean_points(
        points
    )

    if len(clean_points) < 2:

        return None

    anchor = clean_points[0]

    second = clean_points[1]

    dx = (
        second["index"]
        -
        anchor["index"]
    )

    if dx <= 0:

        return None

    slope = (
        second["price"]
        -
        anchor["price"]
    ) / dx

    intercept = (
        anchor["price"]
        -
        slope
        *
        anchor["index"]
    )

    errors = _calculate_errors(
        clean_points,
        slope,
        intercept
    )

    if not errors:

        return None

    error_mean = (
        sum(errors)
        /
        len(errors)
    )

    error_max = max(
        errors
    )

    return {
        "slope":
            float(slope),

        "intercept":
            float(intercept),

        "points":
            len(clean_points),

        "error_mean":
            float(error_mean),

        "error_max":
            float(error_max),

        "model":
            "anchor",

        "anchor_index":
            anchor["index"],

        "anchor_price":
            anchor["price"],

        "second_index":
            second["index"],

        "second_price":
            second["price"],

        "anchor_span":
            int(dx)
    }


def calculate_price(
    line,
    index
):
    """
    Возвращает цену линии
    в указанной точке X.
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

    try:

        return (
            float(slope)
            *
            float(index)
            +
            float(intercept)
        )

    except (
        TypeError,
        ValueError
    ):

        return None