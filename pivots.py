"""
pivots.py

Поиск Pivot High / Pivot Low.

Ответственность:
- анализ локальных экстремумов;
- подготовка точек для Geometry Engine.

Не отвечает за:
- торговые решения;
- сигналы;
- Telegram.
"""


def find_pivots(df, left=3, right=3, min_change=0.003):

    highs = []
    lows = []

    if df is None or df.empty:
        return [], []


    # дополнительная очистка входных данных
    required = [
        "high",
        "low"
    ]

    for col in required:

        if col not in df.columns:
            return [], []

        df[col] = df[col].apply(
            lambda x: float(x)
            if x is not None
            else None
        )


    df = df.dropna(
        subset=required
    ).reset_index(drop=True)


    # Column arrays: the same values and comparisons as the former per-row
    # df.loc slices (identical output), without pandas indexing per candle.
    high_values = df["high"].to_numpy()
    low_values = df["low"].to_numpy()

    for i in range(left, len(df) - right):

        high = high_values[i]
        low = low_values[i]


        if (
            high > high_values[i-left:i].max()
            and high > high_values[i+1:i+right+1].max()
        ):

            highs.append({
                "index": i,
                "price": high,
                "type": "high"
            })


        if (
            low < low_values[i-left:i].min()
            and low < low_values[i+1:i+right+1].min()
        ):

            lows.append({
                "index": i,
                "price": low,
                "type": "low"
            })


    return (
        filter_pivots(highs, min_change),
        filter_pivots(lows, min_change)
    )



def filter_pivots(points, min_change):

    if not points:
        return []


    result = [
        points[0]
    ]

    last_price = points[0]["price"]


    for p in points[1:]:

        if last_price == 0:
            continue


        change = abs(
            p["price"] - last_price
        ) / last_price


        if change >= min_change:

            result.append(p)
            last_price = p["price"]


    return result