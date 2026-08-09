"""
analyzer.scoring

Расчёт итогового рейтинга сигнала.
"""


def calculate_final_score(
    result,
    confirmation
):
    """
    Итоговый Score = структура + подтверждение.
    """

    base_score = result.get(
        "score",
        0
    )


    confirmation_score = confirmation.get(
        "confirmation_score",
        0
    )


    return min(
        base_score + confirmation_score,
        100
    )