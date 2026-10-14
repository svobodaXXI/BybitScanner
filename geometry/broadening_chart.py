"""
geometry.broadening_chart

HORN-4: chart renderer for an already detected Broadening Formation
(``geometry.broadening.BroadeningFormation``). It never detects anything, so the
picture cannot disagree with the detector.

Shows only: candles up to the decision bar, every confirmed anchor (P1..Pn,
HIGH/LOW), START, both diverging boundaries from START to the decision bar
(solid) and projected forward (dashed), the stage (PRELIMINARY / MATURE) and
the ticker/timeframe. No direction, entry, stop or target: observation only.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")           # headless: same choice as the other chart renderers

import matplotlib.pyplot as plt
import pandas as pd

from timeframe_format import format_timeframe_ru

PATTERN_NAME = "Рупор"
STAGE_LABELS = {
    "PRELIMINARY": "PRELIMINARY — предварительная геометрия",
    "MATURE": "MATURE",
}
UPPER_COLOR = "#1565c0"
LOWER_COLOR = "#6a1b9a"
START_COLOR = "#ef6c00"

# Presentation only (not a detection rule): bars shown before START and the
# forward projection length, as a share of the formation span.
LEAD_BARS = 20
PROJECTION_SHARE = 0.35
MIN_PROJECTION_BARS = 10


def broadening_caption(symbol, timeframe, formation):
    """Ticker, timeframe, pattern, stage and anchor count. No direction."""
    return "{} · {} · {} · {} · опорных точек: {}\nНаблюдение: без направления сделки и без торговли".format(
        symbol,
        format_timeframe_ru(timeframe),
        PATTERN_NAME,
        STAGE_LABELS.get(formation.stage, formation.stage),
        len(formation.anchors),
    )


def _msk(ms):
    return (
        pd.to_datetime(int(ms), unit="ms", utc=True)
        .tz_convert("Europe/Moscow")
        .strftime("%d.%m %H:%M")
    )


def render_broadening_chart(closed, formation, path, *, symbol, timeframe):
    """Render to ``path``. ``closed`` is the exact frame the detector read."""
    start, as_of = formation.start_index, formation.as_of_index
    first = max(0, start - LEAD_BARS)
    span = max(1, as_of - start)
    projection = max(MIN_PROJECTION_BARS, int(round(span * PROJECTION_SHARE)))
    last = as_of + projection
    frame = closed.iloc[first: as_of + 1]

    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    for index, row in frame.iterrows():
        up = row["close"] >= row["open"]
        colour = "#2e7d32" if up else "#c62828"
        ax.vlines(index, row["low"], row["high"], color=colour, linewidth=0.8)
        body_low = min(row["open"], row["close"])
        body = max(abs(row["close"] - row["open"]), 1e-12)
        ax.add_patch(plt.Rectangle((index - 0.3, body_low), 0.6, body, color=colour))

    for line, colour, label in (
        (formation.upper_line, UPPER_COLOR, "Верхняя граница"),
        (formation.lower_line, LOWER_COLOR, "Нижняя граница"),
    ):
        value = lambda i, line=line: line["slope"] * i + line["intercept"]
        ax.plot([start, as_of], [value(start), value(as_of)], color=colour, linewidth=1.8, label=label)
        ax.plot([as_of, last], [value(as_of), value(last)], color=colour, linewidth=1.3, linestyle="--")

    for number, (index, side, price) in enumerate(formation.anchors, 1):
        ax.plot(index, price, marker="v" if side == "H" else "^", color="black", markersize=9)
        ax.annotate(
            f"P{number}", (index, price), textcoords="offset points",
            xytext=(0, 10 if side == "H" else -16), ha="center", fontsize=9,
        )

    ax.axvline(start, color=START_COLOR, linewidth=1.2)
    ax.annotate("START", (start, frame["low"].min()), color=START_COLOR, fontsize=9,
                xytext=(3, 0), textcoords="offset points")
    ax.axvline(as_of, color="#555555", linewidth=0.9, linestyle=":")
    ax.axvspan(as_of + 0.5, last + 0.5, color="#f2f2f2", zorder=0)

    ticks = list(range(first, as_of + 1, max(1, (as_of - first) // 8)))
    ax.set_xticks(ticks)
    ax.set_xticklabels([_msk(closed.iloc[i]["time"]) for i in ticks], rotation=30, fontsize=8)
    ax.set_xlim(first - 1, last + 1)
    ax.set_title(
        "{} · {} · {} · {}".format(
            symbol, format_timeframe_ru(timeframe), PATTERN_NAME,
            STAGE_LABELS.get(formation.stage, formation.stage),
        ),
        fontsize=11,
    )
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
