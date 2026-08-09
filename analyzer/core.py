"""
analyzer.core

Главный координатор анализа торговой пары.

Отвечает только за последовательность:
- загрузка свечей;
- поиск Pivot;
- анализ структуры;
- подтверждение;
- расчёт Score;
- оценка качества сигнала;
- фильтрация сигнала;
- создание Signal Object;
- построение графика;
- сохранение отчёта.

Логика отдельных частей вынесена в другие модули.
"""

import traceback

from pivots import find_pivots
from wedge import analyze_wedge
from confirmation import confirm_signal

from signal.quality import evaluate_quality
from signal.filter import evaluate_signal

from tradingview_bridge import create_signal_payload

from config import (
    TIMEFRAME,
    CANDLE_LIMIT
)

from .candles import load_candles
from .scoring import calculate_final_score
from .charts import create_chart
from .reports import create_report



def analyze_symbol(symbol):
    """
    Анализ одной торговой пары.
    """

    print(f"[DEBUG] analyze_symbol() -> {symbol}")

    try:

        # =========================
        # Candles
        # =========================

        df = load_candles(
            symbol,
            TIMEFRAME,
            CANDLE_LIMIT
        )

        if df is None:

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
        # Pivot
        # =========================

        highs, lows = find_pivots(df)

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
        # Wedge
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
        # Confirmation
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
        # Score
        # =========================

        result["final_score"] = calculate_final_score(
            result,
            confirmation
        )

        # =========================
        # Signal Quality
        # =========================

        result["quality"] = evaluate_quality(
            result.get("pattern"),
            result.get("geometry"),
            confirmation,
            result["final_score"]
        )

        # =========================
        # Signal Filter
        # =========================

        result["signal"] = evaluate_signal(
            result.get("quality"),
            result["final_score"],
            confirmation,
            mode="hunter"
        )

        # =========================
        # TradingView Bridge
        # =========================

        result["tradingview"] = create_signal_payload(
            symbol,
            TIMEFRAME,
            result
        )

        # =========================
        # Chart
        # =========================

        create_chart(
            df,
            highs,
            lows,
            symbol,
            result
        )

        # =========================
        # Report
        # =========================

        create_report(
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

    except Exception:

        print(f"[DEBUG] EXCEPTION INSIDE analyze_symbol({symbol})")

        traceback.print_exc()

        raise