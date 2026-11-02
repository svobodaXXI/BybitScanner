"""#592: real MIRROR STOP -> compatible fresh Box -> owner PAPER grid fill/protection.

Isolated temporary PAPER SQLite; no exchange/VPS/LIVE or forged STOP ledger.
The production Robot monitor and ordered PaperRuntime process the new Box grid.
"""
from __future__ import annotations

from decimal import Decimal
import os
import time
from unittest import mock

from terminal.application.robot_autopilot import OUTCOME_ALLOW
from terminal.application.robot_autopilot_shadow import (
    SOURCE_BOX_PLAN, SOURCE_SCANNER, admit_arrived_auto_candidate,
)
from terminal.application.robot_control import start_robot
from terminal.domain.models import Category, PositionKey, Symbol
from terminal.diary.reentry import ReentryDiaryReader
from terminal.runtime.closed_candle_cache import CachedClosedCandleProvider
from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_mirror_standalone_paper_e2e import (
    ACCOUNT, FIVE, SYMBOL, MirrorStandaloneHarness, _RobotCandle,
)
from tests.test_robot_paper_acceptance import (
    _MutableBookProvider, _event_book, _start_robot_monitor, _wait_until,
)
from tests.test_stop_reentry_box_handoff import compatible_retry_box_plan


class BoxRetryRealPaperE2E(MirrorStandaloneHarness):
    def test_proven_mirror_stop_then_new_box_p1_fill_arms_stop_take(self):
        with mock.patch.dict(os.environ, {"BYBITSCANNER_STOP_REENTRY_AUTO": "1"}):
            timeline = self.timeline
            self.assertEqual(
                self.scan(timeline.breakout_open + 2 * FIVE)["new_candidates"], 1,
            )
            first_ids = self.scan(timeline.t)["standalone_handoffs"]
            self.assertEqual(len(first_ids), 1)
            first_id = first_ids[0]
            feed = _RobotCandle()
            cache = CachedClosedCandleProvider(max_age_s=60)
            cache._fetch = feed
            book = _MutableBookProvider()
            book.set(SYMBOL, bid=Decimal("105.3"), ask=Decimal("105.4"))
            runtime, instrument = self.runtime(cache, book)
            try:
                self.assertEqual(start_robot(database_path=self.db).recovery_status, "READY")
                with SQLiteStore.open(self.db) as store:
                    state = store.get_robot_autopilot_state(ACCOUNT)
                    store.update_robot_autopilot_state(
                        ACCOUNT, mode="PAPER_AUTO", expected_version=state.version,
                        updated_at_ms=int(time.time() * 1000),
                    )
                    original = admit_arrived_auto_candidate(
                        store, ACCOUNT, source=SOURCE_SCANNER,
                        candidate_ref=first_id,
                        protection_healthy=lambda: True,
                        candidate_fresh=lambda *_: True,
                        candidate_store_dir=self.candidates,
                        clock_ms=lambda: int(time.time() * 1000),
                        daily_loss_gate_enabled=False,
                    )
                    self.assertEqual(original.result.outcome, OUTCOME_ALLOW)
                    original_attempts = store._connection.execute(
                        "SELECT candidate_id, attempt_index FROM robot_reentry_attempts "
                        "ORDER BY attempt_index"
                    ).fetchall()
                    self.assertEqual([tuple(row) for row in original_attempts], [
                        (first_id, 1),
                    ])
                _start_robot_monitor(runtime)
                symbol = Symbol(SYMBOL)
                key = PositionKey(ACCOUNT, Category.LINEAR, symbol, 0)

                def candidate(cid):
                    return runtime.call(
                        lambda owner: owner.store.get_robot_candidate(cid),
                    )

                def protection():
                    p = runtime.call(
                        lambda owner: owner.store.get_protection_projection(key),
                    )
                    return p if p and p.stop_loss and p.take_profit else None

                def initial_limit():
                    state = (candidate(first_id).robot_state or {}).get("execution") or {}
                    oid = state.get("limit_order_id")
                    return runtime.call(
                        lambda owner: owner.store.get_paper_limit(oid, ACCOUNT),
                    ) if oid else None

                initial_order = _wait_until(initial_limit)
                book.set(SYMBOL, bid=initial_order.price - instrument.tick_size,
                         ask=initial_order.price)
                initial_trade = _wait_until(lambda: runtime.call(
                    lambda owner: owner.store.get_open_robot_trade_for_symbol(
                        ACCOUNT, symbol,
                    ),
                ))
                first_protection = _wait_until(protection)
                stop_bid = first_protection.stop_loss - instrument.tick_size
                book.set(SYMBOL, bid=stop_bid, ask=first_protection.stop_loss)
                stop_event = _event_book(
                    SYMBOL, bid=stop_bid, ask=first_protection.stop_loss,
                )
                runtime.call(lambda owner: owner.process_robot_market_event(
                    SYMBOL, stop_event, event_id="box-retry-original-stop",
                    received_at_ms=stop_event.received_at_ms,
                ))
                stopped = _wait_until(lambda: (
                    lambda row: row if row and row.exit_time_ms else None
                )(runtime.call(
                    lambda owner: owner.store.get_robot_trade(initial_trade.trade_id),
                )))
                self.assertEqual(stopped.exit_reason, "STOP")
                self.assertEqual(candidate(first_id).status, "CLOSED")
                self.assertIsNone(runtime.call(lambda owner:
                    owner.store.get_open_robot_trade_for_symbol(ACCOUNT, symbol),
                ))

                # The Box formation is genuinely newer, not a reused pre-STOP
                # candle or a relabelled old candidate. Its frozen grid (shifted
                # from the verified planner fixture) overlaps the old MIRROR
                # reference corridor but has an independent source identity.
                decision = (stopped.exit_time_ms // FIVE + 1) * FIVE
                verified_now = decision + FIVE + 1000
                snapshot = compatible_retry_box_plan()
                snapshot["identity"]["symbol"] = SYMBOL
                snapshot["decision_time_ms"] = decision
                book.set(SYMBOL, bid=Decimal("106.5"), ask=Decimal("106.6"))
                clock = mock.patch("time.time", lambda: verified_now / 1000)
                clock.start()
                self.addCleanup(clock.stop)
                source_id = runtime.call(lambda owner:
                    owner.store.save_box_plan_only(
                        snapshot=snapshot, created_at_ms=decision + 1,
                    )[0].candidate_id,
                )
                admission = runtime.call(lambda owner: admit_arrived_auto_candidate(
                    owner.store, ACCOUNT, source=SOURCE_BOX_PLAN,
                    candidate_ref=source_id, clock_ms=lambda: verified_now,
                    protection_healthy=lambda: True,
                    candidate_fresh=lambda *_: True,
                    daily_loss_gate_enabled=False,
                ))
                self.assertIsNotNone(admission)
                self.assertEqual(admission.result.outcome, OUTCOME_ALLOW, admission.result)
                second_id = admission.candidate.candidate_id
                self.assertNotEqual(second_id, source_id)
                attempts = runtime.call(lambda owner: owner.store._connection.execute(
                    "SELECT candidate_id,attempt_index FROM robot_reentry_attempts "
                    "ORDER BY attempt_index",
                ).fetchall())
                self.assertEqual([tuple(row) for row in attempts], [
                    (first_id, 1), (second_id, 2),
                ])
                self.assertEqual(candidate(source_id).status, "BOX_PLAN_ONLY")
                self.assertEqual(candidate(second_id).status, "APPROVED")

                # Production Robot monitor must create frozen Box P1..P4
                # ownership; tests never preseed orders or fills.
                def box_p1():
                    return runtime.call(lambda owner: (
                        lambda records: next(
                            (owner.store.get_paper_limit(
                                entry.order_id.value, ACCOUNT,
                            ) for entry in records
                             if entry.role == "ENTRY" and entry.slot == 1),
                            None,
                        )
                    )(owner.store.load_box_order_ownership(source_id)))
                p1 = _wait_until(box_p1)
                self.assertEqual(p1.status, "open")
                self.assertEqual(p1.filled_quantity, Decimal("0"))
                self.assertIsNone(runtime.call(
                    lambda owner: owner.store.get_open_robot_trade_for_symbol(
                        ACCOUNT, symbol,
                    ),
                ))

                # Match just the first Box grid LIMIT through the same
                # ordered production book event as protection triggers.
                fill_bid = p1.price - instrument.tick_size
                book.set(SYMBOL, bid=fill_bid, ask=p1.price)
                fill_book = _event_book(
                    SYMBOL, bid=fill_bid, ask=p1.price,
                )
                runtime.call(lambda owner: owner.process_robot_market_event(
                    SYMBOL, fill_book, event_id="box-retry-p1-fill",
                    received_at_ms=fill_book.received_at_ms,
                ))
                retry_trade = _wait_until(lambda: (
                    lambda trade: trade if trade and trade.candidate_id == second_id else None
                )(runtime.call(lambda owner:
                    owner.store.get_open_robot_trade_for_symbol(ACCOUNT, symbol),
                )))
                self.assertEqual(retry_trade.pattern, "IKIGAI_BOX")
                self.assertNotEqual(retry_trade.trade_id, initial_trade.trade_id)
                self.assertGreater(retry_trade.entry_quantity, 0)
                # Box deliberately arms a STOP projection, but takes profit
                # through Box-owned EXIT LIMITs, not protection.take_profit.
                # The earlier MIRROR strategy uses STOP+TAKE projection;
                # never conflate these independent canonical contracts.
                def box_stop():
                    value = runtime.call(
                        lambda owner: owner.store.get_protection_projection(key),
                    )
                    return value if value and value.stop_loss is not None else None

                second_protection = _wait_until(box_stop)
                from robot_protection import box_stop_for_actual_entry
                expected_stop = box_stop_for_actual_entry(
                    snapshot, average_entry=retry_trade.average_entry,
                )
                self.assertEqual(second_protection.stop_loss, expected_stop)
                self.assertGreaterEqual(
                    second_protection.stop_loss,
                    Decimal(snapshot["plan"]["stop_price"]),
                )
                self.assertEqual(
                    retry_trade.take_price,
                    Decimal(snapshot["plan"]["take_price"]),
                )

                def exit_limits():
                    return runtime.call(lambda owner: [
                        owner.store.get_paper_limit(item.order_id.value, ACCOUNT)
                        for item in owner.store.load_box_order_ownership(source_id)
                        if item.role == "EXIT"
                    ])
                take_limits = _wait_until(exit_limits)
                self.assertTrue(any(
                    item is not None and item.status == "open"
                    and item.price == Decimal(snapshot["plan"]["take_price"])
                    for item in take_limits
                ))
                journal = ReentryDiaryReader(self.db).load()
                self.assertEqual(len(journal), 1)
                self.assertEqual(
                    [attempt.status for attempt in journal[0].attempts],
                    ["CLOSED", "OPEN"],
                )
                self.assertEqual(
                    journal[0].attempts[1].candidate_id, second_id,
                )
            finally:
                runtime.close()
