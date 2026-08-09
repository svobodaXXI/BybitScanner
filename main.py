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

from analyzer import analyze_symbol
from bybit_api import get_symbols
from config import MODE, MIN_SCORE, MAX_SYMBOLS

from signal_adapter import prepare_signal
from signal_memory import update_signal
from notification import send_signal


def main():
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

            if not pattern:
                print(f"{symbol:<15} no wedge")
                continue

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

    print()
    print("=" * 60)
    print("Scan finished")
    print("=" * 60)


if __name__ == "__main__":
    main()
