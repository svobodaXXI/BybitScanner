"""
geometry.l_shape_preview

Small independent chart renderer for an already detected L-shaped formation
(``geometry.l_shape.LShapeFormation``).

It deliberately does NOT detect anything: the formation is passed in, so the
picture can never disagree with the detector that produced it.

Owner presentation (B2USDT 5m, 2026-09-23): only the candles, one rightward
ray at the breakout level H from the local HIGH/LOW candle, one horizontal
target level labelled ``Цель`` with its potential, and a header with ticker,
timeframe, direction arrow before the pattern name and potential. No impulse
diagonal, origin marker, trough outline or formula text.

Source candle indices stay authoritative: only candles through the breakout
(decision) candle are drawn and every coordinate is translated by the same
single offset.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")           # headless: same choice chart_clean.py already makes

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from timeframe_format import format_timeframe_ru

PATTERN_NAME = "Г-образная"

BREAKOUT_COLOR = "#1f77b4"
TARGET_COLOR = "#2ca02c"


def _moscow_index(frame):
    """Same timestamp convention as chart_clean.py: MSK, tz-naive."""
    return (
        pd.to_datetime(frame["time"].astype("int64"), unit="ms", utc=True)
        .dt.tz_convert("Europe/Moscow")
        .dt.tz_localize(None)
    )


def format_potential(formation):
    return "{:+.2f}%".format(formation.potential_percent)


def l_shape_caption(symbol, timeframe, formation):
    """Shared chart/Telegram identity: ticker, timeframe, arrow, name, potential.

    Potential is in parentheses immediately after the pattern name (unified
    Scanner caption format, PR #211/BACKLOG.md); this pattern keeps its own
    single-line ticker/timeframe layout, which predates and is unaffected by
    that rule's "Сканер:"/"Баллы:" template (this pattern has no score)."""
    arrow = "↑" if formation.direction == "LONG" else "↓"
    return "{} · {} · {} {} ({})".format(
        symbol, format_timeframe_ru(timeframe), arrow, PATTERN_NAME,
        format_potential(formation),
    )


def render_l_shape_preview(
    candles,
    formation,
    output_path,
    *,
    context_bars: int = 10,
    projection_bars: int = 10,
    symbol: str = "",
    timeframe: str = "",
):
    """Draw one formation and return the exact coordinates that were used.

    The returned mapping lets a test verify index alignment without parsing the
    image: every ``*_x`` value plus ``window_start`` must equal the matching
    source index of the formation.
    """
    if formation is None:
        raise ValueError("a detected LShapeFormation is required")
    if context_bars < 0:
        raise ValueError("context_bars must not be negative")
    if projection_bars < 0:
        raise ValueError("projection_bars must not be negative")

    total = len(candles)
    if formation.breakout_index >= total or formation.start_index < 0:
        raise ValueError("formation indices are outside the supplied candles")

    window_start = max(0, formation.start_index - context_bars)
    window_end = formation.breakout_index
    frame = candles.iloc[window_start:window_end + 1].copy()
    frame.index = _moscow_index(frame)
    frame = frame[["open", "high", "low", "close"]].astype(float)

    def x(source_index: int) -> int:
        return source_index - window_start

    fig, axes = mpf.plot(
        frame,
        type="candle",
        style="charles",
        volume=False,
        figsize=(7.2, 7),
        datetime_format="%H:%M",
        returnfig=True,
    )
    ax = axes[0]
    ax.set_xlabel("МСК")

    ray_left = x(formation.extreme_index)
    ray_right = x(formation.breakout_index) + projection_bars
    ax.hlines(
        formation.breakout_level, ray_left, ray_right,
        color=BREAKOUT_COLOR, linewidth=1.6, zorder=4,
    )
    target_left = x(formation.breakout_index)
    ax.hlines(
        formation.target_level, target_left, ray_right,
        color=TARGET_COLOR, linewidth=1.8, zorder=4,
    )
    ax.text(
        ray_right, formation.target_level,
        "Цель {}".format(format_potential(formation)),
        color=TARGET_COLOR, fontsize=10, fontweight="bold",
        va="bottom" if formation.direction == "LONG" else "top",
        ha="right", zorder=5,
    )

    visible = [
        float(frame["low"].min()), float(frame["high"].max()),
        formation.breakout_level, formation.target_level,
    ]
    pad = (max(visible) - min(visible)) * 0.05
    ax.set_ylim(min(visible) - pad, max(visible) + pad)
    ax.set_xlim(-1, ray_right + 0.5)

    ax.set_title(l_shape_caption(symbol, timeframe, formation), fontsize=12)

    fig.savefig(output_path, dpi=125, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_path": str(output_path),
        "window_start": window_start,
        "window_end": window_end,
        "context_bars_before_start": formation.start_index - window_start,
        "start_x": x(formation.start_index),
        "extreme_x": ray_left,
        "breakout_x": target_left,
        "ray_right_x": ray_right,
        "direction": formation.direction,
        "breakout_level": formation.breakout_level,
        "target_level": formation.target_level,
    }
