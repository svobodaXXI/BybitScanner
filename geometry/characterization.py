"""
geometry.characterization

Описание характера геометрической структуры.

Модуль отвечает только за анализ:
- направления линий;
- сравнение наклонов;
- характера движения.

Не содержит логики:
- паттернов;
- сигналов;
- скоринга.
"""


def slope_direction(
    slope
):
    """
    Определяет направление линии.
    """

    if slope > 0:
        return "up"

    if slope < 0:
        return "down"

    return "flat"



def compare_slopes(
    upper_slope,
    lower_slope
):
    """
    Сравнивает скорость изменения линий.
    """

    if lower_slope > upper_slope:
        return "lower_faster"

    if lower_slope < upper_slope:
        return "upper_faster"

    return "equal"



def analyze_characterization(
    upper_line,
    lower_line
):
    """
    Создаёт описание геометрического характера.
    """

    if (
        upper_line is None
        or lower_line is None
    ):
        return None


    upper_slope = upper_line["slope"]

    lower_slope = lower_line["slope"]


    upper_direction = slope_direction(
        upper_slope
    )

    lower_direction = slope_direction(
        lower_slope
    )


    slope_relation = compare_slopes(
        upper_slope,
        lower_slope
    )


    return {

        "upper_slope":
            float(
                upper_slope
            ),

        "lower_slope":
            float(
                lower_slope
            ),

        "upper_direction":
            upper_direction,

        "lower_direction":
            lower_direction,

        "slope_relation":
            slope_relation

    }