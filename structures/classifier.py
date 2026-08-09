"""
structures/classifier.py

Главный классификатор структур.

Отвечает только за:
- маршрутизацию между типами структур.

Не отвечает за:
- геометрию;
- линии;
- валидацию;
- скоринг.
"""


from structures.wedge import detect_wedge
from structures.channel import detect_channel



def classify_structure(
    upper_line,
    lower_line,
    compression
):
    """
    Определяет тип структуры.
    """


    if not upper_line or not lower_line:

        return {

            "structure":
                "Invalid",

            "reason":
                "Missing trendlines"

        }



    upper_slope = upper_line.get(
        "slope",
        0
    )


    lower_slope = lower_line.get(
        "slope",
        0
    )



    # Сначала проверяем канал.
    # Канал важнее клина,
    # потому что параллельность
    # исключает wedge.


    channel = detect_channel(
        upper_slope,
        lower_slope
    )


    if channel["structure"] != "Invalid":

        return channel



    # Затем проверяем клин.

    wedge = detect_wedge(
        upper_slope,
        lower_slope,
        compression
    )


    if wedge["structure"] != "Invalid":

        return wedge



    return {

        "structure":
            "Invalid",

        "reason":
            "No recognizable structure"

    }