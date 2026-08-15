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

import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib as mpl

import matplotlib as mpl

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
    # Dynamic chart context
    # ?????????? ??????? ?? primary anchor,
    # ????? ???? ????? ????????, ???????
    # ???????????? ????????? ?????????.
    # =====================================

    geometry_for_window = (
        result.get("geometry")
        if result
        else None
    ) or {}

    pair_metrics_for_window = (
        geometry_for_window.get(
            "pair_metrics"
        )
        or {}
    )

    anchor_sequence_for_window = (
        pair_metrics_for_window.get(
            "anchor_sequence"
        )
        or {}
    )

    primary_anchor = (
        anchor_sequence_for_window.get(
            "primary_anchor"
        )
    )

    pre_anchor_context = 25

    if primary_anchor is not None:

        chart_offset = max(
            0,
            int(primary_anchor)
            - pre_anchor_context
        )

    else:

        chart_offset = max(
            0,
            original_length - 120
        )

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
        f"{symbol}_analysis.png"
    )



    fig, axes = mpf.plot(

        df,

        type="candle",

        style="charles",

        addplot=addplots,

        volume=False,

        figsize=(12,7),

        datetime_format="%H:%M",
        returnfig=True

    )


    ax = axes[0]

    ax.set_xlabel('МСК')



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


    title = symbol


    if result:

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

        geometry = (
            result.get(
                "geometry"
            )
            or {}
        )

        pair_metrics = (
            geometry.get(
                "pair_metrics"
            )
            or {}
        )

        geometry_mode = result.get(
            "geometry_mode"
        )

        if not geometry_mode:
            geometry_mode = pair_metrics.get(
                "geometry_mode",
                "NONE"
            )

        geometry_names = {
            "CANONICAL":
                'КАНОНИЧЕСКАЯ',

            "EXPLORATORY":
                'ИССЛЕДОВАТЕЛЬСКАЯ',

            "NONE":
                'НЕТ',

            "UNKNOWN":
                'НЕТ',

            "REJECT":
                'ОТКЛОНЕНА',
        }

        geometry_name = geometry_names.get(
            geometry_mode,
            str(geometry_mode)
        )

        detection = (
            result.get(
                "detection"
            )
            or {}
        )

        pattern_confirmed = bool(
            detection.get(
                "detected",
                False
            )
        )

        detection_name = (
            "ПОДТВЕРЖДЕН"
            if pattern_confirmed
            else "НЕ ПОДТВЕРЖДЕН"
        )

        score = result.get(
            "final_score",
            result.get(
                "score",
                0
            )
        )

        training_name = (
            "ПОДХОДИТ"
            if (
                geometry_mode == "CANONICAL"
                and pattern_confirmed
            )
            else "НЕ ИСПОЛЬЗУЕТСЯ"
        )

        potential = (
            result.get("potential")
            or {}
        )

        signed_potential = potential.get(
            "signed_percent"
        )

        if signed_potential is None:

            potential_name = (
                'РАСЧЁТ НЕДОСТУПЕН'
            )

        else:

            potential_name = (
                f"{signed_potential:+.2f}%"
            )

        title = (
            f"{symbol}\n"
            f"СТРУКТУРА: {structure_name}\n"
            f"ГЕОМЕТРИЯ: {geometry_name}\n"
            f"ПАТТЕРН: {detection_name}\n"
            f"КАЧЕСТВО СТРУКТУРЫ: {score}/100\n"
            f"ПОТЕНЦИАЛ ДВИЖЕНИЯ: {potential_name}\n"
            f"ОБУЧЕНИЕ: {training_name}"
        )


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
