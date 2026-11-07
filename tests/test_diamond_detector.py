"""Diamond #500: causal offline structure only, with negative control patterns."""

from unittest.mock import patch

import pytest

from geometry.diamond import detect_diamond_candidate
from tests.test_broadening_detector import zigzag, FIVE

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
    assert candidate.turn_indices == (96, 108) if not reflection else (108, 96)
    assert candidate.width_first < candidate.width_widest_anchor_pair
    assert candidate.width_last < candidate.width_widest_anchor_pair
    assert not hasattr(candidate, "direction")
    assert not hasattr(candidate, "entry")
    assert not hasattr(candidate, "stop")
    assert not hasattr(candidate, "take")


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
