"""
geometry.trendline

Построение трендовых линий
на основе Pivot точек.

Модуль отвечает только за математику линии.

Не содержит логики:
- клиньев;
- сигналов;
- скоринга;
- фильтров.
"""

import numpy as np

from .debug.logger import debug



def fit_trendline(points):
    """
    Строит линейную модель по Pivot точкам.

    Защищён от:
    - None price;
    - None index;
    - неправильных типов данных.
    """


    if not points:

        return None



    clean_points = []



    for p in points:

        if not isinstance(
            p,
            dict
        ):

            continue



        index = p.get(
            "index"
        )

        price = p.get(
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
                    "index": int(index),
                    "price": float(price)
                }
            )


        except (
            TypeError,
            ValueError
        ):

            continue



    if len(clean_points) < 2:

        return None



    x = np.array(
        [
            p["index"]
            for p in clean_points
        ],
        dtype=float
    )



    y = np.array(
        [
            p["price"]
            for p in clean_points
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
        slope * x
        +
        intercept
    )



    errors = abs(
        y - predictions
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
            )

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