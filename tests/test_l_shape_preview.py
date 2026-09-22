"""Narrow checks for the L-shape preview renderer.

Only what this slice claims: index alignment after the context crop, the whole
impulse inside the drawn window, and no re-detection while rendering. No
Scanner, Telegram, Robot, backend, market data or database is involved.
"""

import inspect
from pathlib import Path

import pytest

import geometry.l_shape as detector_module
from geometry.l_shape import detect_l_shape
from geometry.l_shape_preview import render_l_shape_preview

from tests.test_l_shape_detector import _long_shape, _short_shape


def test_drawn_coordinates_map_back_to_the_source_indices(tmp_path: Path):
    candles = _long_shape()
    formation = detect_l_shape(candles)
    assert formation is not None

    drawn = render_l_shape_preview(
        candles, formation, tmp_path / "long.png", context_bars=6,
    )

    offset = drawn["window_start"]
    assert drawn["start_x"] + offset == formation.start_index
    assert drawn["impulse_x"][0] + offset == formation.impulse_start_index
    assert drawn["impulse_x"][1] + offset == formation.impulse_end_index
    assert drawn["shelf_x"][0] + offset == formation.shelf_start_index
    assert drawn["shelf_x"][1] + offset == formation.shelf_end_index
    assert drawn["shelf_high"] == formation.shelf_high
    assert drawn["shelf_low"] == formation.shelf_low


def test_window_contains_the_whole_impulse_plus_context(tmp_path: Path):
    candles = _short_shape()
    formation = detect_l_shape(candles)
    assert formation is not None

    drawn = render_l_shape_preview(
        candles, formation, tmp_path / "short.png", context_bars=6,
    )

    assert drawn["window_start"] <= formation.impulse_start_index
    assert drawn["window_end"] >= formation.impulse_end_index
    assert drawn["window_end"] == formation.shelf_end_index
    assert drawn["context_bars_before_start"] == 6
    assert (tmp_path / "short.png").stat().st_size > 5_000


def test_rendering_never_detects_again(tmp_path: Path, monkeypatch):
    candles = _long_shape()
    formation = detect_l_shape(candles)

    def _forbidden(*args, **kwargs):
        raise AssertionError("the preview must not run detection")

    monkeypatch.setattr(detector_module, "detect_l_shape", _forbidden)

    drawn = render_l_shape_preview(candles, formation, tmp_path / "again.png")

    assert drawn["direction"] == formation.direction
    assert "detect_l_shape" not in inspect.getsource(
        __import__("geometry.l_shape_preview", fromlist=["x"])
    )


def test_formation_outside_the_supplied_candles_is_refused(tmp_path: Path):
    candles = _long_shape()
    formation = detect_l_shape(candles)

    with pytest.raises(ValueError):
        render_l_shape_preview(
            candles.iloc[: formation.shelf_start_index], formation,
            tmp_path / "invalid.png",
        )


def test_high_first_target_uses_impulse_high_and_confirmed_shelf_trough(tmp_path: Path):
    """H = the confirmed impulse HIGH, L = the confirmed post-HIGH trough
    (shelf_low) already known at as_of_index (the shelf never reads past
    shelf_end), T = 2*H - L. No Fibonacci drawing exists in this renderer.
    """
    candles = _long_shape()
    formation = detect_l_shape(candles)

    drawn = render_l_shape_preview(candles, formation, tmp_path / "long.png")

    assert drawn["target_high"] == formation.impulse_high
    assert drawn["target_trough"] == formation.shelf_low
    assert drawn["target_level"] == 2 * formation.impulse_high - formation.shelf_low
    assert "fib" not in inspect.getsource(
        __import__("geometry.l_shape_preview", fromlist=["x"])
    ).lower()


def test_low_first_setup_has_no_target_drawn(tmp_path: Path):
    """Scope of this slice: only the HIGH-first (LONG) target formula was
    given. SHORT keeps its existing formation drawing and gets no target.
    """
    candles = _short_shape()
    formation = detect_l_shape(candles)

    drawn = render_l_shape_preview(candles, formation, tmp_path / "short.png")

    assert drawn["target_high"] is None
    assert drawn["target_trough"] is None
    assert drawn["target_level"] is None
