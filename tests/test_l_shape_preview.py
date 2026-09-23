"""Narrow checks for the L-shape chart renderer.

Only what this slice claims: index alignment after the context crop, candles
only through the breakout candle, the owner's minimal breakout ray / target /
caption, and no re-detection while rendering. No Scanner, Telegram, Robot,
backend, market data or database is involved.
"""

import inspect
from pathlib import Path

import pytest

import geometry.l_shape as detector_module
import geometry.l_shape_preview as preview_module
from geometry.l_shape import detect_l_shape
from geometry.l_shape_preview import l_shape_caption, render_l_shape_preview

from tests.test_l_shape_detector import _long_shape, _short_shape


def test_drawn_coordinates_map_back_to_the_source_indices(tmp_path: Path):
    candles = _long_shape()
    formation = detect_l_shape(candles)

    drawn = render_l_shape_preview(
        candles, formation, tmp_path / "long.png", context_bars=6,
    )

    offset = drawn["window_start"]
    assert drawn["start_x"] + offset == formation.start_index
    assert drawn["extreme_x"] + offset == formation.extreme_index
    assert drawn["breakout_x"] + offset == formation.breakout_index
    assert drawn["breakout_level"] == formation.breakout_level
    assert drawn["target_level"] == formation.target_level


def test_window_ends_at_the_breakout_candle(tmp_path: Path):
    candles = _short_shape()
    formation = detect_l_shape(candles)

    drawn = render_l_shape_preview(
        candles, formation, tmp_path / "short.png", context_bars=6,
    )

    assert drawn["window_start"] <= formation.impulse_start_index
    assert drawn["window_end"] == formation.breakout_index
    assert drawn["context_bars_before_start"] == 6
    assert drawn["ray_right_x"] > drawn["breakout_x"]
    assert (tmp_path / "short.png").stat().st_size > 5_000


def test_caption_is_ticker_timeframe_arrow_name_potential():
    long_formation = detect_l_shape(_long_shape())
    short_formation = detect_l_shape(_short_shape())

    assert l_shape_caption("TESTUSDT", "5", long_formation) == (
        "TESTUSDT · 5м · ↑ Г-образная (+{:.2f}%)".format(
            long_formation.potential_percent)
    )
    assert l_shape_caption("TESTUSDT", "5", short_formation).startswith(
        "TESTUSDT · 5м · ↓ Г-образная (-"
    )


def test_removed_annotations_are_not_drawn():
    source = inspect.getsource(preview_module)
    for removed in ("START", "полка", "shelf", "2H", "impulse_low", "axvspan"):
        assert removed not in source


def test_rendering_never_detects_again(tmp_path: Path, monkeypatch):
    candles = _long_shape()
    formation = detect_l_shape(candles)

    def _forbidden(*args, **kwargs):
        raise AssertionError("the preview must not run detection")

    monkeypatch.setattr(detector_module, "detect_l_shape", _forbidden)
    monkeypatch.setattr(detector_module, "find_latest_l_shape", _forbidden)

    drawn = render_l_shape_preview(candles, formation, tmp_path / "again.png")

    assert drawn["direction"] == formation.direction
    assert "detect_l_shape" not in inspect.getsource(preview_module)


def test_formation_outside_the_supplied_candles_is_refused(tmp_path: Path):
    candles = _long_shape()
    formation = detect_l_shape(candles)

    with pytest.raises(ValueError):
        render_l_shape_preview(
            candles.iloc[: formation.breakout_index], formation,
            tmp_path / "invalid.png",
        )
