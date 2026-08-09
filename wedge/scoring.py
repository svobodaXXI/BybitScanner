"""
wedge.scoring

Расчёт качества структуры.

Отвечает только за:
- оценку геометрии;
- расчёт score;
- детализацию баллов.

Не содержит:
- поиска линий;
- классификации;
- сигналов.
"""


def calculate_score(
    pattern,
    compression,
    touches,
    quality=None
):
    """
    Рассчитывает структурный score.

    Максимум:

    structure 40
    compression 25
    touches 20
    quality bonus 15

    Итого: 100
    """


    breakdown = {

        "structure":
            0,

        "compression":
            0,

        "touches":
            0,

        "quality":
            0

    }



    #
    # Тип структуры
    #

    if pattern in (

        "Falling Wedge",

        "Rising Wedge"

    ):

        breakdown["structure"] = 40


    elif pattern == "Triangle Compression":

        breakdown["structure"] = 30



    #
    # Сжатие
    #

    compression_percent = (

        compression.get(
            "compression_percent",
            0
        )

    )


    if compression_percent >= 40:

        breakdown["compression"] = 25


    elif compression_percent >= 20:

        breakdown["compression"] = 20


    elif compression_percent >= 5:

        breakdown["compression"] = 10



    #
    # Касания
    #

    total_touches = (

        touches.get(
            "total_touches",
            0
        )

    )


    if total_touches >= 8:

        breakdown["touches"] = 20


    elif total_touches >= 6:

        breakdown["touches"] = 15


    elif total_touches >= 4:

        breakdown["touches"] = 10



    #
    # Качество
    #

    if quality:

        status = quality.get(
            "status"
        )


        if status == "VALID":

            breakdown["quality"] = 15


        elif status == "WARNING":

            breakdown["quality"] = 8



    total = sum(
        breakdown.values()
    )


    return {

        "score":
            min(
                total,
                100
            ),

        "score_breakdown":
            breakdown

    }