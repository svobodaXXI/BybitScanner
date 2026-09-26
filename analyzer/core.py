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
from scanner_geometry_cursor import (
    ScannerGeometryCursorError,
    build_scanner_geometry_cursor_anchor,
    project_frozen_geometry_to_robot_1m,
)

from config import (
    TIMEFRAME,
    CANDLE_LIMIT,
    MODE,
    MIN_SCORE
)

from .candles import load_candles
from .scoring import calculate_final_score
from .charts import create_chart
from .reports import create_report


def analyze_symbol(symbol, *, timeframe=None):
    """
    Анализ одной торговой пары.
    """

    timeframe = str(TIMEFRAME if timeframe is None else timeframe).strip()
    if timeframe not in ("1", "5"):
        raise ValueError("Scanner timeframe must be 1 or 5")
    print(f"[DEBUG] analyze_symbol() -> {symbol} {timeframe}m")

    try:

        # =========================
        # Candles
        # =========================

        df = load_candles(
            symbol,
            timeframe,
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
                "lows": lows,
                # Reuse this OHLC snapshot for opt-in Box observation even
                # when Wedge pivot or geometry admission fails.
                "data": df
            }

        # =========================
        # Wedge
        # =========================

        current_index = len(df) - 1

        result = analyze_wedge(
            highs,
            lows,
            current_index=current_index,
            candles=df
        )

        if result is None:

            return {
                "symbol": symbol,
                "result": None,
                "highs": highs,
                "lows": lows,
                # Reuse this OHLC snapshot for opt-in Box observation even
                # when Wedge pivot or geometry admission fails.
                "data": df
            }

        # Scanner geometry stays in its native timeframe for charting and
        # provenance. Robot v0.1, however, evaluates the accepted frozen wedge
        # on closed 1m candles. Build an exact affine 1m coordinate projection
        # at the same source-candle timestamp instead of pretending a 5m
        # geometry index is already a 1m index.
        result["timeframe"] = timeframe
        # A canonical Scanner Wedge is Robot-eligible on both 5m and 1m.
        result["scanner_observational_only"] = False
        result["scanner_source_timeframe"] = timeframe.strip()
        # Identify a frozen formation by source-candle anchor timestamps,
        # not moving dataframe indices or the current scan candle.
        try:
            geometry = result["geometry"]
            anchor_indices = (
                int(geometry[name]["anchor_index"])
                for name in ("upper_line", "lower_line")
            )
            upper, lower = anchor_indices
            if any(index < 0 or index >= len(df) for index in (upper, lower)):
                raise ValueError("formation anchor outside source candles")
            result["scanner_formation_id"] = (
                f"{int(df.iloc[upper]['time'])}:{int(df.iloc[lower]['time'])}"
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            # Unknown identity cannot be used to create a new dedup namespace.
            result["scanner_formation_id"] = None

        try:
            source_candle_time_ms = int(df.iloc[current_index]["time"])
            result["scanner_source_candle_time_ms"] = source_candle_time_ms
            result["robot_geometry"] = project_frozen_geometry_to_robot_1m(
                result["geometry"],
                source_timeframe=timeframe,
            )
            result["scanner_geometry_cursor"] = build_scanner_geometry_cursor_anchor(
                geometry_index=current_index,
                source_candle_time_ms=source_candle_time_ms,
                timeframe="1",
            )
            result["robot_handoff_ready"] = True
        except (ScannerGeometryCursorError, KeyError, TypeError, ValueError, OverflowError) as exc:
            # Scanner notification remains available, but Robot handoff must
            # fail closed when its frozen 1m execution coordinate cannot be
            # proven from the Scanner source evidence.
            result["robot_handoff_ready"] = False
            result["robot_handoff_error"] = str(exc)

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
            result["final_score"],
            containment_violations=(
                result.get("detection", {})
                .get("features", {})
                .get("containment_violations")
            )
        )

        # =========================
        # Signal Filter
        # =========================

        result["signal"] = evaluate_signal(
            result.get("quality"),
            result["final_score"],
            confirmation,
            mode=MODE,
            min_score=MIN_SCORE
        )

        # =========================
        # TradingView Bridge
        # =========================

        result["tradingview"] = create_signal_payload(
            symbol,
            timeframe,
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
            timeframe,
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
