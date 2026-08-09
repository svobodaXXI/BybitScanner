"""
confidence.py

Confidence Engine v2.3.1

Оценивает качество торгового сигнала.
"""


def calculate_confidence(result):

    if not result:

        return {
            "level": "LOW",
            "reason": "No result"
        }


    score = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )


    confirmation = result.get(
        "confirmation",
        {}
    )


    confirmation_score = confirmation.get(
        "confirmation_score",
        0
    )


    touches = (

        result.get(
            "high_touches",
            0
        )

        +

        result.get(
            "low_touches",
            0
        )

    )


    reasons = []



    points = 0



    # Score

    if score >= 90:

        points += 3

        reasons.append(
            "high score"
        )


    elif score >= 80:

        points += 2

    else:

        points += 1



    # Confirmation

    if confirmation_score >= 20:

        points += 3

        reasons.append(
            "strong confirmation"
        )


    elif confirmation_score >= 10:

        points += 2


    # Structure

    if touches >= 12:

        points += 2

        reasons.append(
            "many touches"
        )


    elif touches >= 8:

        points += 1



    # Final label


    if points >= 7:

        level = "HIGH"


    elif points >= 4:

        level = "MEDIUM"


    else:

        level = "LOW"



    return {

        "level": level,

        "points": points,

        "reason": ", ".join(
            reasons
        )

    }