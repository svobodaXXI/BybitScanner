"""
breakout.py

Проверка пробоя графических фигур.

SNIPER B:
Pattern
   ↓
Breakout confirmation
   ↓
Waiting retest
"""

def calculate_line(
    slope,
    intercept,
    index
):
    """
    Расчёт значения линии тренда.
    """

    return (
        slope * index
        + intercept
    )

def check_breakout(
    df,
    pattern_result
):
    """
    Проверяет пробой фигуры.

    Parameters
    ----------
    df :
        DataFrame свечей Bybit

    pattern_result :
        результат analyze_wedge()

    Returns
    -------
    dict
        информация о пробое
    """

    if pattern_result is None:

        return {
            "breakout": False,
            "status": "NO_PATTERN"
        }

    pattern = pattern_result.get(
        "pattern"
    )

    if pattern == "No wedge":

        return {
            "breakout": False,
            "status": "NO_PATTERN"
        }

    # последняя свеча

    candle = df.iloc[-1]

    index = len(df) - 1

    close = float(
        candle["close"]
    )

    high_line = calculate_line(
        pattern_result["high_slope"],
        pattern_result["high_intercept"],
        index
    )

    low_line = calculate_line(
        pattern_result["low_slope"],
        pattern_result["low_intercept"],
        index
    )

    direction = None
    breakout = False

    # Falling Wedge
    # выход вверх

    if pattern == "Falling Wedge":

        if close > high_line:

            breakout = True
            direction = "LONG"

    # Rising Wedge
    # выход вниз

    elif pattern == "Rising Wedge":

        if close < low_line:

            breakout = True
            direction = "SHORT"

    # Triangle

    elif pattern == "Triangle Compression":

        if close > high_line:

            breakout = True
            direction = "LONG"

        elif close < low_line:

            breakout = True
            direction = "SHORT"

    if breakout:

        return {

            "breakout": True,

            "direction":
                direction,

            "breakout_price":
                close,

            "candle_index":
                index,

            "status":
                "WAITING_RETEST"
        }

    return {

        "breakout": False,

        "status":
            "WAITING"
    }