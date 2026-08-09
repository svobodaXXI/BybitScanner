"""
bybit_api.py

Data Layer BybitScanner.

Отвечает только за:
- получение рыночных данных Bybit;
- преобразование данных в DataFrame.

Не отвечает за:
- вывод в консоль;
- анализ;
- Geometry;
- Signal;
- Telegram.
"""


from pybit.unified_trading import HTTP
import pandas as pd

from config import BYBIT_CATEGORY


# ==================================================
# Bybit HTTP session
# ==================================================

session = HTTP(
    testnet=False
)

# Не позволяем requests автоматически
# использовать системные proxy-настройки Windows.
#
# Это необходимо, поскольку локальный SOCKS proxy
# может быть установлен в Windows, но PySocks
# отсутствовать в текущем virtual environment.
session.client.trust_env = False


# ==================================================
# Symbols
# ==================================================

def get_symbols():

    data = session.get_tickers(
        category=BYBIT_CATEGORY
    )

    symbols = []

    for item in data["result"]["list"]:

        symbol = item["symbol"]

        if symbol.endswith("USDT"):
            symbols.append(symbol)

    symbols.sort()

    return symbols


# ==================================================
# Candles
# ==================================================

def get_candles(
    symbol,
    interval,
    limit
):

    try:

        data = session.get_kline(
            category=BYBIT_CATEGORY,
            symbol=symbol,
            interval=interval,
            limit=limit
        )

        rows = (
            data
            .get("result", {})
            .get("list", [])
        )

        if not rows:

            return pd.DataFrame()


        df = pd.DataFrame(

            rows,

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


        numeric = [

            "open",
            "high",
            "low",
            "close",
            "volume"

        ]


        for column in numeric:

            df[column] = pd.to_numeric(

                df[column],

                errors="coerce"

            )


        df = df.dropna(
            subset=numeric
        )


        if df.empty:

            return pd.DataFrame()


        df["time"] = pd.to_numeric(
            df["time"],
            errors="coerce"
        )


        df = df.dropna(
            subset=["time"]
        )


        df = df.sort_values(
            "time"
        ).reset_index(
            drop=True
        )


        return df


    except Exception as error:

        print(
            f"[BYBIT ERROR] {symbol}: {error}"
        )

        return pd.DataFrame()