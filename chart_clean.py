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


    window = 120


    df = df.tail(
        window
    ).copy()


    chart_offset = (
        original_length
        -
        len(df)
    )


    df["time"] = df["time"].astype(
        "int64"
    )


    df.index = pd.to_datetime(
        df["time"],
        unit="ms"
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
            "geometry",
            {}
        )


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



            # начало структуры

            if apex_x is not None:


                start_x = max(
                    0,
                    int(apex_x - 80)
                )


            else:

                start_x = 0



            end_x = len(df)-1



            mask = (
                chart_x >= start_x
            ) & (
                chart_x <= end_x
            )


            if mask.any():


                upper_plot = np.where(
                    mask,
                    upper_chart,
                    np.nan
                )


                lower_plot = np.where(
                    mask,
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


                wedge_x = chart_x[mask]

                wedge_upper = upper_chart[mask]

                wedge_lower = lower_chart[mask]



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

        returnfig=True

    )


    ax = axes[0]



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
            ""
        )


        score = result.get(
            "final_score",
            result.get(
                "score",
                0
            )
        )


        compression = result.get(
            "compression",
            0
        )


        quality = result.get(
            "quality",
            {}
        )


        quality_name = quality.get(
            "quality",
            ""
        )


        confirmation = result.get(
            "confirmation",
            {}
        )


        direction = confirmation.get(
            "direction",
            "WAIT"
        )


        title = (

            f"{symbol} | {pattern}\n"
            f"{quality_name} | {direction}\n"
            f"Score: {score}/100   "
            f"Compression: {compression}%"

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