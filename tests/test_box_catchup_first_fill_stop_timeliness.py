"""#447 RED: a mixed Box catch-up must protect its first LIMIT fill on the same event.

ARIAUSDT PAPER run2 (2026-10-09, laptop DB snapshot): catch-up plan MARKET slots
1,2 + LIMIT slots 3,4; LIMITs created 22:46:40; LIMIT P3 filled 22:47:29.689 on
the ordered Robot event path; the slot-1 MARKET was only admitted at 22:48:02
(monitor tick) and stayed `submitting` until 22:50:12; the first STOP was
created at 22:50:13.617, after that MARKET completed (~164 s unprotected).

Contract (PaperRuntime.process_robot_market_event): an authoritative fill is
finalized and protected on the same event, without a periodic monitor tick.
Here the fill-only path re-enters _advance_box_entry_ready, which first needs to
submit the still-pending MARKET slot; the event-path monitor has no MARKET
preflight/submit, so it returns before _sync_box_trade arms the STOP.
Temporary SQLite only.
"""
from decimal import Decimal as D
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import robot_protection as rp
from terminal.application.ikigai_box_catchup import (
    build_box_market_ownership_specs,
    build_box_market_plans,
    classify_box_catchup_slots,
    durable_box_market_intent,
)
from terminal.application.ikigai_box_first_grid import build_box_first_grid_specs
from terminal.domain.models import CommandId, Category, PositionKey, PositionSide, Price, Quantity, Symbol
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_box_first_fill_frozen_stop import ACCOUNT, HIMS_PRICES, _hims_instrument
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument, _set_admission


def _book(ask, quantity, *, sequence):
    now = int(time.time() * 1000)
    return NormalizedOrderBook(
        symbol=Symbol("HIMSUSDT"),
        bids=(PriceLevel(Price(D(ask) - D("0.01")), Quantity(D("5"))),),
        asks=(PriceLevel(Price(D(ask)), Quantity(D(quantity))),),
        health=BookHealth.READY, received_at_ms=now, available_depth=1,
        source_generation=0, source_sequence=sequence, source_update_id=sequence,
        source_event_at_ms=now, source_matching_engine_cts_ms=None,
    )


class MixedCatchupFirstLimitFillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = PaperRuntime(
            Path(self.tmp.name) / "paper.sqlite3", book_provider=StaticBookProvider(),
            instrument_snapshot=_instrument(), instrument_provider=_hims_instrument,
        )
        self.addCleanup(self.runtime.close)
        _set_admission(self.runtime, mode="ROBOT_RUNNING", recovery_status="READY")
        store = self.runtime.store
        source_id = self.runtime._prepare_ikigai_box_robot_plan("HIMSUSDT", "5", {
            "direction": "LONG", "a_time_ms": 1000, "b_time_ms": 2000, "decision_time_ms": 3000,
            "anchor_a_price": "29.30", "anchor_b_price": "28.70",
            "f1": "28.70", "f1618": "28.10", "f2618": "27.13",
        })
        source = store.get_robot_candidate(source_id)
        self.assertEqual(source.signal_snapshot["plan"]["limit_prices"], HIMS_PRICES)
        self.candidate, _ = store.handoff_box_plan_to_robot(
            source_id, symbol=source.symbol,
            expected_snapshot_sha256=source.snapshot_sha256,
            approved_at_ms=source.updated_at_ms + 1,
        )

        # Late admission: ask 28.22 has crossed P1 28.25 only -> MARKET slot 1, LIMIT 2..4.
        plan_book = _book("28.22", "50", sequence=1)
        slots = classify_box_catchup_slots(source, plan_book)
        self.assertEqual([s.slot for s in slots if s.entry_mode == "MARKET"], [1])
        market_plans = build_box_market_plans(source, plan_book, slots=(1,))
        limit_specs = tuple(
            spec for spec in build_box_first_grid_specs(source, created_at_ms=int(time.time() * 1000))
            if spec.slot in {2, 3, 4}
        )
        self.assertTrue(store.begin_box_attempt_ownership(source_id))
        store.create_box_mixed_entry_ownership(
            source_id, trading_account_id=ACCOUNT, symbol=source.symbol,
            market_orders=build_box_market_ownership_specs(market_plans),
            limit_orders=limit_specs,
        )
        # Durable state the monitor writes once it owns the mixed plan, before the
        # MARKET slot has been submitted (ARIAUSDT 22:46:40 -> 22:48:02).
        limit_ids = [spec.order_id.value for spec in limit_specs]
        state = dict(self.candidate.robot_state)
        state["execution"] = {
            "entry_mode": "BOX_CATCHUP", "source_box_candidate_id": source_id,
            "box_catchup": {
                "market_slots": [1], "limit_slots": [2, 3, 4],
                "market_intents": [durable_box_market_intent(plan) for plan in market_plans],
                "limit_order_ids": limit_ids, "book_received_at_ms": plan_book.received_at_ms,
            },
            "limit_order_ids": limit_ids,
            "market_order_ids": [plan.order_id.value for plan in market_plans],
            "box_ownership_ready": True,
        }
        self.candidate = store.save_robot_candidate_state(
            self.candidate.candidate_id, status="APPROVED", robot_state=state,
            expected_revision=self.candidate.state_revision,
            updated_at_ms=source.updated_at_ms + 2,
        )
        time.sleep(0.01)  # the fill must be later than the candidate's last write

    def test_first_limit_fill_is_stop_protected_on_the_same_event_while_market_slot_pending(self):
        store = self.runtime.store
        fill_book = _book("28.19", "1.17", sequence=2)  # partial P2 LIMIT fill only
        self.runtime.process_robot_market_event(
            "HIMSUSDT", fill_book, event_id="HIMSUSDT:2", received_at_ms=fill_book.received_at_ms,
        )

        key = PositionKey(ACCOUNT, Category.LINEAR, Symbol("HIMSUSDT"), 0)
        position = store.get_position_projection(key)
        # Precondition: real exposure exists from the resting LIMIT.
        self.assertEqual((position.side, position.quantity.value), (PositionSide.LONG, D("1.17")))
        # Contract: that exposure owns a STOP after the same ordered event.
        protection = store.get_protection_projection(key)
        self.assertIsNotNone(
            protection.stop_loss if protection is not None else None,
            "filled Box exposure has no STOP after its fill event (#447)",
        )

    def test_unconfirmed_stop_never_sends_the_pending_market_slot(self):
        store = self.runtime.store
        monitor = self.runtime._robot_breakout_monitor
        sent = MagicMock(name="submit_market")
        monitor._submit_market = sent
        monitor._market_preflight = MagicMock(
            return_value=MagicMock(admitted=True, normalized_quantity=D("2.21")))

        def refuse(*_a, **_k):
            raise rp.RobotProtectionError("simulated initial STOP refusal")

        fill_book = _book("28.19", "1.17", sequence=2)
        with patch.object(rp, "build_box_stop_only_plan", refuse):
            self.runtime.process_robot_market_event(
                "HIMSUSDT", fill_book, event_id="HIMSUSDT:2", received_at_ms=fill_book.received_at_ms,
            )
            monitor.tick()

        pending = self.candidate.robot_state["execution"]["box_catchup"]["market_intents"][0]
        entry_sends = [
            call for call in sent.call_args_list
            if call.args and call.args[1].command_id.value == pending["command_id"]
        ]
        self.assertEqual(entry_sends, [], "pending MARKET entry was sent without a confirmed STOP")
        self.assertIsNone(store.get_command(
            CommandId(pending["command_id"])))


if __name__ == "__main__":
    unittest.main()
