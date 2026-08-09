"""
structures/wedge.py

Определение клиновых структур.

Отвечает только за:
- Falling Wedge;
- Rising Wedge.

Не отвечает за:
- каналы;
- валидацию;
- скоринг;
- сигналы.
"""


def detect_wedge(
    upper_slope,
    lower_slope,
    compression
):
    """
    Определяет клин.

    Требования:
    - линии должны сходиться;
    - структура должна сжиматься.
    """


    if not compression.get(
        "is_compressing",
        False
    ):

        return {

            "structure":
                "Invalid",

            "reason":
                "Structure is not compressing"

        }



    # Falling Wedge

    if (

        upper_slope < 0

        and

        lower_slope < 0

        and

        lower_slope > upper_slope

    ):

        return {

            "structure":
                "Falling Wedge",

            "reason":
                "Descending converging trendlines"

        }



    # Rising Wedge

    if (

        upper_slope > 0

        and

        lower_slope > 0

        and

        lower_slope < upper_slope

    ):

        return {

            "structure":
                "Rising Wedge",

            "reason":
                "Ascending converging trendlines"

        }



    return {

        "structure":
            "Invalid",

        "reason":
            "No wedge structure"

    }