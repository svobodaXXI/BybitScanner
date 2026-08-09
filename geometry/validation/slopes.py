"""
geometry.validation.slopes

Проверка наклонов трендовых линий.

Validation Engine v2:

Возвращает диагностический результат,
а не только True/False.
"""


def validate_slopes(
    upper_line,
    lower_line,
    minimum_difference=0.000001
):
    """
    Проверяет различие наклонов линий.

    Условие:

    Линии не должны быть практически параллельными.

    Возвращает:

    {
        "valid": bool,
        "reason": str,
        "details": dict
    }

    """

    if (
        upper_line is None
        or lower_line is None
    ):

        return {

            "valid":
                False,

            "reason":
                "Missing trendline data",

            "details":
                {}

        }


    upper_slope = float(
        upper_line["slope"]
    )


    lower_slope = float(
        lower_line["slope"]
    )


    difference = abs(
        upper_slope
        -
        lower_slope
    )


    if difference <= minimum_difference:

        return {

            "valid":
                False,

            "reason":
                "Trendlines are almost parallel",

            "details":
                {

                    "upper_slope":
                        upper_slope,

                    "lower_slope":
                        lower_slope,

                    "difference":
                        difference,

                    "minimum_difference":
                        minimum_difference

                }

        }


    return {

        "valid":
            True,

        "reason":
            "Slope difference acceptable",

        "details":
            {

                "upper_slope":
                    upper_slope,

                "lower_slope":
                    lower_slope,

                "difference":
                    difference

            }

    }