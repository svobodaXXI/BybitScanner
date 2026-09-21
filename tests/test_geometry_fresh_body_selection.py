"""Focused regression for fresh, body-contained candidate selection."""

from types import SimpleNamespace
from unittest.mock import patch

from geometry.engine import analyze_geometry


def _candidate(mode, score, breaches, anchor):
    return SimpleNamespace(
        validation={"valid": True},
        pair_metrics={"geometry_mode": mode},
        envelope_metrics={
            "body_zone_breaches": {
                "upper_body_breach_indices": list(range(breaches)),
                "lower_body_breach_early_indices": [],
                "lower_body_breach_late_indices": [],
            }
        },
        upper_line={"anchor_index": anchor, "slope": 1.0},
        lower_line={"anchor_index": anchor, "slope": 2.0},
        current_index=199,
    )


def _select(candidates, fresh=lambda geometry: True):
    with (
        patch("geometry.engine.build_candidate_lines", side_effect=[
            [{"line": 1}], [{"line": 2}]
        ]),
        patch("geometry.engine.filter_candidates", side_effect=lambda values: values),
        patch("geometry.engine.evaluate_candidate_pair", side_effect=candidates),
        patch("geometry.engine.rank_geometry", side_effect=lambda geometry: geometry.score),
    ):
        return analyze_geometry(
            [None] * 4, [None] * 4,
            freshness_predicate=fresh,
        )


def test_fresh_exploratory_prefers_zero_breaches_over_higher_score():
    stale = _candidate("EXPLORATORY", 300, 0, 12)
    dirty = _candidate("EXPLORATORY", 236.746, 49, 20)
    clean = _candidate("EXPLORATORY", 226.579, 0, 156)
    for geometry in (stale, dirty, clean):
        geometry.score = geometry.pair_metrics.get("score", 0)
    stale.score, dirty.score, clean.score = 300, 236.746, 226.579
    # Give the engine three candidate pairs without invoking market data.
    with (
        patch("geometry.engine.build_candidate_lines", side_effect=[
            [{"line": 1}], [{"line": 2}, {"line": 3}, {"line": 4}]
        ]),
        patch("geometry.engine.filter_candidates", side_effect=lambda values: values),
        patch("geometry.engine.evaluate_candidate_pair", side_effect=[stale, dirty, clean]),
        patch("geometry.engine.rank_geometry", side_effect=lambda geometry: geometry.score),
    ):
        result = analyze_geometry(
            [None] * 4, [None] * 4,
            freshness_predicate=lambda geometry: geometry is not stale,
        )
    assert result is clean


def test_canonical_priority_is_preserved():
    canonical = _candidate("CANONICAL", 227.2285, 0, 156)
    exploratory = _candidate("EXPLORATORY", 300, 0, 20)
    canonical.score, exploratory.score = 227.2285, 300
    with (
        patch("geometry.engine.build_candidate_lines", side_effect=[
            [{"line": 1}], [{"line": 2}, {"line": 3}]
        ]),
        patch("geometry.engine.filter_candidates", side_effect=lambda values: values),
        patch("geometry.engine.evaluate_candidate_pair", side_effect=[exploratory, canonical]),
        patch("geometry.engine.rank_geometry", side_effect=lambda geometry: geometry.score),
    ):
        result = analyze_geometry(
            [None] * 4, [None] * 4,
            freshness_predicate=lambda geometry: True,
        )
    assert result is canonical


def test_all_stale_pool_still_returns_geometry():
    """No fresh candidate: keep pre-change behaviour instead of dropping
    geometry, so the detector still receives it and reports detected=False
    itself. Ranking among the stale pool stays (mode_priority, score)."""

    low = _candidate("EXPLORATORY", 100, 0, 20)
    high = _candidate("EXPLORATORY", 200, 7, 156)
    low.score, high.score = 100, 200
    with (
        patch("geometry.engine.build_candidate_lines", side_effect=[
            [{"line": 1}], [{"line": 2}, {"line": 3}]
        ]),
        patch("geometry.engine.filter_candidates", side_effect=lambda values: values),
        patch("geometry.engine.evaluate_candidate_pair", side_effect=[low, high]),
        patch("geometry.engine.rank_geometry", side_effect=lambda geometry: geometry.score),
    ):
        result = analyze_geometry(
            [None] * 4, [None] * 4,
            freshness_predicate=lambda geometry: False,
        )
    assert result is high
