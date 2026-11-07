"""Offline regression for initial four-pivot channel projections (#490)."""

from unittest.mock import patch

import pytest

from geometry.channel_preview import observe_four_pivot_channel
from tests.test_broadening_detector import FOUR, zigzag


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
