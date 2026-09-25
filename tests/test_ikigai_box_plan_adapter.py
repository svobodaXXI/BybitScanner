"""One focused adapter integration check; no runtime or network."""

import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from terminal.application.ikigai_box_plan_persistence import persist_ikigai_box_plan
from terminal.application.ikigai_box_first_grid import build_box_first_grid_specs
from terminal.domain.models import OrderSide, TradingAccountId
from terminal.paper.ikigai_box_plan import plan_approved_first_ikigai_box
from terminal.persistence.sqlite_store import DuplicateIdentity, SQLiteStore


class IkigaiBoxPlanAdapterTests(unittest.TestCase):
    def test_frozen_plan_builds_four_stable_non_executing_entry_specs(self):
        inputs = dict(working_quantity=D("8"), tick_size=D("0.01"),
                      entry_fee_rate=D("0"), target_fee_rate=D("0"),
                      stop_fee_rate=D("0"), structural_stop=None)
        plan = plan_approved_first_ikigai_box(direction="LONG", frozen_f1=D("100"),
                                             frozen_f1618=D("92"), **inputs)
        args = dict(planner_version="099cfedc", decision_time_ms=3000,
                    identity=dict(venue="bybit", market="linear", symbol="BTCUSDT",
                                  timeframe="5", direction="LONG", a_time_ms=1000, b_time_ms=2000),
                    anchor_a_price=D("112.94498381877023"), anchor_b_price=D("100"),
                    frozen_f2618=D("79.05501618122977"), **inputs)
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore.open(Path(directory) / "adapter.sqlite3")
            try:
                candidate, _ = persist_ikigai_box_plan(store, plan, created_at_ms=3001, **args)
                first = build_box_first_grid_specs(candidate, created_at_ms=4000)
                second = build_box_first_grid_specs(candidate, created_at_ms=4000)
                self.assertEqual(first, second)
                self.assertEqual(tuple(item.slot for item in first), (1, 2, 3, 4))
                self.assertEqual(tuple(item.price for item in first), plan.limit_prices)
                self.assertEqual(tuple(item.quantity for item in first), plan.limit_quantities)
                self.assertTrue(all(item.side is OrderSide.BUY for item in first))
                self.assertEqual(len({item.order_id for item in first}), 4)
                self.assertEqual(len({item.client_action_id for item in first}), 4)
                self.assertFalse(candidate.signal_snapshot["execution_authorized"])
            finally:
                store.close()

    def test_persist_calculated_plan_duplicate_and_conflict(self):
        inputs = dict(working_quantity=D("8"), tick_size=D("0.01"),
                      entry_fee_rate=D("0"), target_fee_rate=D("0"),
                      stop_fee_rate=D("0"), structural_stop=None)
        # Calculate once explicitly in the caller, never in the adapter.
        plan = plan_approved_first_ikigai_box(direction="LONG", frozen_f1=D("100"),
                                            frozen_f1618=D("92"), **inputs)
        args = dict(planner_version="099cfedc", decision_time_ms=3000,
                    identity=dict(venue="bybit", market="linear", symbol="BTCUSDT",
                                  timeframe="5", direction="LONG", a_time_ms=1000, b_time_ms=2000),
                    anchor_a_price=D("112.94498381877023"), anchor_b_price=D("100"),
                    frozen_f2618=D("79.05501618122977"), **inputs)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "adapter.sqlite3"
            store = SQLiteStore.open(path)
            try:
                record, created = persist_ikigai_box_plan(store, plan, created_at_ms=3001, **args)
                self.assertTrue(created)
                self.assertEqual(record.status, "BOX_PLAN_ONLY")
                self.assertIsNone(record.approved_at_ms)
                self.assertIsNone(record.robot_state)
                self.assertFalse(record.signal_snapshot["execution_authorized"])
                self.assertEqual(tuple(map(D, record.signal_snapshot["plan"]["limit_prices"])),
                                 plan.limit_prices)
                self.assertEqual(record.signal_snapshot["fibonacci"]["f2618"],
                                 "79.05501618122977")
                self.assertEqual(D(record.signal_snapshot["plan"]["slices"][0]["reward_risk"]),
                                 plan.slices[0].reward_risk)
                # Detached data and durable reopening must not change identity or content.
                record.signal_snapshot["plan"]["take_price"] = "1"
            finally:
                store.close()
            store = SQLiteStore.open(path)
            try:
                repeated, created = persist_ikigai_box_plan(store, plan, created_at_ms=4000, **args)
                self.assertFalse(created)
                self.assertEqual(repeated.candidate_id, record.candidate_id)
                self.assertEqual(repeated.snapshot_sha256, record.snapshot_sha256)
                self.assertEqual(repeated.updated_at_ms, 3001)
                self.assertEqual(D(repeated.signal_snapshot["plan"]["take_price"]), plan.take_price)
                with self.assertRaises(DuplicateIdentity):
                    persist_ikigai_box_plan(store, plan, created_at_ms=4001,
                                           **(args | {"planner_version": "different"}))
                self.assertEqual(len(store.load_robot_candidates(TradingAccountId("paper"))), 1)
                self.assertEqual(store.load_active_robot_candidate_states(TradingAccountId("paper")), ())
                self.assertFalse(plan.execution_authorized)
            finally:
                store.close()
