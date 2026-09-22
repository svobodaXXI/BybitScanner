"""
geometry.l_shape_preview

Small independent preview renderer for an already detected L-shaped formation
(``geometry.l_shape.LShapeFormation``).

It deliberately does NOT detect anything: the formation is passed in, so the
picture can never disagree with the detector that produced it. Wedge rendering
in ``chart_clean.py`` is untouched and nothing here is wired into Scanner,
Telegram, Robot or any trading path.

Source candle indices stay authoritative: the window is cropped for context and
every drawn coordinate is translated by the same single offset, so START, the
impulse span and the shelf boundaries cannot drift by one bar.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")           # headless: same choice chart_clean.py already makes

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

CAPTION = "Г-образная формация"
DIRECTION_LABELS = {"LONG": "LONG (импульс вверх, полка у максимума)",
                    "SHORT": "SHORT (импульс вниз, полка у минимума)"}

IMPULSE_COLOR = "#1f77b4"
SHELF_COLOR = "#d62728"
START_COLOR = "#ff7f0e"
TARGET_COLOR = "#2ca02c"


def _moscow_index(frame):
    """Same timestamp convention as chart_clean.py: MSK, tz-naive."""
    return (
        pd.to_datetime(frame["time"].astype("int64"), unit="ms", utc=True)
        .dt.tz_convert("Europe/Moscow")
        .dt.tz_localize(None)
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
    if formation.shelf_end_index >= total or formation.start_index < 0:
        raise ValueError("formation indices are outside the supplied candles")

    window_start = max(0, formation.start_index - context_bars)
    window_end = formation.shelf_end_index
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
        figsize=(12, 7),
        datetime_format="%H:%M",
        returnfig=True,
    )
    ax = axes[0]
    ax.set_xlabel("МСК")

    long_side = formation.direction == "LONG"

    # --- the whole impulse, start to end -------------------------------------
    ax.axvspan(
        x(formation.impulse_start_index) - 0.5,
        x(formation.impulse_end_index) + 0.5,
        color=IMPULSE_COLOR, alpha=0.08, zorder=0,
    )
    ax.plot(
        [x(formation.impulse_start_index), x(formation.impulse_extreme_index)],
        [
            formation.impulse_low if long_side else formation.impulse_high,
            formation.impulse_high if long_side else formation.impulse_low,
        ],
        color=IMPULSE_COLOR, linewidth=2.0, zorder=3,
    )

    # --- shelf boundaries, only over the shelf span --------------------------
    shelf_left = x(formation.shelf_start_index)
    shelf_right = x(formation.shelf_end_index)
    for level in (formation.shelf_high, formation.shelf_low):
        ax.hlines(
            level, shelf_left - 0.5, shelf_right + 0.5,
            color=SHELF_COLOR, linewidth=1.8, zorder=4,
        )
    ax.fill_between(
        [shelf_left - 0.5, shelf_right + 0.5],
        formation.shelf_low, formation.shelf_high,
        color=SHELF_COLOR, alpha=0.10, zorder=1,
    )
    ax.text(
        shelf_right, formation.shelf_high, " полка",
        color=SHELF_COLOR, fontsize=9, va="bottom", ha="left", zorder=5,
    )

    # --- START at the beginning of the impulse -------------------------------
    start_price = (
        formation.impulse_low if long_side else formation.impulse_high
    )
    ax.scatter(
        [x(formation.start_index)], [start_price],
        color=START_COLOR, s=90, zorder=6,
    )
    ax.text(
        x(formation.start_index), start_price, " START",
        color=START_COLOR, fontsize=10, fontweight="bold",
        va="top" if long_side else "bottom", ha="left", zorder=6,
    )

    # --- HIGH-first target projection (LONG only) ----------------------------
    # H = the confirmed impulse HIGH; L = formation.shelf_low, the confirmed
    # post-HIGH trough already known at as_of_index (the shelf is read only up
    # to shelf_end == as_of_index, so this is never inferred from a later bar).
    # T = 2*H - L projects the same distance above H that the shelf retraced
    # below it. No SHORT/LOW-first mirror is drawn: that target formula was
    # not specified for this slice.
    target_high = None
    target_trough = None
    target_level = None
    if long_side:
        target_high = formation.impulse_high
        target_trough = formation.shelf_low
        target_level = 2 * target_high - target_trough

        ray_right = x(formation.shelf_end_index) + projection_bars
        ax.hlines(
            target_high,
            x(formation.impulse_extreme_index), ray_right,
            color=IMPULSE_COLOR, linewidth=1.5, linestyle="--", zorder=4,
        )
        ax.text(
            ray_right, target_high, " H", color=IMPULSE_COLOR,
            fontsize=9, va="bottom", ha="right", zorder=5,
        )
        ax.hlines(
            target_level,
            x(formation.shelf_end_index), ray_right,
            color=TARGET_COLOR, linewidth=1.8, zorder=4,
        )
        ax.text(
            ray_right, target_level, " T = 2H-L", color=TARGET_COLOR,
            fontsize=9, fontweight="bold", va="bottom", ha="right", zorder=5,
        )

    header = CAPTION
    if symbol:
        header = "{} · {}".format(symbol, header)
    if timeframe:
        header = "{} · {}м".format(header, timeframe)
    ax.set_title(
        "{}\n{}\nимпульс {} ATR · полка {} баров · откат {:.0%} размаха".format(
            header,
            DIRECTION_LABELS.get(formation.direction, formation.direction),
            round(formation.impulse_atr_multiple, 1),
            formation.shelf_end_index - formation.shelf_start_index + 1,
            formation.shelf_retrace_fraction,
        )
    )

    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)

    return {
        "output_path": str(output_path),
        "window_start": window_start,
        "window_end": window_end,
        "context_bars_before_start": formation.start_index - window_start,
        "start_x": x(formation.start_index),
        "impulse_x": (x(formation.impulse_start_index), x(formation.impulse_end_index)),
        "shelf_x": (shelf_left, shelf_right),
        "shelf_high": formation.shelf_high,
        "shelf_low": formation.shelf_low,
        "direction": formation.direction,
        "target_high": target_high,
        "target_trough": target_trough,
        "target_level": target_level,
    }
