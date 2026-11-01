"""Robot Telegram chart viewport regressions (render-only, no trading)."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

import robot_position_chart as charts
from robot_position_view import PositionView, TradeMarker


def candles(n=300, base=0.032):
    # Flat-ish trade area and explicit trailing open times, as in Scanner.
    return pd.DataFrame([
        {"time": i * 60_000, "open": base + (i % 7) * 0.00001,
         "high": base + (i % 7) * 0.00001 + 0.00003,
         "low": base + (i % 7) * 0.00001 - 0.00003,
         "close": base + (i % 7) * 0.00001 + 0.000005}
        for i in range(n)
    ])


def view(*, stop="0.03186", take="0.03718"):
    return PositionView(
        symbol="KMNOUSDT", direction="LONG", is_open=True,
        quantity=Decimal("1"), average_entry=Decimal("0.03189"),
        stop_price=Decimal(stop), take_price=Decimal(take),
        pattern="MIRROR", chart_candle_minutes=1,
        markers=(TradeMarker(299 * 60_000, Decimal("0.03189"), "Buy", True),),
    )


def test_far_take_does_not_flatten_local_candles():
    data = charts._prepare_candles(candles()).tail(charts.VIEWPORT_CANDLES)
    lower, upper = charts._price_viewport(data, view())
    assert lower < 0.032 < upper
    assert upper < 0.033  # 0.03718 TP must never force a 16%-wide axis


def test_far_stop_does_not_flatten_local_candles():
    data = charts._prepare_candles(candles()).tail(charts.VIEWPORT_CANDLES)
    lower, upper = charts._price_viewport(data, view(stop="0.025", take="0.03205"))
    assert lower > 0.031 and upper < 0.033


def test_close_targets_fit_and_keep_price_axis():
    data = charts._prepare_candles(candles()).tail(charts.VIEWPORT_CANDLES)
    lower, upper = charts._price_viewport(data, view(stop="0.03189", take="0.03205"))
    assert lower < 0.03189 < upper
    assert lower < 0.03205 < upper


def test_photo_labels_far_take_without_second_price_scale():
    labels = []
    original = charts._draw_offscreen_level

    def capture(ax, price, label, color, limits, index):
        labels.append((price, label, limits))
        return original(ax, price, label, color, limits, index)

    with TemporaryDirectory() as root:
        with patch.object(charts, "_draw_offscreen_level", capture):
            out = charts.render_position_chart(view(), candles(), Path(root) / "kmno.png")
        assert out.exists() and out.stat().st_size > 0
    assert ("TP" in [label for _, label, _ in labels])
    assert any(price == 0.03718 and limits[1] < price for price, label, limits in labels if label == "TP")


def test_recent_real_fill_marker_remains_visible():
    plotted = []
    original = charts._draw_marker

    def capture(ax, x, price, side, *, filled):
        plotted.append((x, price, side, filled))
        return original(ax, x, price, side, filled=filled)

    with TemporaryDirectory() as root:
        with patch.object(charts, "_draw_marker", capture):
            charts.render_position_chart(view(), candles(), Path(root) / "marker.png")
    assert plotted == [(len(candles()) - 1, 0.03189, "Buy", True)]
