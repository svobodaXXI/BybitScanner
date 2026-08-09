"""
tradingview_bridge.py

BybitScanner TradingView Bridge v4

Центральный модуль связи между:
- анализатором;
- TradingView;
- Trainer;
- Signal Contract.

Отвечает за:
- генерацию ссылки TradingView;
- адаптацию данных;
- подготовку Overlay;
- передачу данных в Signal Contract.

Не выполняет:
- анализ рынка;
- поиск паттернов;
- расчёт Geometry;
- Validation;
- Score;
- торговые решения;
- Telegram отправку.
"""

from contracts.signal_contract import build_signal_contract


def normalize_symbol(symbol):
    """
    Приводит тикер к формату TradingView.
    """

    if not symbol:
        return ""

    symbol = symbol.upper()

    if ":" in symbol:
        return symbol

    return f"BYBIT:{symbol}"


def create_tradingview_url(
    symbol,
    timeframe="15"
):
    """
    Создаёт ссылку TradingView.
    """

    tv_symbol = normalize_symbol(symbol)

    return (
        "https://www.tradingview.com/chart/"
        f"?symbol={tv_symbol}"
        f"&interval={timeframe}"
    )


def extract_geometry(result):
    """
    Извлекает геометрическую модель.
    """

    geometry = result.get(
        "geometry",
        {}
    )

    return {

        "upper_line":
            geometry.get(
                "upper_line",
                {}
            ),

        "lower_line":
            geometry.get(
                "lower_line",
                {}
            ),

        "apex":
            geometry.get(
                "apex",
                {}
            ),

        "compression":
            geometry.get(
                "compression",
                {}
            ),

        "touches":
            geometry.get(
                "touches",
                {}
            ),

        "validation":
            geometry.get(
                "validation",
                result.get(
                    "validation",
                    {}
                )
            )

    }


def create_overlay_payload(geometry):
    """
    TradingView Overlay.

    Подготавливает геометрию для
    будущего Pine Script.

    Никаких вычислений не делает.
    """

    return {

        "upper_line": geometry.get(
            "upper_line",
            {}
        ),

        "lower_line": geometry.get(
            "lower_line",
            {}
        ),

        "apex": geometry.get(
            "apex",
            {}
        ),

        "compression": geometry.get(
            "compression",
            {}
        ),

        "touches": geometry.get(
            "touches",
            {}
        )

    }


def create_signal_payload(
    symbol,
    timeframe,
    result
):
    """
    Создаёт Signal Contract.

    Bridge только собирает данные.
    """

    confirmation = result.get(
        "confirmation",
        {}
    )

    quality = result.get(
        "quality",
        {}
    )

    score = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )

    geometry = extract_geometry(
        result
    )

    payload = build_signal_contract(

        symbol=symbol,

        timeframe=timeframe,

        pattern=result.get(
            "pattern",
            ""
        ),

        score=score,

        quality=quality.get(
            "quality",
            ""
        ),

        direction=confirmation.get(
            "direction",
            "WAIT"
        ),

        geometry=geometry,

        validation=geometry.get(
            "validation",
            {}
        ),

        tradingview_url=create_tradingview_url(
            symbol,
            timeframe
        )

    )

    # -----------------------------------
    # TradingView Overlay v4
    # -----------------------------------

    payload["overlay"] = create_overlay_payload(
        geometry
    )

    return payload


def create_trainer_example(
    payload
):
    """
    Подготавливает данные
    для Trainer.
    """

    return {

        "symbol":
            payload.get(
                "symbol"
            ),

        "timeframe":
            payload.get(
                "timeframe"
            ),

        "pattern":
            payload.get(
                "pattern"
            ),

        "geometry":
            payload.get(
                "geometry"
            ),

        "overlay":
            payload.get(
                "overlay",
                {}
            ),

        "validation":
            payload.get(
                "validation",
                {}
            ),

        "market":
            payload.get(
                "market",
                {}
            ),

        "source":
            "BybitScanner"

    }