"""
analyzer.candles

Работа со свечами.

Отвечает только за:
- загрузку OHLC данных;
- проверку количества свечей.
"""


from bybit_api import get_candles


def load_candles(
    symbol,
    timeframe,
    limit,
    minimum=50
):
    """
    Загружает свечи и проверяет достаточность данных.
    """

    df = get_candles(
        symbol,
        timeframe,
        limit
    )


    if df is None:

        return None


    if len(df) < minimum:

        return None


    return df