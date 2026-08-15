"""
geometry.validation.apex_quality

Оценка качества точки Apex.

Отвечает только за диагностику
геометрической устойчивости Apex.

Не содержит:

- Score;
- Signal;
- торговых решений;
- Telegram.
"""


def evaluate_apex_quality(
    upper_line,
    lower_line,
    apex,
    start_index,
    end_index,
    min_slope_difference=0.05,
    max_ratio=1.0
):
    """
    Проверяет качество Apex.

    Основные проверки:

    1. Apex существует.
    2. Линии не являются почти параллельными.
    3. Apex находится в разумном диапазоне.

    Возвращает:

    {
        "valid": bool,
        "reason": str,
        "details": {}
    }

    """


    if (
        upper_line is None
        or lower_line is None
    ):

        return {

            "valid": False,

            "reason":
                "Missing trendlines",

            "details": {}

        }


    if apex is None:

        return {

            "valid": False,

            "reason":
                "Missing apex",

            "details": {}

        }


    upper_slope = float(
        upper_line.get(
            "slope",
            0
        )
    )


    lower_slope = float(
        lower_line.get(
            "slope",
            0
        )
    )


    slope_difference = abs(
        upper_slope
        -
        lower_slope
    )

    slope_scale = max(
        abs(upper_slope),
        abs(lower_slope),
        1e-12
    )

    relative_slope_difference = (
        slope_difference
        / slope_scale
    )


    apex_index = float(
        apex.get(
            "index",
            0
        )
    )


    structure_length = (
        end_index
        -
        start_index
    )


    if structure_length <= 0:

        return {

            "valid": False,

            "reason":
                "Invalid structure length",

            "details": {}

        }


    distance = (
        apex_index
        -
        end_index
    )


    ratio = (
        distance
        /
        structure_length
    )


    details = {

        "upper_slope":
            upper_slope,

        "lower_slope":
            lower_slope,

        "slope_difference":
            slope_difference,

        "apex_index":
            apex_index,

        "distance":
            distance,

        "ratio":
            round(
                ratio,
                3
            )

    }


    #
    # Линии почти параллельны
    #

    if relative_slope_difference < min_slope_difference:

        return {

            "valid": False,

            "reason":
                "Trendlines almost parallel",

            "details":
                details

        }


    #
    # Apex слишком далеко
    #

    if ratio > max_ratio:

        return {

            "valid": False,

            "reason":
                "Apex extension too large",

            "details":
                details

        }


    return {

        "valid": True,

        "reason":
            "Apex geometry stable",

        "details":
            details

    }