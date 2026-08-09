"""
geometry.engine

Главный модуль Geometry Engine.

Собирает геометрические кандидаты
и выбирает лучшую валидированную модель структуры.

Pipeline:

Pivot Points
↓
Candidate Engine
↓
Candidate Filtering
↓
Candidate Pairs
↓
Geometry Evaluation
↓
Validation Gate
↓
Geometry Ranking
↓
Validated Geometry Model

Не содержит:

- Score;
- Signal;
- Telegram;
- торговых решений.
"""

from .candidate import (
    build_candidate_lines
)

from .filter import (
    filter_candidates
)

from .evaluation import (
    evaluate_candidate_pair
)

from .ranking import (
    rank_geometry
)

from .debug.logger import (
    debug
)


def analyze_geometry(
    highs,
    lows
):
    """
    Главная функция анализа геометрии.

    Принимает:

    highs:
        Pivot High точки

    lows:
        Pivot Low точки

    Возвращает:

        лучшую валидированную
        геометрическую модель.
    """

    if (
        len(highs) < 4
        or
        len(lows) < 4
    ):
        return None

    #
    # 1. Candidate generation
    #

    upper_candidates = build_candidate_lines(
        highs
    )

    lower_candidates = build_candidate_lines(
        lows
    )

    debug(
        "GEOMETRY",
        {
            "raw_upper":
                len(upper_candidates),

            "raw_lower":
                len(lower_candidates)
        }
    )

    #
    # 2. Candidate filtering
    #

    upper_candidates = filter_candidates(
        upper_candidates
    )

    lower_candidates = filter_candidates(
        lower_candidates
    )

    debug(
        "GEOMETRY",
        {
            "filtered_upper":
                len(upper_candidates),

            "filtered_lower":
                len(lower_candidates)
        }
    )

    if (
        not upper_candidates
        or
        not lower_candidates
    ):
        return None

    #
    # 3. Evaluation всех пар
    #

    best_geometry = None
    best_score = -999

    for upper_candidate in upper_candidates:

        for lower_candidate in lower_candidates:

            geometry = evaluate_candidate_pair(
                upper_candidate,
                lower_candidate
            )

            if geometry is None:
                continue

            #
            # 4. Validation Gate
            #
            # Только валидированная геометрия
            # допускается к Ranking.
            #

            validation = getattr(
                geometry,
                "validation",
                {}
            )

            if not validation.get(
                "valid",
                False
            ):
                continue

            #
            # 5. Geometry Ranking
            #
            # Только качество геометрии.
            # Не торговый Score.
            #

            geometry_score = rank_geometry(
                geometry
            )

            if geometry_score > best_score:

                best_score = geometry_score
                best_geometry = geometry

    #
    # 6. Только валидированная модель
    #

    return best_geometry
