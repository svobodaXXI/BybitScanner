"""PAPER option B: a partial first Box fill keeps the frozen STOP (owner, 2026-10-08).

HIMSUSDT 08.10.2026: P1 filled 1.17 @ 28.25 of a 4 x 2.21 grid (P1..P4 28.25 /
28.19 / 28.13 / 28.07, TAKE 28.64, frozen STOP 27.98, fees 0.0006). No STOP
beyond P4 reaches net 2:1 for that entry, so protection raised and the Robot
emergency-closed. The full planned grid still requires net RR >= 2; the actual
partial-fill RR may be lower and is recorded. Temporary SQLite only.
"""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import tempfile
import time
import unittest

import robot_protection as rp
from terminal.application.ikigai_box_first_grid import build_box_first_grid_specs
from terminal.domain.models import (
    Category, PositionKey, PositionSide, Price, Quantity, Symbol, TradingAccountId,
)
from terminal.market_data.models import BookHealth, NormalizedOrderBook, PriceLevel
from terminal.paper.ikigai_box_plan import plan_ikigai_box
from terminal.runtime.paper_runtime import PaperRuntime
from tests.test_terminal_paper_runtime import StaticBookProvider, _instrument, _set_admission

ACCOUNT = TradingAccountId("paper")
HIMS_PRICES = ["28.25", "28.19", "28.13", "28.07"]
FEES = {"entry_fee_rate": "0.0006", "target_fee_rate": "0.0006", "stop_fee_rate": "0.0006"}


def hims_snapshot(*, direction="LONG", prices=None, take="28.64", stop="27.98", tick="0.01"):
    return {
        "pattern": "IKIGAI_BOX", "environment": "PAPER", "execution_authorized": False,
        "attempt": 1, "identity": {"symbol": "HIMSUSDT"},
        "plan": {
            "direction": direction, "limit_prices": prices or HIMS_PRICES,
            "limit_quantities": ["2.21"] * 4, "take_price": take, "stop_price": stop,
        },
        "inputs": {"tick_size": tick, **FEES},
    }


def stop_plan(snapshot, *, entry, quantity="1.17", existing_stop=None, direction="LONG"):
    return rp.build_box_stop_only_plan(
        {"candidate_id": "box-robot-hims", "status": "APPROVED", "signal_snapshot": snapshot},
        {"direction": direction},
        average_entry=D(entry), confirmed_position_quantity=D(quantity),
        existing_stop=D(existing_stop) if existing_stop else None,
    )


def net_rr(entry, stop, take="28.64", fee=D("0.0006")):
    entry, stop, take = D(entry), D(stop), D(take)
    return (take - entry - entry * fee - take * fee) / (entry - stop + entry * fee + stop * fee)


class BoxFirstFillStopTests(unittest.TestCase):
    def test_hims_partial_p1_fill_gets_the_frozen_stop_instead_of_failing(self):
        plan = stop_plan(hims_snapshot(), entry="28.25")
        self.assertEqual((plan.stop_price, plan.take_price), (D("27.98"), D("28.64")))
        self.assertEqual(plan.stop_request.trigger_price, D("27.98"))
        self.assertEqual(plan.stop_basis, "FROZEN_FIRST_FILL")
        self.assertEqual(plan.actual_fill_net_rr, net_rr("28.25", "27.98"))
        self.assertLess(plan.actual_fill_net_rr, 2)

    def test_the_strict_actual_fill_function_still_reports_the_shortfall(self):
        with self.assertRaises(rp.BoxActualFillRRUnsatisfied):
            rp.box_stop_for_actual_entry(hims_snapshot(), average_entry=D("28.25"))
        self.assertTrue(issubclass(rp.BoxActualFillRRUnsatisfied, rp.RobotProtectionError))

    def test_admissible_states_keep_the_existing_tightening(self):
        three = stop_plan(hims_snapshot(), entry="28.19", quantity="6.63")
        self.assertEqual((three.stop_price, three.stop_basis), (D("28.02"), "ACTUAL_FILL_RR"))
        self.assertGreaterEqual(three.actual_fill_net_rr, 2)
        full = stop_plan(hims_snapshot(), entry="28.16", quantity="8.84")
        self.assertEqual((full.stop_price, full.stop_basis), (D("27.98"), "ACTUAL_FILL_RR"))
        self.assertGreaterEqual(full.actual_fill_net_rr, 2)

    def test_an_already_active_stop_is_never_widened_back_to_the_frozen_stop(self):
        plan = stop_plan(hims_snapshot(), entry="28.25", existing_stop="28.02")
        self.assertEqual((plan.stop_price, plan.stop_basis), (D("28.02"), "FROZEN_FIRST_FILL"))

    def test_full_grid_below_net_two_to_one_still_fails_closed(self):
        # TAKE 28.40 leaves the planned full grid below net 2:1.
        weak = hims_snapshot(take="28.40")
        with self.assertRaises(rp.RobotProtectionError):
            rp.box_stop_for_actual_entry(weak, average_entry=D("28.16"))
        with self.assertRaisesRegex(rp.RobotProtectionError, "full grid"):
            stop_plan(weak, entry="28.25")

    def test_frozen_stop_must_be_tick_aligned_strictly_beyond_p4(self):
        for stop in ("27.985", "28.07"):
            with self.subTest(stop=stop), self.assertRaises(rp.RobotProtectionError):
                stop_plan(hims_snapshot(stop=stop), entry="28.25")

    def test_short_mirror(self):
        prices = ["28.25", "28.31", "28.37", "28.43"]
        short = hims_snapshot(direction="SHORT", prices=prices, take="27.86", stop="28.52")
        with self.assertRaises(rp.BoxActualFillRRUnsatisfied):
            rp.box_stop_for_actual_entry(short, average_entry=D("28.25"))
        plan = stop_plan(short, entry="28.25", direction="SHORT")
        self.assertEqual((plan.stop_price, plan.stop_basis), (D("28.52"), "FROZEN_FIRST_FILL"))
        self.assertLess(plan.actual_fill_net_rr, 2)

    def test_planner_still_rejects_a_grid_below_net_two_to_one(self):
        # ACTUSDT 08.10.2026: the full planned grid itself misses net RR >= 2.
        with self.assertRaisesRegex(ValueError, "net RR >= 2"):
            plan_ikigai_box(
                direction="LONG",
                limit_prices=tuple(D(p) for p in ("0.010297", "0.010290", "0.010283", "0.010276")),
                limit_quantities=(D("6075"),) * 4, working_quantity=D("24300"),
                frozen_f1=D("0.010348"), frozen_f1618=D("0.01028002"), tick_size=D("0.000001"),
                entry_fee_rate=D("0.0006"), target_fee_rate=D("0.0006"), stop_fee_rate=D("0.0006"),
                structural_stop=None, take_price=D("0.010341"),
            )


def _hims_instrument(symbol):
    return replace(
        _instrument(), symbol=symbol, min_price=D("0.01"), tick_size=D("0.01"),
        min_order_quantity=D("0.01"), quantity_step=D("0.01"), min_notional_value=D("5"),
    )


def _p1_book(*, quantity="1.17"):
    now = int(time.time() * 1000)
    return NormalizedOrderBook(
        symbol=Symbol("HIMSUSDT"),
        bids=(PriceLevel(Price(D("28.24")), Quantity(D("5"))),),
        asks=(PriceLevel(Price(D("28.25")), Quantity(D(quantity))),),
        health=BookHealth.READY, received_at_ms=now, available_depth=1,
        source_generation=0, source_sequence=1, source_update_id=1,
        source_event_at_ms=now, source_matching_engine_cts_ms=None,
    )


class HimsOwnerThreadFillTests(unittest.TestCase):
    """The live failure path: owner-thread fill finalization on a partial P1 fill."""

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
        # f1 28.70 / f1.618 28.10 yields exactly the HIMS grid, TAKE and STOP.
        source_id = self.runtime._prepare_ikigai_box_robot_plan("HIMSUSDT", "5", {
            "direction": "LONG", "a_time_ms": 1000, "b_time_ms": 2000, "decision_time_ms": 3000,
            "anchor_a_price": "29.30", "anchor_b_price": "28.70",
            "f1": "28.70", "f1618": "28.10", "f2618": "27.13",
        })
        self.source = store.get_robot_candidate(source_id)
        plan = self.source.signal_snapshot["plan"]
        self.assertEqual(
            (plan["limit_prices"], plan["limit_quantities"], plan["take_price"], plan["stop_price"]),
            (HIMS_PRICES, ["2.21"] * 4, "28.64", "27.98"),
        )
        self.candidate, _ = store.handoff_box_plan_to_robot(
            source_id, symbol=self.source.symbol,
            expected_snapshot_sha256=self.source.snapshot_sha256,
            approved_at_ms=self.source.updated_at_ms + 1,
        )
        self.assertTrue(store.begin_box_attempt_ownership(source_id))
        specs = build_box_first_grid_specs(self.source, created_at_ms=int(time.time() * 1000))
        store.create_box_mixed_entry_ownership(
            source_id, trading_account_id=ACCOUNT, symbol=self.source.symbol, market_orders=(),
            limit_orders=specs,
        )
        # The durable state the monitor writes once it owns a pure-LIMIT grid (HIMS live shape).
        order_ids = [spec.order_id.value for spec in specs]
        state = dict(self.candidate.robot_state)
        state["execution"] = {
            "entry_mode": "BOX_CATCHUP", "source_box_candidate_id": source_id,
            "box_catchup": {"market_slots": [], "limit_slots": [1, 2, 3, 4], "market_intents": [],
                            "limit_order_ids": order_ids, "book_received_at_ms": 1},
            "limit_order_ids": order_ids, "market_order_ids": [], "box_ownership_ready": True,
        }
        self.candidate = store.save_robot_candidate_state(
            self.candidate.candidate_id, status="APPROVED", robot_state=state,
            expected_revision=self.candidate.state_revision, updated_at_ms=self.source.updated_at_ms + 2,
        )
        time.sleep(0.01)  # the fill must be later than the candidate's last write

    def test_partial_p1_fill_is_protected_with_the_frozen_stop_and_recorded(self):
        store = self.runtime.store
        book = _p1_book()
        self.runtime.process_robot_market_event(
            "HIMSUSDT", book, event_id="HIMSUSDT:1", received_at_ms=book.received_at_ms,
        )

        state = store.get_robot_runtime_state(ACCOUNT)
        self.assertEqual((state.mode, state.recovery_status), ("ROBOT_RUNNING", "READY"))
        key = PositionKey(ACCOUNT, Category.LINEAR, Symbol("HIMSUSDT"), 0)
        position = store.get_position_projection(key)
        self.assertEqual((position.side, position.quantity.value), (PositionSide.LONG, D("1.17")))
        self.assertEqual(store.get_protection_projection(key).stop_loss, D("27.98"))
        trade = store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))
        self.assertIsNotNone(trade)
        self.assertEqual((trade.stop_price, trade.take_price, trade.average_entry, trade.entry_quantity),
                         (D("27.98"), D("28.64"), D("28.25"), D("1.17")))
        self.assertFalse(any(
            fill.side.value == "Sell"
            for fill in store.load_executions_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))
        ))
        record = store.get_robot_candidate(self.candidate.candidate_id)
        self.assertEqual(record.status, "OPEN")
        first = record.robot_state["execution"]["box_first_fill_protection"]
        self.assertEqual(first["stop_basis"], "FROZEN_FIRST_FILL")
        self.assertEqual((first["stop_price"], first["average_entry"], first["entry_quantity"]),
                         ("27.98", "28.25", "1.17"))
        self.assertEqual(D(first["actual_fill_net_rr"]), net_rr("28.25", "27.98"))
        self.assertLess(D(first["actual_fill_net_rr"]), 2)
        self.assertNotIn("box_emergency_close_intent", record.robot_state["execution"])

    def test_the_first_fill_record_is_not_overwritten_by_a_later_pass(self):
        store = self.runtime.store
        book = _p1_book()
        self.runtime.process_robot_market_event(
            "HIMSUSDT", book, event_id="HIMSUSDT:1", received_at_ms=book.received_at_ms,
        )
        before = store.get_robot_candidate(self.candidate.candidate_id).robot_state["execution"][
            "box_first_fill_protection"]
        again = _p1_book(quantity="0.5")
        self.runtime.process_robot_market_event(
            "HIMSUSDT", again, event_id="HIMSUSDT:2", received_at_ms=again.received_at_ms,
        )
        record = store.get_robot_candidate(self.candidate.candidate_id)
        self.assertEqual(record.robot_state["execution"]["box_first_fill_protection"], before)
        trade = store.get_open_robot_trade_for_symbol(ACCOUNT, Symbol("HIMSUSDT"))
        self.assertEqual((trade.entry_quantity, trade.stop_price), (D("1.67"), D("27.98")))


if __name__ == "__main__":
    unittest.main()
