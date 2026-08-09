"""
structures/channel.py

Определение канальных структур.

Отвечает только за:
- Ascending Channel;
- Descending Channel.

Не отвечает за:
- поиск линий;
- валидацию;
- скоринг;
- торговые сигналы.
"""


def detect_channel(
    upper_slope,
    lower_slope,
    threshold=0.15
):
    """
    Определяет является ли структура каналом.

    Канал:
    - линии имеют близкие наклоны;
    - расстояние между линиями примерно сохраняется.

    threshold:
        допустимое относительное различие наклонов.
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



    if ratio > threshold:

        return {

            "structure":
                "Invalid",

            "reason":
                "Trendlines are not parallel"

        }



    # нисходящий канал

    if (

        upper_slope < 0

        and

        lower_slope < 0

    ):

        return {

            "structure":
                "Descending Channel",

            "reason":
                "Descending parallel trendlines"

        }



    # восходящий канал

    if (

        upper_slope > 0

        and

        lower_slope > 0

    ):

        return {

            "structure":
                "Ascending Channel",

            "reason":
                "Ascending parallel trendlines"

        }



    return {

        "structure":
            "Invalid",

        "reason":
            "No channel structure"

    }