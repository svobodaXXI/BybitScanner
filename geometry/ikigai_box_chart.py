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
from geometry.ikigai_box_overlay import build_trade_overlay


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
    """Terminal-style lines and "level  price" labels for the non-key levels.

    Only levels inside the visible price range are drawn, as the terminal
    clips off-screen levels; the four key levels keep their role captions.
    Labels sit beyond the price-axis tick labels so they never overprint them.
    """
    low_view, high_view = ax.get_ylim()
    for level, price in levels:
        if level in key_levels or not low_view <= price <= high_view:
            continue
        ax.hlines(price, x_left, x_right, colors=TERMINAL_LINE_COLOR,
                  linewidth=TERMINAL_LINE_WIDTH, alpha=0.9)
        ax.text(
            1.115, price, f"{level:g}  {price:.8g}",
            transform=ax.get_yaxis_transform(), clip_on=False, fontsize=8,
            va="center", ha="left", color="#7a5a13",
        )


def _stage_caption(overlay):
    reached = (
        "1.618 БЫЛ ДОСТИГНУТ · сетка 4 × 1/4 РО — схема, НЕ сигнал входа"
        if overlay.level_1_618_reached else
        "1.618 НЕ достигнут · НАБЛЮДЕНИЕ, схема сетки не показана"
    )
    lines = [f"Статус: {overlay.stage} ({overlay.direction})", reached]
    if overlay.stop is not None:
        basis = (
            f"за экстремумом свечи {overlay.stop.anchor_kind}"
            if overlay.stop.basis == "REVERSAL_CANDLE"
            else "запас −1.5% от плановой средней цены входа"
        )
        lines.append(f"STOP план {overlay.stop.price:.8g} · {basis}")
    lines.append(
        f"Цель F(1.0) {overlay.target_price:.8g} · {overlay.partial_take_note}"
    )
    return chr(10).join(lines)


def _draw_trade_overlay(ax, overlay, offset, last):
    """Draw planned grid/STOP/target; returns the prices to keep in view."""
    prices = [overlay.target_price]
    # F(1.0) is annotated once, outside the price axes by the caller.
    # Repeating "TP план" here crowded B and the final box wicks.
    if overlay.grid is None:
        return prices
    grid = overlay.grid
    reach = overlay.first_reach_index - offset
    ax.axvline(reach, linestyle="-.", linewidth=0.9, color="crimson")
    # Grid zone only over the part of the chart where the grid applies, so it
    # does not fight the terminal-palette Fibonacci bands across the whole plot.
    from matplotlib.patches import Rectangle
    ax.add_patch(Rectangle(
        (max(reach - 1, 0) - 0.5, min(grid.prices)), last - max(reach - 1, 0) + 1,
        max(grid.prices) - min(grid.prices),
        facecolor="crimson", alpha=0.10, edgecolor="none", zorder=0.6,
    ))
    for price in grid.prices:
        ax.hlines(price, max(reach - 1, 0), last, colors="crimson",
                  linestyles=":", linewidth=1.3)
    # One combined label: four close lines would overprint separate captions.
    listing = chr(10).join(
        f"{number}/4 · 1/4 РО  {price:.8g}"
        for number, price in enumerate(grid.prices, start=1)
    )
    # Place the numeric illustration beyond the RIGHT edge of the price
    # axes: when 1.618 is touched by the latest candle, an in-axes label
    # covers precisely the bars the user needs to inspect. Tight PNG bounds
    # include this margin text without changing candle or Fibonacci x-coords.
    ax.text(
        1.03, sum(grid.prices) / len(grid.prices),
        "Схема сетки · шаг НЕ утверждён" + chr(10) + listing,
        transform=ax.get_yaxis_transform(), clip_on=False,
        fontsize=7, va="center", ha="left", color="crimson",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.85,
                  edgecolor="crimson"),
    )
    prices += list(grid.prices)
    if overlay.stop is not None:
        stop = overlay.stop
        ax.hlines(stop.price, max(reach - 1, 0), last, colors="black",
                  linestyles="-", linewidth=1.4)
        # Caption on the adverse side of the line, away from the entry grid.
        above = overlay.direction == "SHORT"
        ax.annotate(
            f"STOP план {stop.price:.8g}", (last, stop.price),
            xytext=(-3, 3 if above else -3), textcoords="offset points",
            fontsize=8, va="bottom" if above else "top", ha="right",
        )
        if stop.anchor_index is not None:
            ax.scatter([stop.anchor_index - offset], [stop.price],
                       marker="v", s=40, zorder=7, color="black")
        prices.append(stop.price)
    return prices


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
            figsize=(12, 7),
            datetime_format="%H:%M",
            returnfig=True,
        )
        ax = axes[0]
        start = formation.anchor_start_index - offset
        terminal = formation.anchor_end_index - offset
        box_first = formation.box_start_index - offset
        box_last = formation.box_end_index - offset
        leg_two = (
            formation.first_box_exit_index if is_watch
            else formation.second_start_index
        )
        last = len(window) - 1

        ax.axvspan(box_first - 0.5, box_last + 0.5, alpha=0.12,
                   color="slateblue", label="Проторговка")
        if leg_two is not None:
            ax.axvline(leg_two - offset - 0.5, linestyle=":", linewidth=0.8,
                       color="slategray")
        ax.scatter(
            [start, terminal],
            [formation.anchor_start_price, formation.anchor_end_price],
            marker="o", s=48, zorder=6, color="black",
        )
        # Keep the anchor labels on the OUTER side of the impulse: A above
        # and to the left of its high, B below and to the left of its low.
        # In a short first impulse, labels on the right obscure the next bar.
        a_below = formation.direction == "SHORT"
        ax.annotate(
            "A / 0", (start, formation.anchor_start_price),
            xytext=(-8, -10 if a_below else 10),
            textcoords="offset points", fontsize=9,
            ha="right", va="top" if a_below else "bottom",
        )
        ax.annotate(
            "B / 1", (terminal, formation.anchor_end_price),
            xytext=(-8, 10 if a_below else -10),
            textcoords="offset points", fontsize=9,
            ha="right", va="bottom" if a_below else "top",
        )

        terminal_levels = terminal_fibonacci_levels(formation)
        _draw_fibonacci_bands(ax, terminal_levels, start - 0.5, last + 0.5)
        for level, price in levels:
            ax.hlines(price, start, last, colors=TERMINAL_LINE_COLOR,
                      linewidth=TERMINAL_LINE_WIDTH, alpha=0.95)
            label = (
                "1.000 · цель" if level == 1 else
                f"{level:.3f} · зона {'I' if level == 1.618 else 'II'}"
                if level > 1 else "0.000 · старт"
            )
            if level == 1:
                # Keep the F(1.0) price label OUTSIDE the candle axes. Its
                # previous end-of-line position overprinted B and box wicks.
                ax.text(
                    1.03, price, f"{label}  {price:.8g}",
                    transform=ax.get_yaxis_transform(), clip_on=False,
                    fontsize=8, va="center", ha="left",
                )
            else:
                ax.annotate(
                    f"{label}  {price:.8g}",
                    (last, price), xytext=(3, 1),
                    textcoords="offset points", fontsize=8,
                    va="bottom", ha="right",
                )

        # Planning overlay (presentation only): stage, 1.618 reached?, the
        # four-LIMIT grid, STOP and target. No orders, no candidates.
        overlay = build_trade_overlay(candles, formation)
        overlay_prices = _draw_trade_overlay(ax, overlay, offset, last)

        # Include both target and secondary zone even if not reached yet.
        visible = [float(window["low"].min()), float(window["high"].max())]
        visible += [price for _, price in levels]
        visible += overlay_prices
        spread = max(visible) - min(visible)
        pad = max(spread * 0.055, formation.anchor_start_price * 0.0001)
        ax.set_ylim(min(visible) - pad, max(visible) + pad)
        ax.set_xlim(-1, len(window) + 0.5)
        _draw_terminal_levels(
            ax, terminal_levels, {level for level, _ in levels}, start, last
        )
        ax.set_xlabel("МСК")
        ax.set_title(
            f"{symbol} · {format_timeframe_ru(timeframe)} · "
            f"Коробка Икигаи / {formation.direction}\n"
            + (
                f"WATCH {formation.phase} · второй импульс НЕ подтверждён · "
                if is_watch else ""
            )
            + "Фибо первого импульса · зоны входа ПЛАН (не ордера)",
            fontsize=12,
        )
        # Put the status box on the side opposite to point A so it does not
        # cover the first impulse: LONG starts high (box low), SHORT the reverse.
        box_top = formation.direction == "SHORT"
        ax.text(
            0.01, 0.985 if box_top else 0.015, _stage_caption(overlay),
            transform=ax.transAxes,
            va="top" if box_top else "bottom", ha="left", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.85,
                      edgecolor="slategray"),
        )
        fig.savefig(target, dpi=125, bbox_inches="tight")
    finally:
        if fig is not None:
            plt.close(fig)
    return target
