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
    horn_found_count=0,
    horn_sent_count=0,
    mirror_candidate_count=0,
):
    """Build the final Scanner notification from the admission-owned count."""

    return (
        "🏁 Сканирование завершено\n"
        f"Найдено сигналов: {approved_pattern_count}\n"
        f"Отправлено в Telegram: {sent_to_telegram_count}\n"
        + (f"Наблюдений коробки Икигаи: {box_observation_count}\n" if box_observation_count else "")
        + (f"Рупор (наблюдение): найдено {horn_found_count}, отправлено {horn_sent_count}\n"
           if horn_found_count else "")
        + (f"MIRROR (наблюдение): новых кандидатов {mirror_candidate_count}\n"
           if mirror_candidate_count else "")
        + f"Просканировано тикеров: {total_symbols_scanned}\n"
        f"Elapsed: "
        f"{elapsed_minutes:02d}:"
        f"{elapsed_remainder:02d}"
    )


def observe_mirror_symbol(symbol, mirror_inputs):
    """MIRROR observation of one symbol: 1m first, then 5m with those 1m candles.

    Returns (new candidates, Telegram cards sent, errors). Observation only: a
    failure here never affects any other Scanner delivery.
    """
    from mirror_scanner import closed_rows, observe_mirror_levels, send_mirror_notifications

    found = sent = failed = 0
    fine = None
    if "1" in mirror_inputs:
        try:
            fine = closed_rows(mirror_inputs["1"]["candles"].iloc[:-1], "1")
        except Exception:
            fine = None
    for timeframe in ("1", "5"):
        inputs = mirror_inputs.get(timeframe)
        if inputs is None:
            continue
        try:
            summary = observe_mirror_levels(
                symbol, inputs["candles"], timeframe=timeframe,
                wedge_result=inputs["wedge_result"],
                horn_observation=inputs["horn_observation"],
                l_shape_observation=inputs["l_shape_observation"],
                fine_candles=fine if timeframe == "5" else None,
            )
            if summary:
                found += summary["new_candidates"]
                sent += send_mirror_notifications(
                    symbol, timeframe, test_mode=config.TELEGRAM_TEST_MODE,
                )
        except Exception as mirror_error:
            failed += 1
            print(f"{symbol:<15} {timeframe}m MIRROR ERROR: {mirror_error}", flush=True)
    return found, sent, failed


def run_scan_pass(
    *,
    box_plan_preparer=None,
    control_checkpoint=None,
    robot_candidate_observer=None,
    progress_observer=None,
):
    """Run one Scanner pass; observers receive persisted candidates and progress."""
    from pattern_robot_integration import robot_candidate_observer as observe

    with observe(robot_candidate_observer):
        return _run_scan_pass(
            box_plan_preparer=box_plan_preparer,
            control_checkpoint=control_checkpoint,
            progress_observer=progress_observer,
        )


def _run_scan_pass(*, box_plan_preparer=None, control_checkpoint=None, progress_observer=None):
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
    horn_found_count = 0
    horn_sent_count = 0
    error_count = 0

    symbols = get_symbols()

    if MAX_SYMBOLS is not None:
        symbols = symbols[:MAX_SYMBOLS]

    # Issue #504: progress is visible during the pass (console line flushed per
    # symbol/timeframe and progress.json on disk), never only at the end.
    from horn_scanner import (
        horn_observation_enabled,
        observe_broadening,
        send_broadening_observation,
        write_progress,
    )

    horn_enabled = horn_observation_enabled()

    from mirror_scanner import mirror_observation_enabled

    mirror_enabled = mirror_observation_enabled()
    mirror_candidate_count = 0

    def report_progress(position, symbol, timeframe):
        progress = {
            "symbols_done": position,
            "symbols_total": len(symbols),
            "symbol": symbol,
            "timeframe": timeframe,
            "horn_found": horn_found_count,
            "horn_sent": horn_sent_count,
            "mirror_candidates": mirror_candidate_count,
            "sent_to_telegram": sent_to_telegram_count,
            "errors": error_count,
        }
        print(
            f"[SCAN PROGRESS] {position}/{len(symbols)} {symbol} {timeframe}m "
            f"horn_found={horn_found_count} horn_sent={horn_sent_count} "
            f"telegram_sent={sent_to_telegram_count} errors={error_count}",
            flush=True,
        )
        try:
            write_progress(progress)
        except Exception as progress_error:
            print(f"[SCAN PROGRESS WRITE ERROR] {progress_error}", flush=True)
        if progress_observer is not None:
            progress_observer(progress)

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

    for position, symbol in enumerate(symbols, 1):
        # MIRROR reads the same snapshots after both timeframes, so a 5m retest
        # contact can be settled by this pass's 1m candles (no extra request).
        mirror_inputs = {}
        for timeframe in ("5", "1"):
            if control_checkpoint is not None and not control_checkpoint():
                print("[SCANNER] current pass stopped by owner")
                return
            horn = l_shape = None
            try:
                analysis_result = analyze_symbol(symbol, timeframe=timeframe)

                if not analysis_result:
                    print(f"{symbol:<15} {timeframe}m NO RESULT")
                    continue

                # L-shape is a normal owner-visible Telegram signal, even when
                # no Wedge exists. Its failure must not affect existing delivery.
                if analysis_result.get("data") is not None:
                    try:
                        from l_shape_scanner import (
                            observe_l_shape,
                            send_l_shape_observation,
                        )

                        l_shape = observe_l_shape(
                            symbol, analysis_result["data"], timeframe=timeframe,
                        )
                        if l_shape and send_l_shape_observation(
                            symbol, l_shape, timeframe=timeframe,
                            test_mode=config.TELEGRAM_TEST_MODE,
                        ):
                            sent_to_telegram_count += 1
                            print(f"{symbol:<15} {timeframe}m L-SHAPE observation SENT")
                    except Exception as observation_error:
                        error_count += 1
                        print(f"{symbol:<15} {timeframe}m L-SHAPE ERROR: {observation_error}")

                # #592: independently confirmed double TOP/BOTTOM after STOP.
                # Reuse this pass's already fetched 1m/5m closed bars and
                # the existing Scanner→Robot candidate observer/Admission.
                # OFF unless the owner's STOP-reentry feature is opted in.
                if (
                    os.environ.get("BYBITSCANNER_STOP_REENTRY_AUTO") == "1"
                    and analysis_result.get("data") is not None
                    and timeframe in ("1", "5")
                ):
                    try:
                        from geometry.double_extremum import frozen_neckline_snapshot
                        from pattern_robot_integration import prepare_robot_handoff
                        from signal_memory import load_memory, save_memory

                        frame = analysis_result["data"]
                        if len(frame) >= 8:
                            closed_rows = frame.iloc[:-1].to_dict("records")
                            candidate = frozen_neckline_snapshot(
                                symbol, timeframe, closed_rows,
                            )
                            if candidate is not None:
                                identity = (
                                    f"neckline:{symbol}:{timeframe}:"
                                    f"{candidate['pattern']}:"
                                    f"{candidate['neckline_entry']['breakout_time_ms']}"
                                )
                                memory = load_memory()
                                if identity not in memory:
                                    result = prepare_robot_handoff(
                                        candidate, timeframe=timeframe, enabled=True,
                                    )
                                    if result.candidate_id:
                                        memory[identity] = {
                                            "robot_candidate_id": result.candidate_id,
                                            "pattern": candidate["pattern"],
                                        }
                                        save_memory(memory)
                    except Exception as neckline_error:
                        error_count += 1
                        print(
                            f"{symbol:<15} {timeframe}m NECKLINE ERROR: "
                            f"{type(neckline_error).__name__}",
                            flush=True,
                        )

                # Broadening («Рупор») is observation only: chart + evidence,
                # no Robot/admission/orders. It runs next to Wedge and never
                # suppresses it; its failure must not affect other delivery.
                if horn_enabled and analysis_result.get("data") is not None:
                    try:
                        horn = observe_broadening(
                            symbol, analysis_result["data"], timeframe=timeframe,
                            wedge_result=analysis_result.get("result"),
                        )
                        if horn:
                            horn_found_count += 1
                            if send_broadening_observation(
                                symbol, horn, timeframe=timeframe,
                                test_mode=config.TELEGRAM_TEST_MODE,
                            ):
                                horn_sent_count += 1
                                sent_to_telegram_count += 1
                                print(f"{symbol:<15} {timeframe}m HORN observation SENT", flush=True)
                    except Exception as horn_error:
                        error_count += 1
                        print(f"{symbol:<15} {timeframe}m HORN ERROR: {horn_error}", flush=True)

                if mirror_enabled and analysis_result.get("data") is not None:
                    mirror_inputs[timeframe] = {
                        "candles": analysis_result["data"],
                        "wedge_result": analysis_result.get("result"),
                        "horn_observation": horn,
                        "l_shape_observation": l_shape,
                    }

                # Experimental Box observations are explicitly opt-in and use
                # the same fetched OHLC snapshot even when no Wedge exists.
                # A CONFIRMED Box is only frozen as BOX_PLAN_ONLY for the owner's
                # 🤖 Робот tap; the Scanner itself never admits it into the Robot.
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
                            timeframe=timeframe,
                            test_mode=config.TELEGRAM_TEST_MODE,
                            robot_plan_preparer=box_plan_preparer,
                        )
                        if box_sent:
                            box_observation_count += 1
                            sent_to_telegram_count += 1
                            print(f"{symbol:<15} {timeframe}m IKIGAI BOX observation SENT")
                    except Exception as box_error:
                        # An experimental pattern must not suppress the existing
                        # Wedge Scanner signal on the same market.
                        error_count += 1
                        print(f"{symbol:<15} {timeframe}m IKIGAI BOX ERROR: {box_error}")

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
                                timeframe=timeframe,
                                test_mode=config.TELEGRAM_TEST_MODE,
                            )
                            if watch_sent:
                                box_observation_count += 1
                                sent_to_telegram_count += 1
                                print(f"{symbol:<15} {timeframe}m IKIGAI BOX WATCH observation SENT")
                        except Exception as watch_error:
                            error_count += 1
                            print(f"{symbol:<15} {timeframe}m IKIGAI BOX WATCH ERROR: {watch_error}")

                analysis = analysis_result.get("result")

                if not analysis:
                    print(f"{symbol:<15} {timeframe}m no wedge")
                    continue

                pattern = analysis.get("pattern")

                score = analysis.get(
                    "final_score",
                    analysis.get("score", 0)
                )

                if pattern in (None, "", "No wedge", "Unknown"):
                    print(f"{symbol:<15} {timeframe}m no wedge")
                    continue

                signal_decision = analysis.get("signal") or {}

                # Trading Diary is an opt-in observational sink. Its failure must not
                # change Scanner admission, notifications, or any trading behavior.
                try:
                    diary_observed_at_ms = int(time.time() * 1000)
                    diary_result = record_scanner_diary_observation(
                        symbol=symbol,
                        analysis_result=analysis_result,
                        timeframe=timeframe,
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
                        f"{symbol:<15} {timeframe}m TRADING DIARY ERROR: "
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
                        f"{symbol:<15} {timeframe}m "
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
                        f"{symbol:<15} {timeframe}m SIGNAL ADAPTER ERROR"
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
                    f"{symbol:<15} {timeframe}m "
                    f"{pattern:<20} "
                    f"score={score} "
                    f"signal={status} "
                    f"telegram="
                    f"{'SENT' if telegram_sent else 'NO'}"
                )

            except Exception as e:
                error_count += 1
                error_text = str(e)

                if len(error_text) > 45:
                    error_text = error_text[:42] + "..."

                print(
                    f"{symbol:<15} {timeframe}m "
                    f"ERROR: {error_text}"
                )

            finally:
                report_progress(position, symbol, timeframe)

        if mirror_inputs:
            found, sent, failed = observe_mirror_symbol(symbol, mirror_inputs)
            mirror_candidate_count += found
            sent_to_telegram_count += sent
            error_count += failed

    print(f"Найдено паттернов: {approved_pattern_count}")
    if box_observation_count:
        print(f"Наблюдений коробки Икигаи: {box_observation_count}")
    if horn_found_count:
        print(f"Рупор (наблюдение): найдено {horn_found_count}, отправлено {horn_sent_count}")
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
                horn_found_count=horn_found_count,
                horn_sent_count=horn_sent_count,
                mirror_candidate_count=mirror_candidate_count,
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
