"""
geometry.validation.apex

Validation Engine v2

Проверка качества Apex точки.

Проверяет:

- наличие Apex;
- корректность пересечения линий;
- положение Apex относительно структуры;
- почти параллельные линии.

Не отвечает за:

- расчёт Apex;
- построение линий;
- Score;
- Signal;
- торговую логику.
"""


def validate_apex(
    upper_line,
    lower_line,
    apex,
    start_index,
    end_index
):
    """
    Проверка Apex.

    Поддерживаемый формат Apex:

    {
        "index": float,
        "price": float,
        "valid_intersection": bool
    }

    """

    details = {

        "start_index":
            start_index,

        "end_index":
            end_index

    }


    # -------------------------
    # Проверка входных данных
    # -------------------------

    if not upper_line or not lower_line:

        return {

            "valid": False,

            "reason":
                "Missing trendlines",

            "details":
                details

        }



    if apex is None:

        return {

            "valid": False,

            "reason":
                "Apex missing",

            "details":
                details

        }



    upper_slope = upper_line.get(
        "slope",
        0
    )

    lower_slope = lower_line.get(
        "slope",
        0
    )



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

        return {

            "valid": False,

            "reason":
                "Invalid slope data",

            "details":
                details

        }



    details.update(

        {

            "upper_slope":
                upper_slope,

            "lower_slope":
                lower_slope,

            "slope_difference":
                slope_difference

        }

    )



    # -------------------------
    # Проверка пересечения
    # -------------------------

    if not apex.get(
        "valid_intersection",
        False
    ):

        return {

            "valid": False,

            "reason":
                "Apex intersection invalid",

            "details":
                {
                    **details,
                    "apex":
                        apex
                }

        }



    #
    # Geometry Contract:
    #
    # Apex хранит:
    #
    # index
    # price
    #

    apex_index = apex.get(
        "index"
    )

    apex_price = apex.get(
        "price"
    )



    details.update(

        {

            "apex_index":
                apex_index,

            "apex_price":
                apex_price

        }

    )



    # -------------------------
    # Почти параллельные линии
    # -------------------------

    if slope_difference < 1e-12:

        return {

            "valid": False,

            "reason":
                "Trendlines almost parallel",

            "details":
                {
                    **details,
                    "issue":
                        "parallel_lines"
                }

        }



    # -------------------------
    # Проверка координаты Apex
    # -------------------------

    if apex_index is None:

        return {

            "valid": False,

            "reason":
                "Apex coordinate missing",

            "details":
                details

        }



    try:

        structure_length = (
            float(end_index)
            -
            float(start_index)
        )

    except (
        TypeError,
        ValueError
    ):

        structure_length = 1



    if structure_length <= 0:

        structure_length = 1



    distance = (

        float(apex_index)
        -
        float(end_index)

    )



    ratio = (

        distance
        /
        structure_length

    )



    details.update(

        {

            "distance":
                distance,

            "ratio":
                round(
                    ratio,
                    3
                )

        }

    )



    # -------------------------
    # Apex после структуры
    # -------------------------

    if distance >= 0:

        return {

            "valid": True,

            "reason":
                "Apex after structure",

            "details":
                details

        }



    # -------------------------
    # Apex внутри последних 35%
    # структуры.
    #
    # Для клиньев Apex может
    # находиться немного раньше
    # последнего Pivot.
    # -------------------------

    tolerance = (

        structure_length
        *
        0.35

    )



    if False and abs(distance) <= tolerance:

        return {

            "valid": True,

            "reason":
                "Apex slightly before structure end",

            "details":
                details

        }



    return {

        "valid": False,

        "reason":
            "Apex position invalid",

        "details":
            details

    }