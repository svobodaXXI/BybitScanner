"""
structures/geometry_filter.py

Строгие геометрические проверки структур.

Не определяет название структуры.
Только проверяет:
- сходятся ли линии;
- есть ли сжатие;
- похожи ли линии на канал.
"""


def calculate_width_change(
    upper_line,
    lower_line,
    start_index,
    end_index
):
    """
    Рассчитывает изменение ширины структуры.
    """


    start_upper = (
        upper_line["slope"] * start_index
        +
        upper_line["intercept"]
    )

    start_lower = (
        lower_line["slope"] * start_index
        +
        lower_line["intercept"]
    )


    end_upper = (
        upper_line["slope"] * end_index
        +
        upper_line["intercept"]
    )

    end_lower = (
        lower_line["slope"] * end_index
        +
        lower_line["intercept"]
    )


    start_width = abs(
        start_upper - start_lower
    )

    end_width = abs(
        end_upper - end_lower
    )


    if start_width == 0:
        compression_percent = 0

    else:
        compression_percent = (
            1 -
            end_width / start_width
        ) * 100


    return {

        "start_width":
            round(
                start_width,
                8
            ),

        "end_width":
            round(
                end_width,
                8
            ),

        "compression_percent":
            round(
                compression_percent,
                2
            ),

        "is_compressing":
            end_width < start_width
    }



def check_parallelism(
    upper_slope,
    lower_slope,
    threshold=0.15
):
    """
    Проверяет, являются ли линии почти параллельными.
    """


    difference = abs(
        upper_slope - lower_slope
    )


    base = max(
        abs(upper_slope),
        abs(lower_slope),
        1e-9
    )


    ratio = difference / base


    return {

        "parallel":
            ratio < threshold,

        "ratio":
            round(
                ratio,
                5
            )
    }



def validate_convergence(
    width_change
):
    """
    Проверяет, что структура реально сжимается.
    """


    return {

        "valid":
            width_change.get(
                "is_compressing",
                False
            ),

        "reason":
            (
                "Structure is compressing"
                if width_change.get(
                    "is_compressing",
                    False
                )
                else
                "Structure is expanding"
            )
    }