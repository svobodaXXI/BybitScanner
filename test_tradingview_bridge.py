"""
test_tradingview_bridge.py

Тест TradingView Bridge.

Проверяет полный цикл:

Analyzer
    ↓
TradingView Bridge
    ↓
Signal Contract
    ↓
signals/*.json
"""

import json
from pathlib import Path
from datetime import datetime

from analyzer.core import analyze_symbol
from tradingview_bridge import create_signal_payload


SYMBOL = "INJUSDT"
TIMEFRAME = "5"


def main():

    analysis = analyze_symbol(SYMBOL)

    if not analysis.get("result"):

        print("Нет результата анализа")
        return

    result = analysis["result"]

    # --------------------------------------------------
    # Строим НОВЫЙ Signal Payload через Bridge
    # --------------------------------------------------

    payload = create_signal_payload(

        symbol=SYMBOL,

        timeframe=TIMEFRAME,

        result=result

    )

    # --------------------------------------------------
    # Для удобства тестирования временно добавляем
    # служебные блоки.
    # Они не ломают Signal Contract.
    # --------------------------------------------------

    payload["geometry"] = result.get(
        "geometry",
        {}
    )

    payload["validation"] = result.get(
        "validation",
        {}
    )

    payload["confirmation"] = result.get(
        "confirmation",
        {}
    )

    payload["score_breakdown"] = result.get(
        "score_breakdown",
        {}
    )

    payload["warnings"] = result.get(
        "warnings",
        []
    )

    payload["detection"] = result.get(
        "detection",
        {}
    )

    payload["signal"] = result.get(
        "signal",
        {}
    )

    payload["final_score"] = result.get(
        "final_score",
        result.get(
            "score",
            0
        )
    )

    # --------------------------------------------------
    # Проверяем Overlay
    # --------------------------------------------------

    print()

    print("Overlay:")

    print(

        json.dumps(

            payload.get(
                "overlay",
                {}
            ),

            indent=4,

            ensure_ascii=False

        )

    )

    # --------------------------------------------------
    # Сохраняем
    # --------------------------------------------------

    Path(
        "signals"
    ).mkdir(
        exist_ok=True
    )

    filename = (

        f"signals/{SYMBOL}_"

        f"{datetime.now():%Y%m%d_%H%M%S}.json"

    )

    with open(

        filename,

        "w",

        encoding="utf-8"

    ) as f:

        json.dump(

            payload,

            f,

            indent=4,

            ensure_ascii=False

        )

    print()

    print(

        f"Signal сохранён: {filename}"

    )


if __name__ == "__main__":

    main()