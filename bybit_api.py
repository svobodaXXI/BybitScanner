"""
bybit_api.py

Data Layer BybitScanner.

Отвечает только за:
- получение списка активных Bybit USDT perpetual инструментов;
- получение рыночных данных Bybit;
- преобразование данных в DataFrame.

Не отвечает за:
- вывод в консоль;
- анализ;
- Geometry;
- Signal;
- Telegram.
"""

import sys

from pybit.unified_trading import HTTP
import pandas as pd

from config import BYBIT_CATEGORY


# ==================================================
# Bybit HTTP session
# ==================================================

session = HTTP(
    testnet=False
)

WINDOWS_BYBIT_PROXY = "socks5h://127.0.0.1:10808"


def default_bybit_proxies(platform: str) -> dict[str, str]:
    """Proxies for the Bybit session by platform.

    The Windows workstation reaches Bybit only through the local Happ SOCKS5
    proxy (requests and DNS). A Linux server (the VPS PAPER contour) connects
    directly: there is no such proxy on it, and a dead 127.0.0.1:10808 made the
    Scanner exit on its first market-data request.
    """
    if platform == "win32":
        return {"http": WINDOWS_BYBIT_PROXY, "https": WINDOWS_BYBIT_PROXY}
    return {}


session.client.trust_env = False
session.client.proxies.update(default_bybit_proxies(sys.platform))


# ==================================================
# Symbols
# ==================================================

def get_symbols():
    """
    Возвращает актуальный список активных
    Bybit USDT Linear Perpetual инструментов.

    Источник:
    Bybit Instruments Info.

    Используется pagination, чтобы не потерять
    инструменты при количестве больше лимита API.
    """

    symbols = []
    cursor = None

    while True:

        params = {
            "category": BYBIT_CATEGORY,
            "limit": 1000
        }

        if cursor:
            params["cursor"] = cursor

        data = session.get_instruments_info(
            **params
        )

        result = data.get(
            "result",
            {}
        )

        items = result.get(
            "list",
            []
        )

        for item in items:

            symbol = item.get(
                "symbol",
                ""
            )

            quote_coin = item.get(
                "quoteCoin",
                ""
            )

            contract_type = item.get(
                "contractType",
                ""
            )

            status = item.get(
                "status",
                ""
            )

            if (
                quote_coin == "USDT"
                and contract_type == "LinearPerpetual"
                and status == "Trading"
                and symbol
            ):
                symbols.append(
                    symbol
                )

        cursor = result.get(
            "nextPageCursor"
        )

        if not cursor:
            break

    symbols = sorted(
        set(symbols)
    )

    return symbols


# ==================================================
# Candles
# ==================================================

def get_candles(
    symbol,
    interval,
    limit,
    *,
    end_ms=None,
):
    """
    Загружает свечи Bybit
    и возвращает pandas DataFrame.
    """

    try:

        params = dict(category=BYBIT_CATEGORY, symbol=symbol,
                      interval=interval, limit=limit)
        if end_ms is not None:
            # Historical preview; do not request candles later than signal time.
            params['end'] = int(end_ms)
        data = session.get_kline(**params)

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
