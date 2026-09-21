"""
geometry.engine

Р“Р»Р°РІРЅС‹Р№ РјРѕРґСѓР»СЊ Geometry Engine.

РЎРѕР±РёСЂР°РµС‚ РіРµРѕРјРµС‚СЂРёС‡РµСЃРєРёРµ РєР°РЅРґРёРґР°С‚С‹
Рё РІС‹Р±РёСЂР°РµС‚ Р»СѓС‡С€СѓСЋ РІР°Р»РёРґРёСЂРѕРІР°РЅРЅСѓСЋ РјРѕРґРµР»СЊ СЃС‚СЂСѓРєС‚СѓСЂС‹.

Pipeline:

Pivot Points
в†“
Candidate Engine
в†“
Candidate Filtering
в†“
Candidate Pairs
в†“
Geometry Evaluation
в†“
Validation Gate
в†“
Geometry Ranking
в†“
Validated Geometry Model

РќРµ СЃРѕРґРµСЂР¶РёС‚:

- Score;
- Signal;
- Telegram;
- С‚РѕСЂРіРѕРІС‹С… СЂРµС€РµРЅРёР№.
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


def _body_zone_breach_count(
    geometry
):
    """
    Total body-zone breaches already computed for this candidate by
    geometry/envelope_metrics.py:evaluate_body_zone_breaches().

    Read-only reuse: no recomputation, no new tolerance, and no relation
    to wedge.integrity's disabled containment-violation penalty.
    """

    envelope_metrics = getattr(
        geometry,
        "envelope_metrics",
        {}
    ) or {}

    breaches = (
        envelope_metrics.get(
            "body_zone_breaches"
        )
        or {}
    )

    return (
        len(breaches.get("upper_body_breach_indices") or [])
        + len(breaches.get("lower_body_breach_early_indices") or [])
        + len(breaches.get("lower_body_breach_late_indices") or [])
    )


def _is_candidate_fresh(
    geometry,
    freshness_predicate
):
    """
    Apply the INJECTED Pattern-layer freshness predicate to one candidate.

    Geometry never imports Wedge; wedge/analyzer.py supplies the predicate.
    Without a predicate every candidate stays eligible (previous behavior).
    """

    if freshness_predicate is None:
        return True

    apex = (
        getattr(
            geometry,
            "apex",
            None
        )
        or {}
    )

    apex_index = (
        apex.get("index")
        if isinstance(apex, dict)
        else None
    )

    return bool(
        freshness_predicate(
            getattr(geometry, "start_index", None),
            getattr(geometry, "end_index", None),
            apex_index,
            getattr(geometry, "current_index", None)
        )
    )


def analyze_geometry(
    highs,
    lows,
    current_index=None,
    candles=None,
    freshness_predicate=None
):
    """
    Р“Р»Р°РІРЅР°СЏ С„СѓРЅРєС†РёСЏ Р°РЅР°Р»РёР·Р° РіРµРѕРјРµС‚СЂРёРё.

    РџСЂРёРЅРёРјР°РµС‚:

    highs:
        Pivot High С‚РѕС‡РєРё

    lows:
        Pivot Low С‚РѕС‡РєРё

    current_index:
        РёРЅРґРµРєСЃ РїРѕСЃР»РµРґРЅРµР№ РґРѕСЃС‚СѓРїРЅРѕР№
        СЂС‹РЅРѕС‡РЅРѕР№ СЃРІРµС‡Рё

    Р’РѕР·РІСЂР°С‰Р°РµС‚:

        Р»СѓС‡С€СѓСЋ РІР°Р»РёРґРёСЂРѕРІР°РЅРЅСѓСЋ
        РіРµРѕРјРµС‚СЂРёС‡РµСЃРєСѓСЋ РјРѕРґРµР»СЊ.
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
    # 3. Evaluation РІСЃРµС… РїР°СЂ
    #

    ranked_candidates = []

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
            # РўРѕР»СЊРєРѕ РІР°Р»РёРґРёСЂРѕРІР°РЅРЅР°СЏ РіРµРѕРјРµС‚СЂРёСЏ
            # РґРѕРїСѓСЃРєР°РµС‚СЃСЏ Рє Ranking.
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
            # РўРѕР»СЊРєРѕ РєР°С‡РµСЃС‚РІРѕ РіРµРѕРјРµС‚СЂРёРё.
            # РќРµ С‚РѕСЂРіРѕРІС‹Р№ Score.
            #

            geometry_score = rank_geometry(
                geometry
            )

            pair_metrics = getattr(
                geometry,
                "pair_metrics",
                {}
            ) or {}

            geometry_mode = pair_metrics.get(
                "geometry_mode",
                "EXPLORATORY"
            )

            mode_priority = (
                1
                if geometry_mode == "CANONICAL"
                else 0
            )

            ranked_candidates.append(
                {
                    "geometry":
                        geometry,

                    "mode_priority":
                        mode_priority,

                    "body_breaches":
                        _body_zone_breach_count(
                            geometry
                        ),

                    "score":
                        geometry_score,

                    "fresh":
                        _is_candidate_fresh(
                            geometry,
                            freshness_predicate
                        )
                }
            )

    #
    # 5b. Eligibility and selection
    #
    # Stale candidates are excluded BEFORE ranking so a clean-but-stale
    # structure can never displace a fresh one. If nothing is fresh, the
    # unfiltered pool is kept so downstream detection keeps reporting the
    # same geometry with detected=False instead of losing it entirely.
    #
    # Order: CANONICAL first (unchanged), then fewer body-zone breaches,
    # then the existing geometry_score. Scores are not recalculated.
    #

    eligible_candidates = [
        candidate
        for candidate in ranked_candidates
        if candidate["fresh"]
    ]

    if not eligible_candidates:
        eligible_candidates = ranked_candidates

    best_geometry = None

    if eligible_candidates:

        best_candidate = max(
            eligible_candidates,
            key=lambda candidate: (
                candidate["mode_priority"],
                -candidate["body_breaches"],
                candidate["score"]
            )
        )

        best_geometry = best_candidate["geometry"]
        best_score = best_candidate["score"]

    #
    # 6. РўРѕР»СЊРєРѕ РІР°Р»РёРґРёСЂРѕРІР°РЅРЅР°СЏ РјРѕРґРµР»СЊ
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
