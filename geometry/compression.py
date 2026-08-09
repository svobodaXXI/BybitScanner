"""
geometry.compression

Анализ сжатия между двумя трендовыми линиями.

Модуль отвечает только за измерение
изменения расстояния между линиями.

Не содержит логики:
- паттернов;
- сигналов;
- скоринга.
"""


def calculate_line_distance(
    upper_line,
    lower_line,
    index
):
    """
    Рассчитывает расстояние между
    двумя линиями в определённой точке X.

    Цена линии:

    y = slope*x + intercept

    """

    if (
        upper_line is None
        or lower_line is None
    ):
        return None


    upper_price = (
        upper_line["slope"] * index
        +
        upper_line["intercept"]
    )


    lower_price = (
        lower_line["slope"] * index
        +
        lower_line["intercept"]
    )


    return abs(
        upper_price - lower_price
    )



def calculate_compression(
    upper_line,
    lower_line,
    start_index,
    end_index
):
    """
    Анализирует изменение ширины структуры.

    Возвращает:

    - ширину в начале;
    - ширину в конце;
    - процент сжатия;
    - факт сходимости.

    """


    start_width = calculate_line_distance(
        upper_line,
        lower_line,
        start_index
    )


    end_width = calculate_line_distance(
        upper_line,
        lower_line,
        end_index
    )


    if (
        start_width is None
        or end_width is None
    ):
        return None


    if start_width == 0:
        compression = 0

    else:

        compression = (
            1
            -
            end_width / start_width
        ) * 100


    return {

        "start_width":
            round(
                float(start_width),
                6
            ),


        "end_width":
            round(
                float(end_width),
                6
            ),


        "compression_percent":
            round(
                float(compression),
                2
            ),


        "is_compressing":
            end_width < start_width

    }