"""
signal.quality

Оценка качества торговой структуры.

Отвечает только за:
- классификацию качества сигнала;
- итоговый статус Setup.

Не содержит:
- поиска паттернов;
- Geometry;
- Confirmation;
- Telegram;
- торговых решений.
"""



def evaluate_quality(
    pattern,
    geometry,
    confirmation,
    score
):
    """
    Оценивает качество найденной структуры.

    Возвращает:

    {
        "quality": str,
        "reason": str
    }
    """



    if pattern == "No wedge":

        return {

            "quality": "Invalid",

            "reason":
                "Pattern not found"

        }



    if geometry is None:

        return {

            "quality": "Invalid",

            "reason":
                "Missing geometry"

        }



    validation = geometry.get(
        "validation",
        {}
    )


    if not validation.get(
        "valid",
        False
    ):

        return {

            "quality": "Invalid",

            "reason":
                "Geometry validation failed"

        }



    confirmation = confirmation or {}



    breakout = confirmation.get(
        "breakout",
        False
    )


    volume = confirmation.get(
        "volume",
        False
    )


    retest = confirmation.get(
        "retest",
        False
    )


    confirmation_score = confirmation.get(
        "confirmation_score",
        0
    )



    compression = geometry.get(
        "compression",
        {}
    )


    touches = geometry.get(
        "touches",
        {}
    )


    compression_value = compression.get(
        "compression_percent",
        0
    )


    total_touches = touches.get(
        "total_touches",
        0
    )



    # =========================
    # Elite Setup
    # =========================

    if (

        breakout

        and

        volume

        and

        retest

        and

        score >= 85

        and

        confirmation_score >= 25

        and

        total_touches >= 5

    ):

        return {

            "quality":
                "Elite Setup",

            "reason":
                "Strong structure with full confirmation"

        }



    # =========================
    # A Setup
    # =========================

    if (

        breakout

        and

        score >= 75

        and

        confirmation_score >= 15

    ):

        return {

            "quality":
                "A Setup",

            "reason":
                "Valid structure with breakout confirmation"

        }



    # =========================
    # B Setup
    # =========================

    if (

        score >= 60

        and

        compression_value >= 15

        and

        total_touches >= 4

    ):

        return {

            "quality":
                "B Setup",

            "reason":
                "Valid structure awaiting confirmation"

        }



    # =========================
    # Watch
    # =========================

    if score >= 50:

        return {

            "quality":
                "Watch",

            "reason":
                "Structure exists but quality is limited"

        }



    return {

        "quality":
            "Weak Setup",

        "reason":
            "Insufficient confirmation or structure quality"

    }