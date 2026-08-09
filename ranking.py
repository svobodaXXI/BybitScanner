"""
ranking.py

Signal Ranking Engine v2.3

Отвечает за:
- фильтрацию сигналов;
- сортировку;
- формирование TOP списка.
"""


from config import MIN_SCORE



def rank_signals(results, limit=5):

    """
    Формирует рейтинг лучших сигналов.
    """


    signals = []


    for item in results:


        if not item:
            continue


        result = item.get(
            "result"
        )


        if not result:
            continue


        score = result.get(
            "final_score",
            result.get(
                "score",
                0
            )
        )


        confirmation = result.get(
            "confirmation"
        )


        if score < MIN_SCORE:
            continue


        signals.append(
            {
                "symbol": item["symbol"],

                "pattern": result.get(
                    "pattern",
                    "Unknown"
                ),

                "direction": (
                    confirmation.get(
                        "direction",
                        "WAIT"
                    )
                    if confirmation
                    else "WAIT"
                ),

                "score": score,

                "confirmed": (
                    confirmation.get(
                        "confirmed",
                        False
                    )
                    if confirmation
                    else False
                )
            }
        )


    signals.sort(
        key=lambda x: x["score"],
        reverse=True
    )


    return signals[:limit]