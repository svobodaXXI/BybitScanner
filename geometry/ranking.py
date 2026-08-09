"""
geometry.ranking

Geometry Ranking Layer.

Оценивает качество геометрической модели.

Не отвечает за:
- торговый Score;
- сигналы;
- Confirmation.
"""


def rank_geometry(
    geometry
):

    if geometry is None:

        return -999


    score = 0


    validation = getattr(
        geometry,
        "validation",
        {}
    )


    compression = getattr(
        geometry,
        "compression",
        {}
    )


    touches = getattr(
        geometry,
        "touches",
        {}
    )


    checks = validation.get(
        "checks",
        {}
    )



    if validation.get(
        "valid",
        False
    ):

        score += 100



    if checks.get(
        "apex",
        {}
    ).get(
        "valid",
        False
    ):

        score += 30



    if compression.get(
        "is_compressing",
        False
    ):

        score += 25



    total_touches = touches.get(
        "total_touches",
        0
    )


    score += min(
        total_touches * 5,
        25
    )



    failed = validation.get(
        "failed_checks",
        []
    )


    score -= len(failed) * 10


    return score