"""
main.py

Точка входа BybitScanner.

Текущий режим:

- получение актуальных Bybit USDT Linear Perpetual инструментов;
- ограниченный тестовый запуск через MAX_SYMBOLS;
- анализ выбранных инструментов;
- адаптация найденного сигнала;
- сохранение сигнала в памяти;
- Telegram production mode;
- компактный вывод в консоль.
"""

import config
import time

from analyzer import analyze_symbol
from bybit_api import get_symbols
from config import MODE, MIN_SCORE, MAX_SYMBOLS

from signal_adapter import prepare_signal
from signal_memory import update_signal
from notification import (
    send_message_to_recipients as send_message,
    send_signal,
)


def build_scan_finished_message(
    approved_pattern_count,
    elapsed_minutes,
    elapsed_remainder,
):
    """Build the final Scanner notification from the admission-owned count."""

    return (
        "Сканирование завершено\n"
        f"Найдено сигналов: {approved_pattern_count}\n"
        f"Elapsed: "
        f"{elapsed_minutes:02d}:"
        f"{elapsed_remainder:02d}"
    )


def main():
    scan_started_at = time.perf_counter()
    approved_pattern_count = 0

    symbols = get_symbols()

    if MAX_SYMBOLS is not None:
        symbols = symbols[:MAX_SYMBOLS]

    print("=" * 60)
    print("BybitScanner")
    print("=" * 60)

    print(f"Mode              : {MODE}")
    print(f"Minimum Score     : {MIN_SCORE}")
    print(f"Symbols           : {len(symbols)}")
    print(
        "Telegram Test     : "
        f"{config.TELEGRAM_TEST_MODE}"
    )

    print("=" * 60)
    print()

    for symbol in symbols:
        try:
            analysis_result = analyze_symbol(symbol)

            if not analysis_result:
                print(f"{symbol:<15} NO RESULT")
                continue

            analysis = analysis_result.get("result")

            if not analysis:
                print(f"{symbol:<15} no wedge")
                continue

            pattern = analysis.get("pattern")

            score = analysis.get(
                "final_score",
                analysis.get("score", 0)
            )

            if pattern in (None, "", "No wedge", "Unknown"):
                print(f"{symbol:<15} no wedge")
                continue

            signal_decision = analysis.get("signal") or {}

            if not signal_decision.get("approved", False):
                telegram_sent = False

                if config.TELEGRAM_TEST_MODE:
                    telegram_sent = send_signal(
                        {
                            **analysis,
                            "symbol": symbol,
                            "final_score": score
                        },
                        test_mode=True
                    )

                print(
                    f"{symbol:<15} "
                    f"{pattern:<20} "
                    f"score={score} "
                    f"signal=REJECTED "
                    f"telegram="
                    f"{'TEST' if telegram_sent else 'NO'}"
                )
                continue

            approved_pattern_count += 1

            signal = prepare_signal(
                symbol,
                analysis
            )

            if not signal:
                print(
                    f"{symbol:<15} SIGNAL ADAPTER ERROR"
                )
                continue

            status = update_signal(
                signal
            )

            telegram_sent = False

            telegram_payload = {
                **analysis,
                "symbol": symbol,
                "final_score": signal["score"]
            }

            if config.TELEGRAM_TEST_MODE:
                telegram_sent = send_signal(
                    telegram_payload,
                    test_mode=True
                )

            elif status in (
                "NEW",
                "STRENGTHENING"
            ):
                telegram_sent = send_signal(
                    telegram_payload
                )

            print(
                f"{symbol:<15} "
                f"{pattern:<20} "
                f"score={score} "
                f"signal={status} "
                f"telegram="
                f"{'SENT' if telegram_sent else 'NO'}"
            )

        except Exception as e:
            error_text = str(e)

            if len(error_text) > 45:
                error_text = error_text[:42] + "..."

            print(
                f"{symbol:<15} "
                f"ERROR: {error_text}"
            )

    print(f"Найдено паттернов: {approved_pattern_count}")

    elapsed_seconds = (
        time.perf_counter()
        - scan_started_at
    )

    elapsed_minutes = int(
        elapsed_seconds // 60
    )

    elapsed_remainder = int(
        elapsed_seconds % 60
    )

    print()
    print("=" * 60)
    print("Scan finished")
    print(
        f"Elapsed: "
        f"{elapsed_minutes:02d}:"
        f"{elapsed_remainder:02d}"
    )
    print("=" * 60)

    try:
        send_message(
            build_scan_finished_message(
                approved_pattern_count,
                elapsed_minutes,
                elapsed_remainder,
            )
        )
    except Exception as e:
        print(
            "[TELEGRAM SCAN FINISH ERROR]",
            e
        )


if __name__ == "__main__":
    main()
