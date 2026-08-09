"""
structures/price_position.py

Проверка положения цены относительно структуры.

Отвечает только за:
- нахождение свечей внутри структуры;
- количество выходов за границы;
- качество удержания границ.

Не определяет:
- тип структуры;
- score;
- торговый сигнал.
"""


def calculate_price_position(
    candles,
    upper_line,
    lower_line
):
    """
    Анализирует положение свечей относительно линий структуры.

    candles:
        список свечей.
        Ожидаемый формат:
        {
            "high": цена,
            "low": цена
        }

    upper_line:
        {
            "slope":,
            "intercept":
        }

    lower_line:
        {
            "slope":,
            "intercept":
        }
    """


    if not candles:
        return {
            "valid": False,
            "reason": "No candles"
        }


    inside = 0
    outside = 0
    upper_breaks = 0
    lower_breaks = 0


    for index, candle in enumerate(candles):

        high = candle.get(
            "high",
            0
        )

        low = candle.get(
            "low",
            0
        )


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


        if high <= upper_price and low >= lower_price:

            inside += 1

        else:

            outside += 1


        if high > upper_price:

            upper_breaks += 1


        if low < lower_price:

            lower_breaks += 1



    total = len(candles)


    inside_percent = (
        inside / total
    ) * 100


    outside_percent = (
        outside / total
    ) * 100



    return {

        "valid":
            True,


        "inside_candles":
            inside,


        "outside_candles":
            outside,


        "inside_percent":
            round(
                inside_percent,
                2
            ),


        "outside_percent":
            round(
                outside_percent,
                2
            ),


        "upper_breaks":
            upper_breaks,


        "lower_breaks":
            lower_breaks,


        "quality":
            classify_price_quality(
                inside_percent,
                upper_breaks,
                lower_breaks
            )
    }



def classify_price_quality(
    inside_percent,
    upper_breaks,
    lower_breaks
):
    """
    Оценивает качество удержания границ.

    Только геометрическая оценка.
    """


    total_breaks = (
        upper_breaks
        +
        lower_breaks
    )


    if inside_percent >= 85 and total_breaks <= 3:

        return "Excellent"


    if inside_percent >= 70 and total_breaks <= 8:

        return "Acceptable"


    if inside_percent >= 50:

        return "Weak"


    return "Invalid"