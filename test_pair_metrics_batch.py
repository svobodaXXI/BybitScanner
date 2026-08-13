"""
test_pair_metrics_batch.py

Массовый диагностический прогон Pair Metrics.

Не изменяет:
- Geometry Ranking;
- Validation;
- сигналы;
- Telegram logic.

Собирает текущую выбранную geometry
по ограниченному набору символов
и сохраняет метрики в CSV.
"""


import csv
import io
from contextlib import redirect_stdout

from analyzer import analyze_symbol
from bybit_api import get_symbols


OUTPUT_FILE = "reports/pair_metrics_batch.csv"

MAX_SYMBOLS = 50


def extract_row(symbol, outer):
    result = (
        outer.get("result")
        if isinstance(outer, dict)
        else None
    )

    if not isinstance(result, dict):
        return {
            "symbol": symbol,
            "has_result": False
        }

    geometry = (
        result.get("geometry")
        or {}
    )

    metrics = (
        geometry.get("pair_metrics")
        or {}
    )

    return {
        "symbol":
            symbol,

        "has_result":
            True,

        "pattern":
            result.get("pattern"),

        "score":
            result.get(
                "final_score",
                result.get(
                    "score"
                )
            ),

        "boundary_order_valid":
            metrics.get(
                "boundary_order_valid"
            ),

        "boundary_crossed":
            metrics.get(
                "boundary_crossed"
            ),

        "true_converging":
            metrics.get(
                "true_converging"
            ),

        "compression_percent":
            metrics.get(
                "compression_percent"
            ),

        "anchor_balance":
            metrics.get(
                "anchor_balance"
            ),

        "slope_balance":
            metrics.get(
                "slope_balance"
            ),

        "shared_structure_span":
            metrics.get(
                "shared_structure_span"
            ),

        "common_span":
            metrics.get(
                "common_span"
            ),

        "convergence_strength":
            metrics.get(
                "convergence_strength"
            )
    }


def main():
    symbols = get_symbols()

    symbols = symbols[
        :MAX_SYMBOLS
    ]

    rows = []

    print(
        f"Pair Metrics batch: "
        f"{len(symbols)} symbols"
    )

    for index, symbol in enumerate(
        symbols,
        1
    ):
        print(
            f"[{index}/{len(symbols)}] "
            f"{symbol}"
        )

        try:
            with redirect_stdout(
                io.StringIO()
            ):
                outer = analyze_symbol(
                    symbol
                )

            row = extract_row(
                symbol,
                outer
            )

        except Exception as error:
            row = {
                "symbol":
                    symbol,

                "has_result":
                    False,

                "error":
                    str(error)
            }

        rows.append(
            row
        )

    fieldnames = [
        "symbol",
        "has_result",
        "pattern",
        "score",
        "boundary_order_valid",
        "boundary_crossed",
        "true_converging",
        "compression_percent",
        "anchor_balance",
        "slope_balance",
        "shared_structure_span",
        "common_span",
        "convergence_strength",
        "error"
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames
        )

        writer.writeheader()

        for row in rows:
            writer.writerow(
                row
            )

    print()
    print(
        f"Saved: {OUTPUT_FILE}"
    )


if __name__ == "__main__":
    main()
