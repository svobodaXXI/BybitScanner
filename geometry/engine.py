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


# A candidate may span at most this share of the analysed window. A structure
# stretched across almost the whole window is not a local formation; it only
# passes the span-proportional freshness gate because it is long.
GEOMETRY_MAX_STRUCTURE_SPAN_RATIO = 0.60

# One complete current pivot observation context: 3 left + center + 3 right.
# Explicit bounded rule, NOT automatically coupled to pivot configuration.
# Historical winners are stable for cutoffs 4..8; see the owning decision.
GEOMETRY_MAX_BODY_BREACH_RUN = 7


def _body_zone_breach_count(
    geometry
):
    """Count measured own-anchor..END breaches for the existing selection key.

    Legacy candle-free callers/stubs retain the old diagnostic count when the
    new measurement is unavailable; that is not a measured clean-envelope claim.
    """

    envelope_metrics = getattr(
        geometry,
        "envelope_metrics",
        {}
    ) or {}

    formation_fit = envelope_metrics.get("formation_body_fit")
    if formation_fit is not None:
        return sum(
            len(formation_fit[side]["body_breach_indices"])
            for side in ("upper", "lower")
        )

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


def _is_candidate_local(
    geometry,
    current_index
):
    """
    Locality admission: span (end_index - start_index) must not exceed
    GEOMETRY_MAX_STRUCTURE_SPAN_RATIO of the analysed window
    (current_index + 1 bars).

    Uses only the existing start/end indices; no new tolerance or metric.
    A candidate without indices is not admitted. Without current_index the
    window length is unknown and the gate is not applied.
    """

    if current_index is None:
        return True

    start_index = getattr(geometry, "start_index", None)
    end_index = getattr(geometry, "end_index", None)

    if start_index is None or end_index is None:
        return False

    max_span = round(
        (current_index + 1)
        * GEOMETRY_MAX_STRUCTURE_SPAN_RATIO
    )

    return (end_index - start_index) <= max_span


def _is_boundary_structurally_valid(geometry):
    """Reject sustained body mismatch, never an isolated candle or post-END break.

    The shared evaluator already scopes each side to its own anchor..END.
    This replaces #180's independent pivot-plus-body veto: a confirmed outside
    pivot is neither required nor sufficient. No rescue of an emptied pool.
    Optional candle-free Geometry calls have no new body assessment.
    """
    envelope = getattr(geometry, "envelope_metrics", {}) or {}
    fit = envelope.get("formation_body_fit")
    if fit is None:
        return True
    return all(
        fit[side]["max_consecutive_breaches"] < GEOMETRY_MAX_BODY_BREACH_RUN
        for side in ("upper", "lower")
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
            # 4b. Locality admission
            #
            # A non-local candidate never enters the pool, and there is no
            # fallback to it: an empty pool means no geometry.
            #

            if not _is_candidate_local(
                geometry,
                current_index
            ):
                continue

            #
            # 4c. Boundary-validity admission
            #
            # Sustained body mismatch on either own-anchor..END interval
            # rejects the pair. Isolated excursions and post-END breakouts
            # cannot independently invalidate a formation.
            #

            if not _is_boundary_structurally_valid(
                geometry
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
    # Order: CANONICAL first (unchanged), then fewer own-anchor..END body breaches,
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
