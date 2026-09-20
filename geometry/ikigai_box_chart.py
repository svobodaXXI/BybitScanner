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
        ax.annotate("A / 0", (start, formation.anchor_start_price),
                    xytext=(5, -17), textcoords="offset points", fontsize=9)
        ax.annotate("B / 1", (terminal, formation.anchor_end_price),
                    xytext=(5, 9), textcoords="offset points", fontsize=9)

        for level, price in levels:
            ax.hlines(price, start, last, linestyles="--" if level > 1 else "-",
                      linewidth=1.1, alpha=0.80)
            label = (
                "1.000 · цель" if level == 1 else
                f"{level:.3f} · зона {'I' if level == 1.618 else 'II'}"
                if level > 1 else "0.000 · старт"
            )
            ax.annotate(
                f"{label}  {price:.8g}",
                (last, price), xytext=(3, 1),
                textcoords="offset points", fontsize=8,
                va="bottom", ha="right",
            )

        # Include both target and secondary zone even if not reached yet.
        visible = [float(window["low"].min()), float(window["high"].max())]
        visible += [price for _, price in levels]
        spread = max(visible) - min(visible)
        pad = max(spread * 0.055, formation.anchor_start_price * 0.0001)
        ax.set_ylim(min(visible) - pad, max(visible) + pad)
        ax.set_xlim(-1, len(window) + 0.5)
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
        fig.savefig(target, dpi=125, bbox_inches="tight")
    finally:
        if fig is not None:
            plt.close(fig)
    return target
