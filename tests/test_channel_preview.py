"""Offline regression for initial four-pivot channel projections (#490)."""

from unittest.mock import patch

import pytest

from geometry.channel_preview import compare_channel_preview, observe_four_pivot_channel
from tests.test_broadening_detector import FIVE, FOUR, zigzag


@pytest.mark.parametrize("points,expected", [
    (FOUR, "DIVERGING"),
    ([(0, 100), (60, 100.2), (72, 104), (84, 96),
      (96, 103), (108, 97), (120, 100)], "CONVERGING"),
    ([(0, 100), (60, 100.2), (72, 105), (84, 100),
      (96, 105), (108, 100), (120, 101)], "PARALLEL_HORIZONTAL"),
    ([(0, 100), (60, 100.2), (72, 105), (84, 100),
      (96, 104), (108, 99), (120, 101)], "PARALLEL_TILTED"),
])
def test_four_pivots_immediately_project_two_boundaries(points, expected):
    bars = zigzag(points, 121)
    assert observe_four_pivot_channel(bars, 110) is None
    preview = observe_four_pivot_channel(bars, 111)
    assert preview is not None
    assert preview.stage == "PROVISIONAL_OBSERVATION"
    assert preview.geometry_relation == expected
    assert [p[0] for p in preview.anchor_identity] == [72, 84, 96, 108]
    assert len(preview.anchor_identity) == 4
    upper, lower = preview.project(130)
    assert upper > lower
    assert not {"direction", "entry", "take", "stop", "order"} & vars(preview).keys()


def test_as_of_is_causal_and_snapshot_identity_is_explicit():
    bars = zigzag(FOUR, 140)
    first = observe_four_pivot_channel(bars, 111)
    assert first is not None
    assert first == observe_four_pivot_channel(bars.iloc[:112].copy(), 111)
    corrupted_future = bars.copy()
    corrupted_future.loc[112:, "close"] = 9999
    corrupted_future.loc[112:, "high"] = 9999
    assert observe_four_pivot_channel(corrupted_future, 111) == first
    assert first.anchor_identity == tuple(first.anchor_identity)


def test_bad_cutoff_corrupt_ohlc_and_crossing_lines_rejected():
    bars = zigzag(FOUR, 140)
    assert observe_four_pivot_channel(None) is None
    assert observe_four_pivot_channel(bars, True) is None
    assert observe_four_pivot_channel(bars, -1) is None
    assert observe_four_pivot_channel(bars, len(bars)) is None
    bad = bars.copy()
    bad.loc[85, "high"] = float("nan")
    assert observe_four_pivot_channel(bad, 111) is None
    bad = bars.copy()
    bad.loc[85, "high"] = bad.loc[85, "low"] - 1
    assert observe_four_pivot_channel(bad, 111) is None

    # High/low lines cross at or before the decision cutoff: no channel.
    crossing = [
        {"index": 72, "price": 101.0}, {"index": 96, "price": 97.0}
    ]
    lows = [{"index": 84, "price": 99.0}, {"index": 108, "price": 103.0}]
    with patch("geometry.channel_preview.find_pivots", return_value=(crossing, lows)):
        assert observe_four_pivot_channel(bars, 111) is None


def test_non_alternating_or_split_wave_is_not_a_four_pivot_channel():
    bars = zigzag(FOUR, 140)
    highs = [{"index": 72, "price": 101.0}, {"index": 84, "price": 102.0}]
    lows = [{"index": 96, "price": 99.0}, {"index": 108, "price": 97.0}]
    with patch("geometry.channel_preview.find_pivots", return_value=(highs, lows)):
        assert observe_four_pivot_channel(bars, 111) is None


def test_reflection_preserves_relation_without_trade_bias():
    points = [(index, 200 - price) for index, price in FOUR]
    preview = observe_four_pivot_channel(zigzag(points, 121), 111)
    assert preview is not None
    assert preview.geometry_relation == "DIVERGING"
    assert [p[1] for p in preview.anchor_identity] == ["L", "H", "L", "H"]


def test_followup_retains_exact_four_anchors_until_new_confirmed_pivot():
    bars = zigzag(FIVE, 140)
    original = observe_four_pivot_channel(bars, 111)
    assert original is not None
    first = compare_channel_preview(original, bars, 113)
    assert first is not None
    assert first.status == "SAME_ANCHORS_PROVISIONAL"
    assert first.original_identity == first.current_identity == original.anchor_identity
    assert first.body_breach_indices == ()
    # The new fifth confirmed pivot is a NEW identity requiring explicit
    # review, not an automatic rewrite of lines/START on the original record.
    renewed = compare_channel_preview(original, bars, 123)
    assert renewed is not None
    assert renewed.status == "NEW_ANCHORS_REVIEW_REQUIRED"
    assert renewed.original_identity == original.anchor_identity
    assert renewed.current_identity is not None
    assert renewed.current_identity != renewed.original_identity
    assert original.anchor_identity == first.original_identity
    assert original.as_of_index == 111


def test_followup_wick_only_is_not_body_breach_and_body_cross_is_diagnostic():
    bars = zigzag(FIVE, 140)
    original = observe_four_pivot_channel(bars, 111)
    assert original is not None
    wick = bars.copy()
    wick.loc[112, "high"] = 1000.0  # Unconfirmed wick; do not treat as body.
    observed = compare_channel_preview(original, wick, 113)
    assert observed is not None
    assert observed.status == "SAME_ANCHORS_PROVISIONAL"
    assert not observed.body_breach_indices

    breached = bars.copy()
    upper, _ = original.project(112)
    breached.loc[112, "open"] = upper + 1.0
    breached.loc[112, "close"] = upper + 2.0
    breached.loc[112, "high"] = upper + 2.5
    breached.loc[112, "low"] = upper + 0.9
    observed = compare_channel_preview(original, breached, 113)
    assert observed is not None
    assert observed.status == "BODY_BREACH_OBSERVED"
    assert observed.body_breach_indices == (112,)
    # A body crossing is evidence, NOT a trade signal/automatic invalidation.
    assert not {"entry", "stop", "take", "order"} & vars(observed).keys()


def test_followup_ignores_future_and_fails_closed_when_unproved():
    bars = zigzag(FIVE, 140)
    original = observe_four_pivot_channel(bars, 111)
    assert original is not None
    full = compare_channel_preview(original, bars, 113)
    assert full == compare_channel_preview(original, bars.iloc[:114].copy(), 113)
    future_changed = bars.copy()
    future_changed.loc[114:, "close"] = 9999.0
    future_changed.loc[114:, "high"] = 9999.0
    assert compare_channel_preview(original, future_changed, 113) == full

    corrupted = bars.copy()
    corrupted.loc[112, "high"] = float("nan")
    unavailable = compare_channel_preview(original, corrupted, 113)
    assert unavailable is not None
    assert unavailable.status == "NOT_PROVEN"
    assert unavailable.current_identity is None
    assert compare_channel_preview(original, bars, 111) is None
    assert compare_channel_preview(original, bars, 110) is None
    assert compare_channel_preview(original, bars, True) is None
