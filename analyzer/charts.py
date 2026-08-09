"""
analyzer.charts

Отвечает только за построение графиков.
"""


from chart_clean import draw_chart


def create_chart(
    df,
    highs,
    lows,
    symbol,
    result
):
    """
    Построение графика анализа.
    """

    draw_chart(
        df,
        highs,
        lows,
        symbol,
        result
    )