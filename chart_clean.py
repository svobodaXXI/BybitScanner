"""
chart_clean.py

BybitCleanScanner v3

Профессиональная визуализация Wedge Setup.

Отображает:
- свечи;
- границы клина только в области формирования;
- область сжатия клина;
- начало структуры;
- apex;
- текущую цену;
- название паттерна;
- направление;
- Score;
- Quality;
- Compression.

Исправления v3.1:
- сохранение графиков в отдельную папку charts/;
- автоматическое создание папки charts;
- корректный перевод координат Pivot -> окно графика;
- линии клина привязаны к реальному участку формирования;
- apex отображается относительно текущего окна;
- заливка клина строится только по валидным координатам;
- сохраняется совместимость:
  draw_chart(df, highs, lows, symbol, result)
"""


import warnings
import logging
import os

import matplotlib as mpl

# Headless backend: must be selected before importing mplfinance or
# matplotlib.pyplot, since either import resolves and locks in a backend as
# a side effect. Rendering runs on ScannerControlRuntime's background
# thread, not the process main thread, and matplotlib's default
# auto-detected GUI backend (TkAgg, when Tkinter is available) is not
# thread-safe -- it previously crashed the whole PAPER backend process with
# a native Tcl error ("Tcl_AsyncDelete: async handler deleted by the wrong
# thread"). Agg is the non-interactive, thread-safe rendering backend and
# never opens a GUI/event loop, matching this module's savefig()-only usage.
mpl.use("Agg")

import pandas as pd
import numpy as np
import mplfinance as mpf

from timeframe_format import format_timeframe_ru

# Owner format 2026-09-23: a wedge's arrow describes its own geometry (the
# slope of its two trendlines) and never changes after breakout, unlike a
# breakout-direction arrow. Mirrored from notification.py's copy (kept
# separate since the two modules must not import each other).
WEDGE_GEOMETRY_ARROWS = {"Falling Wedge": "↘", "Rising Wedge": "↗"}

# Cyrillic-capable font for Russian signal interface.
mpl.rcParams["font.family"] = "DejaVu Sans"
mpl.rcParams["axes.unicode_minus"] = False
import matplotlib.pyplot as plt


# ---------------------------------
# Console cleanup
# ---------------------------------

warnings.filterwarnings(
    "ignore",
    category=UserWarning
)


logging.getLogger(
    "matplotlib"
).setLevel(
    logging.ERROR
)


mpl.rcParams[
    "font.family"
] = "DejaVu Sans"



# ---------------------------------
# Charts directory
# ---------------------------------

CHARTS_DIR = "charts"


def ensure_charts_dir():
    """
    Создаёт папку для графиков,
    если её нет.
    """

    if not os.path.exists(CHARTS_DIR):
        os.makedirs(
            CHARTS_DIR
        )


def build_chart_title(symbol, result):
    """Build the chart's title/header text. Pure string-building, no plotting
    side effects -- extracted so the timeframe annotation is unit-testable
    without a full mplfinance render."""

    if not result:
        return symbol

    pattern = result.get(
        "pattern",
        "No wedge"
    )

    pattern_names = {
        "Falling Wedge":
            'Нисходящий клин',

        "Rising Wedge":
            'Восходящий клин',

        "Triangle Compression":
            'Сжимающийся треугольник',

        "No wedge":
            'Клин не найден',

        "Unknown":
            'Неизвестная структура',
    }

    structure_name = pattern_names.get(
        pattern,
        pattern
    )

    score = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )

    potential = (
        result.get("potential")
        or {}
    )

    signed_potential = potential.get(
        "signed_percent"
    )

    if potential.get("direction") == "SYMMETRIC":

        symmetric_percent = potential.get("percent")

        potential_name = (
            f"±{symmetric_percent:.2f}%"
            if symmetric_percent is not None
            else 'РАСЧЁТ НЕДОСТУПЕН'
        )

    elif signed_potential is None:

        potential_name = (
            'РАСЧЁТ НЕДОСТУПЕН'
        )

    else:

        potential_name = (
            f"{signed_potential:+.2f}%"
        )

    chart_timeframe = result.get("timeframe")

    title_symbol_line = (
        f"{symbol} · {format_timeframe_ru(chart_timeframe)}"
        if chart_timeframe
        else symbol
    )

    arrow = WEDGE_GEOMETRY_ARROWS.get(pattern, "")
    structure_line = f"{arrow} {structure_name}".strip()
    lines = [title_symbol_line, structure_line, f"Потенциал: {potential_name}"]
    if pattern in ("Falling Wedge", "Rising Wedge"):
        lines.append("Тип клина: не определено")
    lines.append(f"КАЧЕСТВО СТРУКТУРЫ: {score}/100")
    return "\n".join(lines)



def _chart_window(df, result):
    """Select loaded source bars only; geometry keeps its original coordinates.

    Target one formation span before the earlier frozen boundary anchor, plus
    max(10 bars, 8% of formation) as a left margin. Scanner renders immediately
    from the same frame used for detection, unlike Robot's projected 1m charts.
    """
    fallback = max(0, len(df) - 120)
    if not result:
        return fallback, None
    unknown = "История перед паттерном недоступна: неизвестны исходные якоря"
    geometry = result.get("geometry") or {}
    try:
        anchors = [float(geometry[name]["anchor_index"])
                   for name in ("upper_line", "lower_line")]
        if any(not np.isfinite(x) or not x.is_integer() or x >= len(df)
               for x in anchors):
            return fallback, unknown
        earliest = int(min(anchors))
        times = df["time"].to_numpy(dtype=np.int64)
        # Use the source interval, never the Robot's projected cursor interval.
        timeframe = result.get("scanner_source_timeframe", result.get("timeframe"))
        step = float(timeframe) * 60_000
        if not np.isfinite(step) or step <= 0 or np.any(np.diff(times) <= 0):
            return fallback, unknown
    except (KeyError, TypeError, ValueError, OverflowError):
        return fallback, unknown

    start_time = (times[earliest] if earliest >= 0
                  else times[0] + earliest * step)
    formation = times[-1] - start_time
    margin = max(10, int(np.ceil(0.08 * formation / step))) * step
    target_time = start_time - formation - margin
    # Include the candle at/before the target if available; never pad missing OHLC.
    offset = max(0, len(df) - 1000,
                 int(np.searchsorted(times, target_time, side="right")) - 1)
    if times[offset] > start_time:
        warning = "Начало паттерна раньше окна графика"
    elif times[offset] > target_time or np.any(
        np.diff(times[offset:max(offset + 1, earliest + 1)]) > step
    ):
        warning = "Предшествующий импульс показан не полностью"
    else:
        warning = None
    return offset, warning


def draw_chart(
    df,
    highs,
    lows,
    symbol,
    result
):

    df = df.copy()


    # =====================================
    # сохраняем исходную длину для координат
    # =====================================

    original_length = len(df)

    # =====================================
    # Show the earlier genuine boundary anchor and available pre-formation candles.
    chart_offset, history_warning = _chart_window(df, result)

    df = df.iloc[
        chart_offset:
    ].copy()


    df["time"] = df["time"].astype(
        "int64"
    )


    # ????? ??????? ?????????? ?? ?????? (???, UTC+3).
    # ????? ??????????? ??????? timezone ?? ???????,
    # ????? mplfinance ????????? ????????? ???????.
    df.index = (
        pd.to_datetime(
            df["time"],
            unit="ms",
            utc=True
        )
        .dt.tz_convert(
            "Europe/Moscow"
        )
        .dt.tz_localize(
            None
        )
    )


    addplots = []


    wedge_x = None
    wedge_upper = None
    wedge_lower = None

    apex_x = None
    apex_price = None



    # =====================================
    # Геометрия клина
    # =====================================

    if result:


        geometry = result.get(
            "geometry"
        ) or {}


        upper_data = geometry.get(
            "upper_line",
            {}
        )


        lower_data = geometry.get(
            "lower_line",
            {}
        )


        apex = geometry.get(
            "apex",
            {}
        )


        upper_slope = upper_data.get(
            "slope"
        )

        upper_intercept = upper_data.get(
            "intercept"
        )

        lower_slope = lower_data.get(
            "slope"
        )

        lower_intercept = lower_data.get(
            "intercept"
        )



        if None not in (
            upper_slope,
            upper_intercept,
            lower_slope,
            lower_intercept
        ):


            source_x = np.arange(
                original_length
            )


            upper_full = (
                upper_slope * source_x
                +
                upper_intercept
            )


            lower_full = (
                lower_slope * source_x
                +
                lower_intercept
            )


            chart_x = np.arange(
                len(df)
            )


            upper_chart = upper_full[
                chart_offset:
            ]


            lower_chart = lower_full[
                chart_offset:
            ]



            # координаты apex в текущем окне

            apex_original = apex.get(
                "index"
            )


            if apex_original is not None:


                apex_x = (
                    apex_original
                    -
                    chart_offset
                )


                if (
                    0 <= apex_x < len(df)
                ):

                    apex_price = (

                        upper_slope
                        *
                        apex_original

                        +

                        upper_intercept

                    )



            # Real geometry anchors

            upper_anchor_original = upper_data.get(
                "anchor_index"
            )

            lower_anchor_original = lower_data.get(
                "anchor_index"
            )

            if upper_anchor_original is None:
                upper_anchor_original = 0

            if lower_anchor_original is None:
                lower_anchor_original = 0

            upper_start_x = max(
                0,
                int(upper_anchor_original) - chart_offset
            )

            lower_start_x = max(
                0,
                int(lower_anchor_original) - chart_offset
            )

            common_start_x = max(
                upper_start_x,
                lower_start_x
            )

            end_x = len(df) - 1

            upper_mask = (
                chart_x >= upper_start_x
            ) & (
                chart_x <= end_x
            )

            lower_mask = (
                chart_x >= lower_start_x
            ) & (
                chart_x <= end_x
            )

            common_mask = (
                chart_x >= common_start_x
            ) & (
                chart_x <= end_x
            )

            upper_plot = np.where(
                upper_mask,
                upper_chart,
                np.nan
            )

            lower_plot = np.where(
                lower_mask,
                lower_chart,
                np.nan
            )

            addplots.append(
                mpf.make_addplot(
                    upper_plot,
                    width=2
                )
            )

            addplots.append(
                mpf.make_addplot(
                    lower_plot,
                    width=2
                )
            )

            if common_mask.any():

                wedge_x = chart_x[common_mask]

                wedge_upper = upper_chart[common_mask]

                wedge_lower = lower_chart[common_mask]



    # =====================================
    # построение
    # =====================================


    ensure_charts_dir()


    filename = os.path.join(
        CHARTS_DIR,
        (f"{symbol}_analysis.png" if str(result.get("timeframe", "5")) == "5"
         else f"{symbol}_{result['timeframe']}_analysis.png")
    )



    fig, axes = mpf.plot(

        df,

        type="candle",

        style="charles",

        addplot=addplots,

        volume=False,

        figsize=(12,7),

        datetime_format="%H:%M",
        ylabel="",
        returnfig=True

    )


    ax = axes[0]

    # Owner format 2026-09-23: axis-label text removed; tick values and the
    # time/price scales are unaffected (mplfinance's default y-axis label
    # is "Price", set at plot() time via ylabel="" a few lines above).
    ax.set_xlabel("")



    # =====================================
    # заливка клина
    # =====================================


    if (
        wedge_x is not None
        and
        wedge_upper is not None
        and
        wedge_lower is not None
    ):


        ax.fill_between(

            wedge_x,

            wedge_lower,

            wedge_upper,

            alpha=0.18

        )



    # =====================================
    # START
    # =====================================


    if (
        wedge_x is not None
        and
        len(wedge_x)
        and max(upper_anchor_original, lower_anchor_original) >= chart_offset
    ):


        start = wedge_x[0]


        price = (

            wedge_upper[0]
            +
            wedge_lower[0]

        ) / 2



        ax.scatter(

            start,

            price,

            s=70

        )


        ax.text(

            start,

            price,

            " START",

            fontsize=9

        )



    # =====================================
    # APEX
    # =====================================


    if (
        apex_x is not None
        and
        apex_price is not None
    ):


        ax.scatter(

            apex_x,

            apex_price,

            s=90

        )


        ax.text(

            apex_x,

            apex_price,

            " APEX",

            fontsize=9

        )



    # =====================================
    # текущая цена
    # =====================================


    current_price = df["close"].iloc[-1]


    ax.axhline(

        current_price,

        linestyle="--",

        linewidth=1

    )


    ax.text(

        len(df)-1,

        current_price,

        " PRICE",

        fontsize=9

    )



    # =====================================
    # заголовок
    # =====================================

    title = build_chart_title(symbol, result)
    # Owner format 2026-09-23: the chart header stays minimal. The
    # incomplete-impulse note is presentation-only and no longer shown;
    # _chart_window's own return value (used by callers/tests) is unchanged.
    if history_warning and history_warning != "Предшествующий импульс показан не полностью":
        title += f"\n{history_warning}"


    ax.set_title(
        title
    )



    fig.savefig(

        filename,

        bbox_inches="tight"

    )


    plt.close(
        fig
    )


    print(
        f"График сохранён: {filename}"
    )
