"""
analyzer.py

Модуль анализа одной торговой пары.

Выполняет полный цикл анализа:

- загрузка свечей;
- поиск Pivot High / Pivot Low;
- анализ структуры;
- подтверждение сигнала;
- построение графика;
- сохранение отчёта.

Возвращает результат анализа.
"""


from bybit_api import get_candles
from pivots import find_pivots
from wedge import analyze_wedge
from confirmation import confirm_signal
from chart import draw_chart
from report import save_report

from config import (
    TIMEFRAME,
    CANDLE_LIMIT
)



def analyze_symbol(symbol):

    """
    Анализ одной торговой пары.
    """


    try:

        # =========================
        # Load candles
        # =========================

        df = get_candles(
            symbol,
            TIMEFRAME,
            CANDLE_LIMIT
        )


        if df is None or len(df) < 50:

            print(
                f"{symbol}: недостаточно свечей"
            )

            return {

                "symbol": symbol,
                "result": None,
                "highs": [],
                "lows": []

            }



        # =========================
        # Pivot detection
        # =========================


        highs, lows = find_pivots(
            df
        )


        if (
            len(highs) < 3
            or len(lows) < 3
        ):

            print(
                f"{symbol}: недостаточно Pivot"
            )

            return {

                "symbol": symbol,
                "result": None,
                "highs": highs,
                "lows": lows

            }



        # =========================
        # Wedge analysis
        # =========================


        result = analyze_wedge(
            highs,
            lows
        )


        if result is None:


            return {

                "symbol": symbol,

                "result": None,

                "highs": highs,

                "lows": lows

            }



        # =========================
        # Confirmation Engine
        # =========================


        confirmation = confirm_signal(

            df,

            result

        )


        if confirmation is None:

            confirmation = {

                "breakout": False,

                "volume": False,

                "volatility": False,

                "breakout_score": 0,

                "volume_score": 0,

                "volatility_score": 0,

                "freshness_score": 0,

                "distance_score": 0,

                "confirmation_score": 0,

                "direction": "WAIT",

                "confirmed": False

            }



        result["confirmation"] = confirmation



        # =========================
        # Final score
        # =========================


        base_score = result.get(
            "score",
            0
        )


        confirmation_score = confirmation.get(
            "confirmation_score",
            0
        )


        result["final_score"] = min(

            base_score
            +
            confirmation_score,

            100

        )



        # =========================
        # Chart
        # =========================


        draw_chart(

            df,

            highs,

            lows,

            symbol,

            result

        )



        # =========================
        # Report
        # =========================


        save_report(

            symbol,

            TIMEFRAME,

            result,

            highs,

            lows

        )



        return {

            "symbol": symbol,

            "result": result,

            "highs": highs,

            "lows": lows,

            "data": df

        }



    except Exception as error:


        print(
            f"[ERROR] {symbol}: {error}"
        )


        return {

            "symbol": symbol,

            "result": None,

            "highs": [],

            "lows": []

        }