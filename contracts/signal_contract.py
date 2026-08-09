"""
contracts.signal_contract

BybitScanner Signal Contract

Единый формат внешнего объекта сигнала.

Отвечает за:
- структуру JSON;
- совместимость данных;
- подготовку внешнего контракта.

Не выполняет:
- анализ рынка;
- Geometry;
- Validation;
- Score расчёт;
- торговые решения.
"""


from datetime import datetime



def build_signal_contract(
    symbol,
    timeframe,
    pattern,
    score,
    quality,
    direction,
    geometry,
    validation,
    tradingview_url
):
    """
    Создаёт стандартный Signal Contract.

    Используется:
    - TradingView Bridge;
    - Trainer;
    - внешние интеграции.

    Сохраняет:
    - market;
    - pattern_data;
    - geometry;
    - validation;
    - tradingview;
    - trainer.
    """


    return {


        #
        # Metadata
        #

        "created_at":
            datetime.utcnow().isoformat(),



        #
        # Legacy compatibility
        #

        "symbol":
            symbol,


        "exchange":
            "BYBIT",


        "timeframe":
            timeframe,


        "pattern":
            pattern,


        "score":
            score,


        "quality":
            quality,


        "direction":
            direction,


        "geometry":
            geometry,



        #
        # New Contract
        #

        "market":
            {

                "symbol":
                    symbol,

                "exchange":
                    "BYBIT",

                "timeframe":
                    timeframe

            },



        "pattern_data":
            {

                "name":
                    pattern,

                "score":
                    score,

                "quality":
                    quality,

                "direction":
                    direction

            },



        "validation":
            validation,



        "tradingview":
            {

                "url":
                    tradingview_url

            },



        "trainer":
            {

                "source":
                    "BybitScanner"

            }

    }