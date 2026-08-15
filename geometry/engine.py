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
    lows,
    current_index=None,
    candles=None
):
    """
    Главная функция анализа геометрии.

    Принимает:

    highs:
        Pivot High точки

    lows:
        Pivot Low точки

    current_index:
        индекс последней доступной
        рыночной свечи

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
                lower_candidate,
                highs=highs,
                lows=lows,
                current_index=current_index,
                candles=candles
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

    if best_geometry is not None:

        pair_metrics = getattr(
            best_geometry,
            "pair_metrics",
            {}
        ) or {}

        envelope_metrics = getattr(
            best_geometry,
            "envelope_metrics",
            {}
        ) or {}

        upper_envelope = (
            envelope_metrics.get("upper")
            or {}
        )

        lower_envelope = (
            envelope_metrics.get("lower")
            or {}
        )

        debug(
            "GEOMETRY_BEST",
            {
                "score":
                    best_score,

                "current_index":
                    getattr(
                        best_geometry,
                        "current_index",
                        None
                    ),

                "upper_anchor":
                    best_geometry.upper_line.get(
                        "anchor_index"
                    ),

                "lower_anchor":
                    best_geometry.lower_line.get(
                        "anchor_index"
                    ),

                "upper_slope":
                    best_geometry.upper_line.get(
                        "slope"
                    ),

                "lower_slope":
                    best_geometry.lower_line.get(
                        "slope"
                    ),

                "common_start":
                    pair_metrics.get(
                        "common_start"
                    ),

                "common_span":
                    pair_metrics.get(
                        "common_span"
                    ),

                "shared_span":
                    pair_metrics.get(
                        "shared_structure_span"
                    ),

                "upper_support":
                    upper_envelope.get(
                        "support_count"
                    ),

                "upper_support_span":
                    upper_envelope.get(
                        "support_span"
                    ),

                "lower_support":
                    lower_envelope.get(
                        "support_count"
                    ),

                "lower_support_span":
                    lower_envelope.get(
                        "support_span"
                    )
            }
        )

    return best_geometry