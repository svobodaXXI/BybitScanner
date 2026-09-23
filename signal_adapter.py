"""
signal_adapter.py

Приведение результата анализа
к формату signal_memory.
"""


def prepare_signal(
    symbol,
    result
):

    if not result:
        return None


    confirmation = result.get(
        "confirmation",
        {}
    )


    return {

        "symbol": symbol,
        **({"timeframe": str(result["timeframe"])} if result.get("timeframe") is not None else {}),

        "score":
            result.get(
                "final_score",
                result.get(
                    "score",
                    0
                )
            ),

        "direction":
            confirmation.get(
                "direction",
                "WAIT"
            ),

        "pattern":
            result.get(
                "pattern",
                "Unknown"
            )

    }