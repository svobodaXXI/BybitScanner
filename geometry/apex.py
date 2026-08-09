"""
geometry.apex

Расчёт точки пересечения
двух трендовых линий.

Geometry Engine v2.3:

Отвечает только за:
- математическое пересечение линий;
- координаты Apex;
- базовую геометрическую диагностику.

Не содержит:
- Validation;
- Score;
- Signal;
- торговую логику.
"""


def calculate_apex(
    upper_line,
    lower_line
):
    """
    Рассчитывает Apex двух линий.

    Возвращает:

    {
        "index": float,
        "price": float,

        "slope_difference": float,
        "valid_intersection": bool
    }

    Если пересечение невозможно:
    возвращает None.
    """


    if (
        upper_line is None
        or lower_line is None
    ):
        return None



    upper_slope = upper_line.get(
        "slope"
    )

    upper_intercept = upper_line.get(
        "intercept"
    )


    lower_slope = lower_line.get(
        "slope"
    )

    lower_intercept = lower_line.get(
        "intercept"
    )



    if (
        upper_slope is None
        or upper_intercept is None
        or lower_slope is None
        or lower_intercept is None
    ):
        return None



    try:

        slope_difference = abs(
            float(upper_slope)
            -
            float(lower_slope)
        )

    except (
        TypeError,
        ValueError
    ):

        return None



    # Параллельные линии.
    #
    # Apex не существует.

    if slope_difference < 1e-9:

        return None



    try:

        x = (

            float(lower_intercept)
            -
            float(upper_intercept)

        ) / (

            float(upper_slope)
            -
            float(lower_slope)

        )


        y = (

            float(upper_slope)
            *
            x

            +

            float(upper_intercept)

        )


    except (
        TypeError,
        ValueError,
        ZeroDivisionError
    ):

        return None



    return {

        "index":

            float(x),


        "price":

            float(y),


        "slope_difference":

            float(
                slope_difference
            ),


        "valid_intersection":

            True

    }