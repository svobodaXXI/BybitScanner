"""
geometry.touches

Анализ качества касаний
трендовых линий.

Отвечает только за геометрию
контакта цены с линией.

Не содержит логики:
- паттернов;
- сигналов;
- скоринга.
"""


def calculate_line_error(
    line,
    points
):
    """
    Рассчитывает отклонение Pivot точек
    от трендовой линии.
    """

    if (
        line is None
        or not points
    ):
        return None


    errors = []


    for point in points:

        predicted = (
            line["slope"]
            *
            point["index"]
            +
            line["intercept"]
        )


        error = abs(
            point["price"]
            -
            predicted
        )


        errors.append(
            error
        )


    return {

        "mean_error":
            sum(errors) / len(errors),

        "max_error":
            max(errors),

        "errors":
            errors

    }



def count_touches(
    line,
    points,
    tolerance_percent=0.006
):
    """
    Подсчитывает касания линии.

    Использует адаптивный допуск.

    0.006 = 0.6%

    """

    if (
        line is None
        or not points
    ):
        return 0


    touches = 0


    for point in points:


        predicted = (
            line["slope"]
            *
            point["index"]
            +
            line["intercept"]
        )


        if predicted <= 0:
            continue


        deviation = abs(
            point["price"]
            -
            predicted
        ) / predicted


        if deviation <= tolerance_percent:

            touches += 1


    return touches



def analyze_touches(
    upper_line,
    lower_line,
    highs,
    lows
):
    """
    Полный анализ касаний
    верхней и нижней границы.
    """


    upper_touches = count_touches(
        upper_line,
        highs
    )


    lower_touches = count_touches(
        lower_line,
        lows
    )


    total = (
        upper_touches
        +
        lower_touches
    )


    return {

        "upper_touches":
            upper_touches,

        "lower_touches":
            lower_touches,

        "total_touches":
            total,

        "valid":
            (
                upper_touches >= 2
                and
                lower_touches >= 2
            )

    }