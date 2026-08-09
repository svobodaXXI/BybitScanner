from pybit.unified_trading import HTTP
import pandas as pd
import numpy as np

session = HTTP(
    testnet=False
)

def get_candles(symbol, interval="5", limit=200):

    data = session.get_kline(
        category="linear",
        symbol=symbol,
        interval=interval,
        limit=limit
    )

    candles = data["result"]["list"]

    df = pd.DataFrame(
        candles,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover"
        ]
    )

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume"
    ]:
        df[col] = df[col].astype(float)

    df = df.sort_values("time").reset_index(drop=True)

    return df

def find_wedge(df):

    # берём последние 50 свечей для поиска фигуры
    data = df.tail(50)

    highs = data["high"].values
    lows = data["low"].values

    x = np.arange(len(data))

    # линии тренда
    high_line = np.polyfit(x, highs, 1)
    low_line = np.polyfit(x, lows, 1)

    high_slope = high_line[0]
    low_slope = low_line[0]

    # ширина клина в начале и конце
    start_width = highs[0] - lows[0]
    end_width = highs[-1] - lows[-1]

    narrowing = end_width < start_width

    result = {
        "high_slope": round(high_slope, 4),
        "low_slope": round(low_slope, 4),
        "narrowing": narrowing
    }

    # Falling wedge
    if (
        high_slope < 0
        and low_slope < 0
        and low_slope > high_slope
        and narrowing
    ):
        result["pattern"] = "Falling Wedge"
        return result

    # Rising wedge
    if (
        high_slope > 0
        and low_slope > 0
        and low_slope < high_slope
        and narrowing
    ):
        result["pattern"] = "Rising Wedge"
        return result

    result["pattern"] = "No wedge"

    return result

symbol = "SOLUSDT"

df = get_candles(symbol)

print(symbol)
print(find_wedge(df))