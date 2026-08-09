"""
analyzer.reports

Сохранение отчётов анализа.
"""


from report import save_report


def create_report(
    symbol,
    timeframe,
    result,
    highs,
    lows
):
    """
    Создание текстового отчёта.
    """

    save_report(
        symbol,
        timeframe,
        result,
        highs,
        lows
    )