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


def detect_pivots(df, left=3, right=3):
    """
    Возвращает НЕотфильтрованные Pivot High / Pivot Low.

    Тот же алгоритм left/right и те же строгие сравнения,
    что и раньше в find_pivots; индексы — позиции в кадре
    после dropna/reset_index, как и прежде.

    Работает на копии данных и не изменяет переданный
    DataFrame. Смотрит только на свечи внутри переданного
    кадра: будущие свечи должен отсекать вызывающий код.
    """

    highs = []
    lows = []

    if df is None or df.empty:
        return [], []


    required = [
        "high",
        "low"
    ]

    for col in required:

        if col not in df.columns:
            return [], []


    frame = df.loc[
        :,
        required
    ].copy()


    for col in required:

        frame[col] = frame[col].apply(
            lambda x: float(x)
            if x is not None
            else None
        )


    frame = frame.dropna(
        subset=required
    ).reset_index(drop=True)


    for i in range(left, len(frame) - right):

        high = frame.loc[i, "high"]
        low = frame.loc[i, "low"]


        left_high = frame.loc[i-left:i-1, "high"]
        right_high = frame.loc[i+1:i+right, "high"]

        left_low = frame.loc[i-left:i-1, "low"]
        right_low = frame.loc[i+1:i+right, "low"]


        if (
            high > left_high.max()
            and high > right_high.max()
        ):

            highs.append({
                "index": i,
                "price": high,
                "type": "high"
            })


        if (
            low < left_low.min()
            and low < right_low.min()
        ):

            lows.append({
                "index": i,
                "price": low,
                "type": "low"
            })


    return highs, lows



def find_pivots(df, left=3, right=3, min_change=0.003):

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


    highs, lows = detect_pivots(
        df,
        left=left,
        right=right
    )


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