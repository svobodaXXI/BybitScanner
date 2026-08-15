"""
chart.py

BybitCleanScanner

Построение чистого торгового графика клина.

Отображает:

- свечи;
- верхнюю границу клина;
- нижнюю границу клина;
- название паттерна;
- направление;
- итоговый Score;
- Compression.

Не отображает:

- Pivot High / Low;
- служебные точки;
- внутреннюю отладочную информацию.

Изменения v2:

- графики сохраняются в папку charts/
- корневая папка проекта не засоряется изображениями
"""

import os
import warnings
import logging

import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib as mpl


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
# Chart storage
# ---------------------------------

CHARTS_DIR = "charts"


def ensure_charts_dir():
    """
    Создаёт папку для графиков.
    """

    if not os.path.exists(
        CHARTS_DIR
    ):
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
    """
    Строит и сохраняет график анализа.

    Возвращает:
        путь к сохранённому PNG.
    """

    ensure_charts_dir()

    df = df.copy()

    df["time"] = df["time"].astype(
        "int64"
    )

    df.index = pd.to_datetime(
        df["time"],
        unit="ms"
    )

    addplots = []

    # =================================
    # КЛИН - реальные линии геометрии
    # =================================

    if result:

        geometry = result.get(
            "geometry",
            {}
        )

        upper = geometry.get(
            "upper_line"
        )

        lower = geometry.get(
            "lower_line"
        )

        if upper and lower:

            upper_slope = upper.get(
                "slope"
            )

            upper_intercept = upper.get(
                "intercept"
            )

            lower_slope = lower.get(
                "slope"
            )

            lower_intercept = lower.get(
                "intercept"
            )

            if None not in (
                upper_slope,
                upper_intercept,
                lower_slope,
                lower_intercept
            ):

                x = np.arange(
                    len(df)
                )

                upper_line = (
                    upper_slope * x
                    +
                    upper_intercept
                )

                lower_line = (
                    lower_slope * x
                    +
                    lower_intercept
                )

                upper_anchor = upper.get(
                    "anchor_index",
                    0
                )

                lower_anchor = lower.get(
                    "anchor_index",
                    0
                )

                upper_anchor = max(
                    int(upper_anchor or 0),
                    0
                )

                lower_anchor = max(
                    int(lower_anchor or 0),
                    0
                )

                upper_line = np.asarray(
                    upper_line,
                    dtype=float
                )

                lower_line = np.asarray(
                    lower_line,
                    dtype=float
                )

                upper_line[:upper_anchor] = np.nan
                lower_line[:lower_anchor] = np.nan


                addplots.append(
                    mpf.make_addplot(
                        upper_line,
                        width=2
                    )
                )

                addplots.append(
                    mpf.make_addplot(
                        lower_line,
                        width=2
                    )
                )

    # =================================
    # Информация на графике
    # =================================

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

        compression = (
            result.get(
                "geometry",
                {}
            )
            .get(
                "compression",
                {}
            )
            .get(
                "compression_percent",
                0
            )
        )

        confirmation = result.get(
            "confirmation",
            {}
        )

        direction = confirmation.get(
            "direction",
            ""
        )

        title = (
            f"{symbol} | "
            f"{pattern} | "
            f"{direction}\n"
            f"Score: {score}/100   "
            f"Compression: {compression:.1f}%"
        )

    # =================================
    # Save path
    # =================================

    filename = os.path.join(
        CHARTS_DIR,
        f"{symbol}_analysis.png"
    )

    # =================================
    # Построение
    # =================================

    mpf.plot(
        df,
        type="candle",
        style="charles",
        addplot=addplots,
        title=title,
        volume=False,
        figsize=(12, 6),
        savefig=filename
    )

    print(
        f"График сохранён: {filename}"
    )

    return filename
