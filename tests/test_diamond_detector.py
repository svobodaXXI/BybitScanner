"""Diamond #500: causal offline structure only, with negative control patterns."""

from unittest.mock import patch

import pytest

from geometry.diamond import detect_diamond_candidate
from tests.test_broadening_detector import zigzag, FIVE
from pivots import find_pivots

# Confirmed alternating H72-L84-H96-L108-H120-L132; no trade direction.
DIAMOND = [
    (0, 100.0), (60, 100.2),
    (72, 101.0), (84, 99.0), (96, 103.0),
    (108, 97.0), (120, 102.0), (132, 98.5), (144, 100.0),
]


@pytest.mark.parametrize("reflection", [False, True])
def test_single_episode_expands_then_contracts_with_six_confirmed_anchors(reflection):
    prices = [(index, 200.0 - price if reflection else price)
              for index, price in DIAMOND]
    bars = zigzag(prices, 170)
    candidate = detect_diamond_candidate(bars, 135)
    assert candidate is not None
    assert candidate.stage == "OFFLINE_CANDIDATE"
    assert candidate.start_index == 72
    assert [p[0] for p in candidate.anchors] == [72, 84, 96, 108, 120, 132]
    assert candidate.turn_indices == ((96, 108) if not reflection else (108, 96))
    assert candidate.width_first < candidate.width_widest_anchor_pair
    assert candidate.width_last < candidate.width_widest_anchor_pair
    assert not hasattr(candidate, "direction")
    assert not hasattr(candidate, "entry")
    assert not hasattr(candidate, "stop")
    assert not hasattr(candidate, "take")



def test_candidate_line_geometry_is_an_immutable_snapshot():
    bars = zigzag(DIAMOND, 170)
    candidate = detect_diamond_candidate(bars, 135)
    assert candidate is not None
    lines = (
        candidate.expansion_upper, candidate.expansion_lower,
        candidate.contraction_upper, candidate.contraction_lower,
    )
    original = tuple(dict(line) for line in lines)
    for line in lines:
        with pytest.raises(TypeError):
            line["slope"] = 0.0
        with pytest.raises(TypeError):
            line["intercept"] = 999.0
    assert tuple(dict(line) for line in lines) == original
    assert detect_diamond_candidate(bars, 135) == candidate


def test_requires_last_pivot_confirmation_and_ignores_future_bars():
    bars = zigzag(DIAMOND, 170)
    assert detect_diamond_candidate(bars, 134) is None
    as_of = detect_diamond_candidate(bars, 135)
    assert as_of is not None
    truncated = detect_diamond_candidate(bars.iloc[:136].copy(), 135)
    assert as_of == truncated
    changed_future = bars.copy()
    changed_future.loc[136:, "close"] = 9999.0
    changed_future.loc[136:, "high"] = 9999.0
    assert detect_diamond_candidate(changed_future, 135) == as_of


@pytest.mark.parametrize("points", [
    FIVE,  # Existing Horn: continuing expansion, no contracting half.
    [(0, 100), (60, 100.2), (72, 103), (84, 97), (96, 102),
     (108, 98), (120, 101), (132, 99), (144, 100)],  # Triangle-only.
    [(0, 100), (60, 100.2), (72, 101), (84, 99), (96, 101),
     (108, 99), (120, 101), (132, 99), (144, 100)],  # Flat range.
    [(0, 100), (60, 100.2), (72, 101), (84, 99), (96, 104),
     (108, 96), (120, 105), (132, 95), (144, 100)],  # Horn-only.
])
def test_horn_triangle_flat_and_unbroken_expansion_are_not_diamonds(points):
    bars = zigzag(points, 170)
    assert detect_diamond_candidate(bars, 135) is None


def test_extra_same_side_confirmed_pivot_splits_episode():
    bars = zigzag(DIAMOND, 170)
    highs = [
        {"index": i, "price": p} for i, p in
        [(72, 101), (90, 102), (96, 103), (120, 102)]
    ]
    lows = [
        {"index": i, "price": p} for i, p in
        [(84, 99), (108, 97), (132, 98.5)]
    ]
    with patch("geometry.diamond.find_pivots", return_value=(highs, lows)):
        assert detect_diamond_candidate(bars, 135) is None


def test_empty_or_invalid_cutoff_is_rejected():
    bars = zigzag(DIAMOND, 170)
    assert detect_diamond_candidate(None) is None
    assert detect_diamond_candidate(bars, -1) is None
    assert detect_diamond_candidate(bars, len(bars)) is None
    assert detect_diamond_candidate(bars, True) is None


def test_malformed_source_bars_inside_diamond_are_rejected_even_with_good_pivots():
    bars = zigzag(DIAMOND, 170)
    good_pivots = find_pivots(bars.iloc[:136].copy())
    assert detect_diamond_candidate(bars, 135) is not None
    for bad_row in (
        {"open": float("nan")},
        {"high": float("inf")},
        {"high": 0.01},
        {"low": -1.0},
        {"open": 200.0},
    ):
        corrupt = bars.copy()
        for key, value in bad_row.items():
            corrupt.loc[80, key] = value
        # Isolate the OHLC safety check from pivot-find filtering: an
        # apparently valid six-pivot skeleton must never excuse bad candles.
        with patch("geometry.diamond.find_pivots", return_value=good_pivots):
            assert detect_diamond_candidate(corrupt, 135) is None


def test_sustained_body_breach_in_expansion_invalidates_six_pivot_skeleton():
    bars = zigzag(DIAMOND, 170)
    good_pivots = find_pivots(bars.iloc[:136].copy())
    assert detect_diamond_candidate(bars, 135) is not None

    uncontained = bars.copy()
    # The expanding upper line is 101 at H72, rising to 103 at H96.
    # Eight successive *real bodies* above it are an incoherent episode,
    # even if a separately supplied pivot list still looks diamond-shaped.
    for index in range(74, 82):
        uncontained.loc[index, ["open", "high", "low", "close"]] = [
            102.50, 102.80, 100.80, 102.65,
        ]
    with patch("geometry.diamond.find_pivots", return_value=good_pivots):
        assert detect_diamond_candidate(uncontained, 135) is None


def test_unclosed_future_bad_data_outside_decision_prefix_cannot_affect_result():
    bars = zigzag(DIAMOND, 170)
    reference = detect_diamond_candidate(bars, 135)
    assert reference is not None
    later = bars.copy()
    later.loc[136:, "open"] = float("nan")
    later.loc[136:, "high"] = -100.0
    assert detect_diamond_candidate(later, 135) == reference
