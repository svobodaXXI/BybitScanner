"""#592: REAL PAPER matcher STOP -> fresh L-shape -> retry LIMIT -> TAKE.

Uses the pre-existing MIRROR E2E market/runtime harness and one authoritative
SQLite PAPER DB, including canonical Robot Admission, STOP execution,
protection obligations, existing Statistics/Diary, fees and restart fencing.
Only synthetic books/candles, no external API, LIVE, VPS or second engine.
"""
from __future__ import annotations

from decimal import Decimal
import os
import time
from unittest import mock

import robot_candidate_store
import tests.test_telegram_delivery  # existing offline Scanner configuration stubs
import l_shape_scanner
import pandas as pd
from tests.test_l_shape_detector import _long_shape
from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.application.robot_autopilot_shadow import (
    SOURCE_SCANNER, admit_arrived_auto_candidate,
)
from terminal.application.robot_control import start_robot
from terminal.diary.reentry import ReentryDiaryReader
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.runtime.scanner_process import run_scan_pass_in_child_process
from terminal.domain.models import Category, PositionKey, Symbol
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_mirror_standalone_paper_e2e import (
    ACCOUNT, FIVE, SYMBOL, MirrorStandaloneHarness, _RobotCandle,
)
from tests.test_robot_paper_acceptance import (
    _MutableBookProvider, _event_book, _start_robot_monitor, _wait_until,
)


class StopReentryPaperFillE2E(MirrorStandaloneHarness):
    def test_mirror_stop_then_fresh_lshape_limit_fill_take_diary_and_restart(self):
        # First campaign: a genuine Scanner MIRROR handoff confirmed by Nison
        # candles. Enable only for this isolated test; production default OFF.
        with mock.patch.dict(os.environ, {"BYBITSCANNER_STOP_REENTRY_AUTO": "1"}):
            tl = self.timeline
            self.assertEqual(self.scan(tl.breakout_open + 2 * FIVE)["new_candidates"], 1)
            arrived = self.scan(tl.t)
            self.assertEqual(len(arrived["standalone_handoffs"]), 1)
            first_id = arrived["standalone_handoffs"][0]

            closed_candle = _RobotCandle()
            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("105.3"), ask=Decimal("105.4"))
            runtime, instrument = self.runtime(CachedClosedCandleProvider(fetch=closed_candle, max_age_s=0), book)
            try:
                self.assertEqual(start_robot(database_path=self.db).recovery_status, "READY")
                store = SQLiteStore.open(self.db)
                try:
                    auto = store.get_robot_autopilot_state(ACCOUNT)
                    store.update_robot_autopilot_state(
                        ACCOUNT, mode="PAPER_AUTO", expected_version=auto.version,
                        updated_at_ms=int(time.time() * 1000),
                    )
                    admission = admit_arrived_auto_candidate(
                        store, ACCOUNT, source=SOURCE_SCANNER, candidate_ref=first_id,
                        protection_healthy=lambda: True,
                        candidate_fresh=lambda *_: True,
                        candidate_store_dir=self.candidates,
                        clock_ms=lambda: int(time.time() * 1000),
                        daily_loss_gate_enabled=False,
                    )
                    self.assertEqual(admission.result.outcome, OUTCOME_ALLOW, admission.result)
                    self.assertEqual(store._connection.execute(
                        "SELECT COUNT(*) FROM robot_reentry_attempts"
                    ).fetchone()[0], 1)
                finally:
                    store.close()

                _start_robot_monitor(runtime)
                key = PositionKey(ACCOUNT, Category.LINEAR, Symbol(SYMBOL), 0)

                def candidate(cid):
                    return runtime.call(lambda owner: owner.store.get_robot_candidate(cid))

                def limit(cid):
                    record = candidate(cid)
                    order_id = ((record.robot_state or {}).get("execution") or {}).get("limit_order_id")
                    return runtime.call(
                        lambda owner: owner.store.get_paper_limit(order_id, ACCOUNT)
                    ) if order_id else None

                first_order = _wait_until(lambda: limit(first_id))
                self.assertEqual(first_order.price, Decimal("105.2") + 2 * instrument.tick_size)
                book.set(SYMBOL, bid=first_order.price - instrument.tick_size, ask=first_order.price)
                first_trade = _wait_until(lambda: runtime.call(
                    lambda owner: owner.store.get_open_robot_trade_for_symbol(
                        ACCOUNT, Symbol(SYMBOL),
                    ),
                ))
                self.assertEqual(first_trade.candidate_id, first_id)

                def protection():
                    p = runtime.call(lambda owner: owner.store.get_protection_projection(key))
                    return p if p and p.stop_loss and p.take_profit else None

                first_protection = _wait_until(protection)
                # A real market-book STOP closes the first protected PAPER trade;
                # no synthetic INSERT into robot_trades or executions is used.
                stop_bid = first_protection.stop_loss - instrument.tick_size
                stop_ask = first_protection.stop_loss
                book.set(SYMBOL, bid=stop_bid, ask=stop_ask)
                event = _event_book(SYMBOL, bid=stop_bid, ask=stop_ask)
                runtime.call(lambda owner: owner.process_robot_market_event(
                    SYMBOL, event, event_id="reentry-first-stop",
                    received_at_ms=event.received_at_ms,
                ))
                stopped = _wait_until(lambda: (lambda t: t if t and t.exit_time_ms else None)(
                    runtime.call(lambda owner: owner.store.get_robot_trade(first_trade.trade_id)),
                ))
                self.assertEqual(stopped.exit_reason, "STOP")
                self.assertEqual(candidate(first_id).status, "CLOSED")
                self.assertIsNone(runtime.call(lambda owner: owner.store.get_open_robot_trade_for_symbol(
                    ACCOUNT, Symbol(SYMBOL),
                )))

                # Spawn the actual Scanner child. It persists the newly
                # detected post-STOP L-shape and relays its ID through the
                # production pipe to PaperRuntime's PAPER_AUTO dispatcher.
                # Real 5m exchange candles open on a strict grid. The prior
                # STOP can happen inside this candle; it becomes a valid
                # post-STOP confirmation only at the next aligned close.
                breakout_open = (stopped.exit_time_ms // FIVE) * FIVE
                self.assertLess(stopped.exit_time_ms, breakout_open + FIVE)
                candles = _long_shape().copy()
                candles["time"] = [
                    breakout_open - FIVE * (len(candles) - 1 - i)
                    for i in range(len(candles))
                ]
                runtime.call(lambda owner: owner.bind_autopilot_protection_health(
                    lambda: True
                ))
                dispatcher = runtime.call(
                    lambda owner: owner._dispatch_autopilot_shadow_scanner_candidate
                )
                book.set(SYMBOL, bid=Decimal("109.3"), ask=Decimal("109.4"))
                def scanner_candles(symbol, timeframe, limit, minimum=2):
                    return candles
                with mock.patch("analyzer.candles.load_candles", scanner_candles), \
                        mock.patch.dict(os.environ, {
                            "REENTRY_CHILD_CANDIDATES": str(self.candidates),
                            "REENTRY_CHILD_CHARTS": str(self.root),
                            "REENTRY_CHILD_BREAKOUT": str(breakout_open),
                        }):
                    run_scan_pass_in_child_process(
                        target="tests.test_stop_reentry_child_ipc:_child_scan_lshape",
                        robot_candidate_observer=dispatcher,
                    )
                def admitted_retry():
                    decisions = runtime.call(
                        lambda owner: owner.store.load_robot_auto_decisions(ACCOUNT)
                    )
                    for d in reversed(decisions):
                        if d.resulting_candidate_id != first_id and d.outcome == OUTCOME_ALLOW:
                            return d.resulting_candidate_id
                    return None
                try:
                    new_id = _wait_until(admitted_retry)
                except AssertionError:
                    decisions = runtime.call(
                        lambda owner: owner.store.load_robot_auto_decisions(ACCOUNT)
                    )
                    summary = [(d.candidate_ref, d.outcome, d.reason_code)
                               for d in decisions]
                    self.fail(f"Scanner pipe delivered but PAPER_AUTO denied: {summary}")
                self.assertEqual(candidate(new_id).status, "APPROVED")
                rows = runtime.call(lambda owner: owner.store._connection.execute(
                    """SELECT attempt_index,candidate_id,previous_stop_exec_id
                       FROM robot_reentry_attempts ORDER BY attempt_index"""
                ).fetchall())
                self.assertEqual([(r[0], r[1]) for r in rows],
                                 [(1, first_id), (2, new_id)])
                self.assertIsNotNone(rows[1]["previous_stop_exec_id"])

                # Real L-shape Robot monitor must see its own new retest,
                # then submit a new one-WV LIMIT. No extra open position existed
                # at admission time and no direct order call is made here.
                closed_candle.set({
                    "time_ms": stopped.exit_time_ms + 4,
                    "high": "109.5", "low": "109.1", "close": "109.3",
                })
                second_order = _wait_until(lambda: limit(new_id))
                self.assertNotEqual(first_order.order_id, second_order.order_id)
                self.assertEqual(second_order.filled_quantity, 0)
                book.set(SYMBOL, bid=second_order.price - instrument.tick_size,
                         ask=second_order.price)
                second_trade = _wait_until(lambda: (
                    lambda t: t if t is not None and t.candidate_id == new_id else None
                )(runtime.call(lambda owner: owner.store.get_open_robot_trade_for_symbol(
                    ACCOUNT, Symbol(SYMBOL),
                ))))
                self.assertNotEqual(first_trade.trade_id, second_trade.trade_id)
                self.assertEqual((second_trade.pattern, second_trade.entry_path),
                                 ("L-shape", "LIMIT"))
                second_protection = _wait_until(protection)
                self.assertGreater(second_protection.take_profit, second_trade.average_entry)

                # Canonical TAKE closes the retry; the Trading Diary derives
                # all financial values from real executions, not duplicates.
                exit_bid = second_protection.take_profit + instrument.tick_size
                exit_ask = exit_bid + instrument.tick_size
                book.set(SYMBOL, bid=exit_bid, ask=exit_ask)
                event2 = _event_book(SYMBOL, bid=exit_bid, ask=exit_ask)
                runtime.call(lambda owner: owner.process_robot_market_event(
                    SYMBOL, event2, event_id="reentry-second-take",
                    received_at_ms=event2.received_at_ms,
                ))
                taken = _wait_until(lambda: (lambda t: t if t and t.exit_time_ms else None)(
                    runtime.call(lambda owner: owner.store.get_robot_trade(second_trade.trade_id)),
                ))
                self.assertEqual(taken.exit_reason, "TAKE")
                self.assertEqual(candidate(new_id).status, "CLOSED")

                journal = ReentryDiaryReader(self.db).load()
                self.assertEqual(len(journal), 1)
                self.assertEqual([a.pattern for a in journal[0].attempts],
                                 ["MIRROR", "L-shape"])
                self.assertEqual([a.exit_reason for a in journal[0].attempts],
                                 ["STOP", "TAKE"])
                self.assertEqual(journal[0].filled_attempt_count, 2)
                self.assertIsNotNone(stopped.fees_costs_usdt)
                self.assertIsNotNone(taken.fees_costs_usdt)
                net_first = stopped.realized_pnl_usdt - stopped.fees_costs_usdt
                net_second = taken.realized_pnl_usdt - taken.fees_costs_usdt
                self.assertEqual(
                    [a.known_net_pnl_usdt for a in journal[0].attempts],
                    [net_first, net_second],
                )
                self.assertEqual(journal[0].known_net_pnl_usdt, net_first + net_second)
                self.assertLess(net_first, 0)
                self.assertGreater(net_second, 0)
                executions = runtime.call(
                    lambda owner: owner.store.load_executions_for_symbol(
                        ACCOUNT, Symbol(SYMBOL),
                    ),
                )
                self.assertGreaterEqual(len(executions), 4)
                self.assertEqual(
                    sum((fill.fee for fill in executions), Decimal("0")),
                    stopped.fees_costs_usdt + taken.fees_costs_usdt,
                )

                # Reboot from the SAME SQLite and confirm no repeat submission.
                runtime.close()
                runtime, _ = self.runtime(closed_candle, book)
                _start_robot_monitor(runtime)
                time.sleep(0.25)
                after = runtime.call(lambda owner: owner.store.load_executions_for_symbol(
                    ACCOUNT, Symbol(SYMBOL),
                ))
                self.assertEqual(len(after), len(executions))
                self.assertIsNone(runtime.call(lambda owner: owner.store.get_open_robot_trade_for_symbol(
                    ACCOUNT, Symbol(SYMBOL),
                )))
                self.assertEqual(candidate(new_id).status, "CLOSED")
            finally:
                runtime.close()
