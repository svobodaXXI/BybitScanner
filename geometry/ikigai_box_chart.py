"""Presentation-only chart of one frozen Ikigai Box setup.

This is the image renderer intended for Scanner/Telegram integration. It does
not detect a new setup, place orders, or infer an unapproved four-LIMIT grid.
"""

from pathlib import Path
from math import isfinite

import matplotlib as mpl

# The Scanner runs on a background thread. Select the headless backend BEFORE
# importing pyplot or mplfinance (see chart_clean.py).
mpl.use("Agg")
mpl.rcParams["font.family"] = "DejaVu Sans"
mpl.rcParams["axes.unicode_minus"] = False

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from timeframe_format import format_timeframe_ru
from geometry.ikigai_box import IkigaiBoxWatch


def fibonacci_chart_levels(formation):
    """Price coordinates fixed by the FIRST impulse: 0=A, 1=B."""
    return (
        (0.0, formation.anchor_start_price),
        (1.0, formation.fibonacci_1_0),
        (1.618, formation.fibonacci_1_618),
        (2.618, formation.fibonacci_2_618),
    )


# Mirror of the terminal Fibonacci drawing tool (the source of truth):
#   terminal/frontend/src/chart/drawingModel.ts  -> FIBONACCI_LEVELS,
#       fibonacciPrices (first + (second - first) * level), fibonacciBands
#       (one band between every ADJACENT pair of levels, in level order);
#   terminal/frontend/src/chart/DrawingOverlay.tsx -> band palette (cycled by
#       band index), line colour and the "level  price" label form.
# Here first = A (F0) and second = B (F1), so prices equal the frozen
# ``formation.fibonacci_price(level)``; nothing is recalculated.
TERMINAL_FIBONACCI_LEVELS = (
    0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.618, 2.618, 3.618, 4.236,
)
TERMINAL_BAND_RGB = (
    (59, 198, 57), (92, 156, 196), (224, 180, 91), (150, 112, 196),
    (205, 77, 90),
)
# The terminal fills at 8% on a dark canvas; lifted for a white PNG.
TERMINAL_BAND_ALPHA = 0.18
TERMINAL_LINE_COLOR = "#e0b45b"
TERMINAL_LINE_WIDTH = 1.5


def terminal_fibonacci_levels(formation):
    """All terminal levels as (level, price) from the frozen first impulse."""
    return tuple(
        (level, formation.fibonacci_price(level))
        for level in TERMINAL_FIBONACCI_LEVELS
    )


def fibonacci_band_ranges(levels):
    """[(from_level, to_level, low_price, high_price)] for ADJACENT levels."""
    return [
        (a_level, b_level, min(a_price, b_price), max(a_price, b_price))
        for (a_level, a_price), (b_level, b_price) in zip(levels, levels[1:])
    ]


def _draw_fibonacci_bands(ax, levels, x_left, x_right):
    """Translucent terminal-palette bands over the formation x-range."""
    from matplotlib.patches import Rectangle

    for number, (_, _, low, high) in enumerate(fibonacci_band_ranges(levels)):
        red, green, blue = TERMINAL_BAND_RGB[number % len(TERMINAL_BAND_RGB)]
        ax.add_patch(Rectangle(
            (x_left, low), x_right - x_left, high - low,
            facecolor=(red / 255, green / 255, blue / 255, TERMINAL_BAND_ALPHA),
            edgecolor="none", zorder=0.5,
        ))


def _draw_terminal_levels(ax, levels, key_levels, x_left, x_right):
    """Draw visible non-key Fibonacci lines without service captions."""
    low_view, high_view = ax.get_ylim()
    for level, price in levels:
        if level in key_levels or not low_view <= price <= high_view:
            continue
        ax.hlines(price, x_left, x_right, colors=TERMINAL_LINE_COLOR,
                  linewidth=TERMINAL_LINE_WIDTH, alpha=0.9)


def _ikigai_box_pattern(formation):
    """Frozen first-impulse direction and F(1.0) -> F(1.618) potential."""
    up = formation.anchor_end_price > formation.anchor_start_price
    arrow = "↑" if up else "↓"
    potential_pct = (
        abs(formation.fibonacci_1_618 - formation.fibonacci_1_0)
        / formation.fibonacci_1_0 * 100
    )
    sign = "+" if up else "-"
    return f"{arrow} Коробка Икигаи ({sign}{potential_pct:.2f}%)"


def ikigai_box_caption(symbol, timeframe, formation):
    """Compact chart title using the frozen Box presentation values."""
    return (
        f"{symbol} · {format_timeframe_ru(timeframe)} · "
        f"{_ikigai_box_pattern(formation)}"
    )


def ikigai_box_signal_text(symbol, timeframe, formation):
    """Telegram text before the photo; Box has no score or stage circle."""
    return (
        f"📡 Сканер: {symbol}\n"
        f"{_ikigai_box_pattern(formation)}\n"
        f"{format_timeframe_ru(timeframe)}"
    )


def render_ikigai_box_chart(
    candles,
    formation,
    output_path,
    *,
    symbol,
    timeframe,
    context_bars=10,
):
    """Render only candles through formation.as_of_index, never later rows.

    The selected output path is caller-owned. The Scanner will give each
    signal its own path; this renderer never touches <symbol>_analysis.png.
    """
    if type(context_bars) is not int or context_bars < 0:
        raise ValueError("context_bars must be a non-negative integer")
    if formation.direction not in ("LONG", "SHORT"):
        raise ValueError("Unknown Ikigai Box direction")
    if candles is None or any(
        name not in candles.columns
        for name in ("time", "open", "high", "low", "close")
    ):
        raise ValueError("Expected time/open/high/low/close columns")
    end = formation.as_of_index
    if type(end) is not int or not 0 <= end < len(candles):
        raise ValueError("Formation is outside candle data")
    is_watch = isinstance(formation, IkigaiBoxWatch)
    if not (
        0 <= formation.anchor_start_index
        < formation.anchor_end_index
        < formation.box_start_index
        <= formation.box_end_index
        <= end
    ):
        raise ValueError("Invalid frozen Ikigai Box anchor/segment order")
    if is_watch:
        if formation.phase == "BOX_READY":
            if formation.first_box_exit_index is not None:
                raise ValueError("BOX_READY cannot have a prior breakout")
        elif formation.phase == "BOX_BREAK_OBSERVED":
            if not (
                type(formation.first_box_exit_index) is int
                and formation.box_end_index
                < formation.first_box_exit_index
                <= end
            ):
                raise ValueError("Invalid observed box breakout")
        else:
            raise ValueError("Unknown Ikigai Box WATCH phase")
    elif not (
        formation.box_end_index < formation.second_start_index <= end
        and formation.impulse_start_index == formation.anchor_start_index
        and formation.impulse_end_index == formation.anchor_end_index
    ):
        raise ValueError("Invalid confirmed Ikigai Box segments")
    levels = fibonacci_chart_levels(formation)
    if not all(isfinite(price) and price > 0 for _, price in levels):
        raise ValueError("Invalid frozen Fibonacci price")
    for value, price in levels:
        if not abs(formation.fibonacci_price(value) - price) <= (
            1e-8 * max(1, abs(price))
        ):
            raise ValueError("Inconsistent frozen Fibonacci anchors")
    if (formation.anchor_end_price - formation.anchor_start_price) * (
        1 if formation.direction == "SHORT" else -1
    ) <= 0:
        raise ValueError("Fibonacci direction conflicts with setup")

    offset = max(0, formation.anchor_start_index - context_bars)
    window = candles.iloc[offset : end + 1].copy()
    # DataFrame is deep-copied, so signal rendering cannot mutate Scanner
    # source candles. Time is in Bybit milliseconds, not local chart indices.
    for col in ("time", "open", "high", "low", "close"):
        window[col] = pd.to_numeric(window[col], errors="raise")
        if not window[col].map(isfinite).all():
            raise ValueError("Non-finite OHLC/time in chart window")
    if (window["time"].diff().dropna() <= 0).any():
        raise ValueError("Non-monotonic candle times")
    window.index = (
        pd.to_datetime(window["time"].astype("int64"), unit="ms", utc=True)
        .dt.tz_convert("Europe/Moscow")
        .dt.tz_localize(None)
    )
    window = window[["open", "high", "low", "close"]]
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig = None
    try:
        fig, axes = mpf.plot(
            window,
            type="candle",
            style="charles",
            volume=False,
            # A further 30% narrower than the accepted 7.2-inch canvas;
            # both bodies and visible gaps shrink at the same fixed DPI.
            figsize=(5.04, 7),
            datetime_format="%H:%M",
            ylabel="",
            returnfig=True,
        )
        ax = axes[0]
        start = formation.anchor_start_index - offset
        box_first = formation.box_start_index - offset
        box_last = formation.box_end_index - offset
        last = len(window) - 1

        ax.axvspan(box_first - 0.5, box_last + 0.5, alpha=0.12,
                   color="slateblue", label="Проторговка")
        terminal_levels = terminal_fibonacci_levels(formation)
        _draw_fibonacci_bands(ax, terminal_levels, start - 0.5, last + 0.5)
        for level, price in levels:
            ax.hlines(price, start, last, colors=TERMINAL_LINE_COLOR,
                      linewidth=TERMINAL_LINE_WIDTH, alpha=0.95)
        # Include both target and secondary zone even if not reached yet.
        visible = [float(window["low"].min()), float(window["high"].max())]
        visible += [price for _, price in levels]
        spread = max(visible) - min(visible)
        pad = max(spread * 0.055, formation.anchor_start_price * 0.0001)
        ax.set_ylim(min(visible) - pad, max(visible) + pad)
        ax.set_xlim(-1, len(window) + 0.5)
        _draw_terminal_levels(
            ax, terminal_levels, {level for level, _ in levels}, start, last
        )
        # Owner format 2026-09-23: axis-label text removed; tick values and
        # the time/price scales are unaffected.
        ax.set_xlabel("")
        ax.set_title(ikigai_box_caption(symbol, timeframe, formation), fontsize=12)
        fig.savefig(target, dpi=125, bbox_inches="tight")
    finally:
        if fig is not None:
            plt.close(fig)
    return target
