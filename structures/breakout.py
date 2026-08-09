"""
structures/breakout.py

Проверка выхода цены за границы структуры.

Отвечает только за качество удержания цены внутри
геометрической модели.

Не определяет:
- wedge;
- channel;
- triangle.

Только проверяет:
- количество свечей вне границ;
- силу пробоев;
- качество структуры.
"""


def check_boundary_fit(
    candles,
    upper_line,
    lower_line,
    wick_tolerance=0.005,
    close_tolerance=0.002
):
    """
    Проверяет, насколько цена соответствует границам структуры.

    candles:
        список свечей вида:
        {
            "high": float,
            "low": float,
            "close": float
        }

    upper_line:
        верхняя линия:
        {
            "slope": float,
            "intercept": float
        }

    lower_line:
        нижняя линия:
        {
            "slope": float,
            "intercept": float
        }


    Возвращает:
    {
        "valid": bool,
        "inside_ratio": float,
        "outside_count": int,
        "reason": str
    }
    """


    if not candles:
        return {
            "valid": False,
            "inside_ratio": 0,
            "outside_count": 0,
            "reason": "No candles"
        }



    outside = 0
    total = len(candles)



    for index, candle in enumerate(candles):


        upper_price = (
            upper_line["slope"] * index
            +
            upper_line["intercept"]
        )


        lower_price = (
            lower_line["slope"] * index
            +
            lower_line["intercept"]
        )


        high = candle["high"]
        low = candle["low"]
        close = candle["close"]



        # сильный выход свечи вверх

        if high > upper_price * (1 + wick_tolerance):

            outside += 1
            continue



        # сильный выход вниз

        if low < lower_price * (1 - wick_tolerance):

            outside += 1
            continue



        # закрытие вне структуры

        if (
            close > upper_price * (1 + close_tolerance)
            or
            close < lower_price * (1 - close_tolerance)
        ):

            outside += 1



    inside_ratio = (
        (total - outside)
        /
        total
        *
        100
    )


    return {

        "valid":
            inside_ratio >= 70,

        "inside_ratio":
            round(
                inside_ratio,
                2
            ),

        "outside_count":
            outside,

        "reason":
            (
                "Structure boundaries respected"
                if inside_ratio >= 70
                else
                "Too many candles outside structure"
            )
    }