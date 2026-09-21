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

    best_geometry = None
    best_score = -999
    best_mode_priority = -1
    best_body_breaches = float("inf")

    # Fallback used ONLY when no candidate passes freshness, so that a pool
    # without any fresh structure keeps returning geometry exactly as before
    # this change and the detector still decides detected=False itself.
    fallback_geometry = None
    fallback_score = -999
    fallback_mode_priority = -1

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

            # Use the detector's existing freshness decision when supplied by
            # the wedge coordinator; do not impose a second freshness formula.
            if freshness_predicate is not None and not freshness_predicate(geometry):

                stale_score = rank_geometry(geometry)

                stale_mode_priority = (
                    1
                    if (
                        getattr(geometry, "pair_metrics", {}) or {}
                    ).get(
                        "geometry_mode",
                        "EXPLORATORY"
                    ) == "CANONICAL"
                    else 0
                )

                if (
                    stale_mode_priority > fallback_mode_priority
                    or (
                        stale_mode_priority == fallback_mode_priority
                        and stale_score > fallback_score
                    )
                ):

                    fallback_mode_priority = stale_mode_priority
                    fallback_score = stale_score
                    fallback_geometry = geometry

                continue

            body_zones = (
                (getattr(geometry, "envelope_metrics", {}) or {})
                .get("body_zone_breaches") or {}
            )
            body_breaches = sum(
                len(body_zones.get(key) or ())
                for key in (
                    "upper_body_breach_indices",
                    "lower_body_breach_early_indices",
                    "lower_body_breach_late_indices",
                )
            )

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

            if (
                mode_priority > best_mode_priority
                or (
                    mode_priority == best_mode_priority
                    and (
                        body_breaches < best_body_breaches
                        or (
                            body_breaches == best_body_breaches
                            and geometry_score > best_score
                        )
                    )
                )
            ):

                best_mode_priority = mode_priority
                best_score = geometry_score
                best_body_breaches = body_breaches
                best_geometry = geometry

    if best_geometry is None:

        best_geometry = fallback_geometry
        best_score = fallback_score

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
