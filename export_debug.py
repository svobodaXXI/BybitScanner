"""
export_debug.py

BybitScanner Debug Export Tool v1.3

Создаёт диагностический пакет:

debug/
    SYMBOL.json
    SYMBOL_analysis.png
    SYMBOL.txt

Используется для анализа:
- корректности клиньев;
- положения линий;
- привязки к свечам;
- качества графика.
"""

import json
import shutil
from pathlib import Path
from datetime import datetime

from analyzer import analyze_symbol


# ======================================
# SYMBOL
# ======================================

SYMBOL = "ETHUSDT"


# ======================================
# DEBUG FOLDER
# ======================================

DEBUG_DIR = Path("debug")
DEBUG_DIR.mkdir(exist_ok=True)


print("=" * 60)
print("EXPORT DEBUG v1.3")
print("=" * 60)
print()


# ======================================
# ANALYSIS
# ======================================

analysis = analyze_symbol(SYMBOL)


if analysis is None:

    print("Ошибка анализа")

    raise SystemExit()


result = analysis.get(
    "result",
    {}
)


# ======================================
# DATAFRAME
# ======================================

df = analysis.get(
    "data"
)


geometry = result.get(
    "geometry",
    {}
)


# ======================================
# CANDLES
# ======================================

candles = []


if df is not None:

    columns = [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]


    available = [
        c for c in columns
        if c in df.columns
    ]


    candles = (

        df.tail(100)[available]
        .reset_index()
        .to_dict(
            orient="records"
        )

    )


# ======================================
# PIVOTS
# ======================================

high_pivots = analysis.get(
    "highs",
    []
)


low_pivots = analysis.get(
    "lows",
    []
)


# ======================================
# MARKET POSITION
# ======================================

market_position = {}


chart_debug = {}


if df is not None and len(df):


    current_index = float(
        df.index[-1]
    )


    current_price = float(
        df.iloc[-1]["close"]
    )


    market_position["current_price"] = (
        current_price
    )


    market_position["current_index"] = (
        current_index
    )


    upper = geometry.get(
        "upper_line"
    )


    lower = geometry.get(
        "lower_line"
    )


    if upper:


        upper_price = (

            upper["slope"]
            *
            current_index
            +
            upper["intercept"]

        )


        market_position[
            "upper_line_price"
        ] = float(
            upper_price
        )


        market_position[
            "distance_upper"
        ] = float(
            current_price -
            upper_price
        )



    if lower:


        lower_price = (

            lower["slope"]
            *
            current_index
            +
            lower["intercept"]

        )


        market_position[
            "lower_line_price"
        ] = float(
            lower_price
        )


        market_position[
            "distance_lower"
        ] = float(
            current_price -
            lower_price
        )



    chart_debug = {

        "data_length":
            len(df),

        "index_start":
            float(df.index[0]),

        "index_end":
            float(df.index[-1]),

        "current_index":
            current_index,

        "geometry_available":
            bool(geometry)

    }



# ======================================
# EXPORT DATA
# ======================================

export_data = {


    "export_version":
        "1.3",


    "export_time":
        datetime.now()
        .isoformat(),


    "symbol":
        SYMBOL,


    "analysis": {

        "pattern":
            result.get(
                "pattern"
            ),

        "score":
            result.get(
                "score"
            ),

        "final_score":
            result.get(
                "final_score"
            ),

        "reason":
            result.get(
                "reason"
            )

    },


    "geometry":
        geometry,


    "confirmation":
        result.get(
            "confirmation",
            {}
        ),


    "pivots": {

        "highs":
            high_pivots,

        "lows":
            low_pivots

    },


    "candles":
        candles,


    "market_position":
        market_position,


    "chart_debug":
        chart_debug

}



# ======================================
# SAVE JSON
# ======================================

json_file = (

    DEBUG_DIR /
    f"{SYMBOL}.json"

)


with open(
    json_file,
    "w",
    encoding="utf-8"
) as f:


    json.dump(

        export_data,

        f,

        indent=4,

        ensure_ascii=False,

        default=str

    )



# ======================================
# COPY CHART
# ======================================

chart_file = Path(
    f"{SYMBOL}_analysis.png"
)


if chart_file.exists():

    shutil.copy2(

        chart_file,

        DEBUG_DIR /
        chart_file.name

    )



# ======================================
# COPY REPORT
# ======================================

report_file = (

    Path("reports")
    /
    f"{SYMBOL}.txt"

)


if report_file.exists():

    shutil.copy2(

        report_file,

        DEBUG_DIR /
        report_file.name

    )



# ======================================
# DONE
# ======================================

print()

print("Экспорт завершён.")

print()

print("Созданы файлы:")

print(
    f" ✓ {json_file}"
)


if chart_file.exists():

    print(
        f" ✓ debug/{chart_file.name}"
    )


if report_file.exists():

    print(
        f" ✓ debug/{report_file.name}"
    )


print()

print("=" * 60)