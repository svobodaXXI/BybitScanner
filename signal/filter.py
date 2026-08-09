"""
signal.filter

Фильтр торговых сигналов.

Отвечает только за:
- принятие решения по качеству Setup;
- допуск сигнала;
- режимы работы сканера.

Не содержит:
- поиска паттернов;
- Geometry;
- Confirmation;
- Score расчёта;
- Telegram.
"""


def evaluate_signal(
    quality,
    score,
    confirmation,
    mode="hunter"
):
    """
    Определяет, является ли сигнал подходящим.

    Возвращает:

    {
        "approved": bool,
        "reason": str
    }
    """


    quality_name = (
        quality.get("quality")
        if quality
        else "Invalid"
    )


    confirmation = confirmation or {}



    breakout = confirmation.get(
        "breakout",
        False
    )


    confirmed = confirmation.get(
        "confirmed",
        False
    )



    # =========================
    # Invalid
    # =========================

    if quality_name == "Invalid":

        return {

            "approved": False,

            "reason":
                "Invalid structure"

        }



    # =========================
    # Hunter mode
    # =========================

    if mode == "hunter":


        if quality_name in (
            "A+ Setup",
            "A Setup"
        ):

            return {

                "approved": True,

                "reason":
                    "High quality confirmed setup"

            }


        if (
            quality_name == "B Setup"
            and score >= 70
        ):

            return {

                "approved": False,

                "reason":
                    "Good structure waiting confirmation"

            }



    # =========================
    # Sniper mode
    # =========================

    if mode == "sniper":


        if (
            confirmed
            and breakout
            and score >= 80
        ):

            return {

                "approved": True,

                "reason":
                    "Confirmed sniper setup"

            }



    return {

        "approved": False,

        "reason":
            "Conditions not satisfied"

    }