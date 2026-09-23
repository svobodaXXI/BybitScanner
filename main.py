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
import os
import time

from analyzer import analyze_symbol
from bybit_api import get_symbols
from config import MODE, MIN_SCORE, MAX_SYMBOLS

from signal_adapter import prepare_signal
from signal_memory import update_signal
from scanner_diary import record_scanner_diary_observation
from scanner_diary_factors import record_scanner_p0_factors
from telegram_labels import SCANNER_EMOJI
from notification import (
    send_message_to_recipients as send_message,
    send_signal,
)


def build_scan_started_message(
    mode,
    min_score,
    symbol_count,
):
    """Build the Scanner-started notification announced before the scan loop."""

    return (
        f"{SCANNER_EMOJI} Сканер запущен\n"
        f"Mode: {mode}\n"
        f"Minimum Score: {min_score}\n"
        f"Symbols: {symbol_count}"
    )


def build_scan_finished_message(
    approved_pattern_count,
    sent_to_telegram_count,
    total_symbols_scanned,
    elapsed_minutes,
    elapsed_remainder,
    box_observation_count=0,
):
    """Build the final Scanner notification from the admission-owned count."""

    return (
        "🏁 Сканирование завершено\n"
        f"Найдено сигналов: {approved_pattern_count}\n"
        f"Отправлено в Telegram: {sent_to_telegram_count}\n"
        + (f"Наблюдений коробки Икигаи: {box_observation_count}\n" if box_observation_count else "")
        + f"Просканировано тикеров: {total_symbols_scanned}\n"
        f"Elapsed: "
        f"{elapsed_minutes:02d}:"
        f"{elapsed_remainder:02d}"
    )


def run_scan_pass():
    """Run exactly one Scanner scan pass over all discovered symbols.

    Extracted from main() as a reusable, throttled-repeatable unit (mirroring
    Freqtrade's Worker._process_running() pattern) so terminal/runtime's
    ScannerControlRuntime can invoke it repeatedly while RUNNING, instead of
    main() only ever being a one-shot script. Behavior is unchanged.
    """

    scan_started_at = time.perf_counter()
    approved_pattern_count = 0
    sent_to_telegram_count = 0
    box_observation_count = 0

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

    try:
        send_message(
            build_scan_started_message(
                MODE,
                MIN_SCORE,
                len(symbols),
            )
        )
    except Exception as e:
        print(
            "[TELEGRAM SCAN START ERROR]",
            e
        )

    for symbol in symbols:
        try:
            analysis_result = analyze_symbol(symbol)

            if not analysis_result:
                print(f"{symbol:<15} NO RESULT")
                continue

            # Local-only research observer: reuse OHLC even without a wedge.
            # Never let detection/render failures suppress existing delivery.
            if (
                os.environ.get("BYBITSCANNER_L_SHAPE_OBSERVATIONS") == "1"
                and analysis_result.get("data") is not None
            ):
                try:
                    from l_shape_scanner import observe_l_shape

                    observe_l_shape(
                        symbol, analysis_result["data"], timeframe=config.TIMEFRAME,
                    )
                except Exception as observation_error:
                    print(f"{symbol:<15} L-SHAPE ERROR: {observation_error}")

            # Experimental Box observations are explicitly opt-in and use
            # the same fetched OHLC snapshot even when no Wedge exists.
            # A Box photo never enters the Wedge quality/Robot admission path.
            if (
                os.environ.get("BYBITSCANNER_IKIGAI_BOX_SIGNALS") == "1"
                and analysis_result.get("data") is not None
            ):
                # The confirmed-formation sender is stateless, so it runs on
                # every pass and the very first one can already report Boxes
                # that formed before the Scanner started.
                try:
                    from ikigai_box_scanner import send_ikigai_box_observation

                    box_sent = send_ikigai_box_observation(
                        symbol,
                        analysis_result["data"],
                        timeframe=config.TIMEFRAME,
                        test_mode=config.TELEGRAM_TEST_MODE,
                    )
                    if box_sent:
                        box_observation_count += 1
                        sent_to_telegram_count += 1
                        print(f"{symbol:<15} IKIGAI BOX observation SENT")
                except Exception as box_error:
                    # An experimental pattern must not suppress the existing
                    # Wedge Scanner signal on the same market.
                    print(f"{symbol:<15} IKIGAI BOX ERROR: {box_error}")

                # WATCH is an additional early-observation mode, never a
                # replacement: its process-local cursor deliberately only
                # bootstraps on the first pass and emits from the next closed
                # candle on. A WATCH card for an A/B pair the confirmed sender
                # already delivered is suppressed by the shared signal_memory
                # identity, so no second mechanism is needed here.
                if os.environ.get("BYBITSCANNER_IKIGAI_BOX_WATCH") == "1":
                    try:
                        from ikigai_box_watch_stream import process_ikigai_box_watches

                        watch_sent = process_ikigai_box_watches(
                            symbol,
                            analysis_result["data"],
                            timeframe=config.TIMEFRAME,
                            test_mode=config.TELEGRAM_TEST_MODE,
                        )
                        if watch_sent:
                            box_observation_count += 1
                            sent_to_telegram_count += 1
                            print(f"{symbol:<15} IKIGAI BOX WATCH observation SENT")
                    except Exception as watch_error:
                        print(f"{symbol:<15} IKIGAI BOX WATCH ERROR: {watch_error}")

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

            # Trading Diary is an opt-in observational sink. Its failure must not
            # change Scanner admission, notifications, or any trading behavior.
            try:
                diary_observed_at_ms = int(time.time() * 1000)
                diary_result = record_scanner_diary_observation(
                    symbol=symbol,
                    analysis_result=analysis_result,
                    timeframe=config.TIMEFRAME,
                    scanner_mode=MODE,
                    observed_at_ms=diary_observed_at_ms,
                )
                if (
                    diary_result.setup_instance_id is not None
                    and diary_result.decision_event_id is not None
                ):
                    record_scanner_p0_factors(
                        setup_instance_id=diary_result.setup_instance_id,
                        decision_event_id=diary_result.decision_event_id,
                        analysis=analysis,
                        observed_at_ms=diary_observed_at_ms,
                    )
            except Exception as diary_error:
                print(
                    f"{symbol:<15} TRADING DIARY ERROR: "
                    f"{str(diary_error)[:80]}"
                )

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

            if telegram_sent:
                sent_to_telegram_count += 1

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
    if box_observation_count:
        print(f"Наблюдений коробки Икигаи: {box_observation_count}")
    print(f"Отправлено в Telegram: {sent_to_telegram_count}")
    print(f"Просканировано тикеров: {len(symbols)}")

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
                sent_to_telegram_count,
                len(symbols),
                elapsed_minutes,
                elapsed_remainder,
                box_observation_count=box_observation_count,
            )
        )
    except Exception as e:
        print(
            "[TELEGRAM SCAN FINISH ERROR]",
            e
        )


def main():
    run_scan_pass()


if __name__ == "__main__":
    main()
