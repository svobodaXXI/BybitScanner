"""MIRROR-LINK-1: real PAPER_AUTO Box admission into an owned Wedge campaign."""

from decimal import Decimal
import copy
import unittest
from unittest.mock import patch

import mirror_retest_robot as mirror
from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW,
    OUTCOME_WAIT,
    REASON_ELIGIBLE,
    REASON_SYMBOL_OWNED,
)
from terminal.application.robot_autopilot_shadow import (
    PAPER_AUTO_MODE,
    SOURCE_BOX_PLAN,
    admit_arrived_auto_candidate,
)
from terminal.application.robot_portfolio import collect_portfolio_facts
from terminal.domain.models import OrderId, OrderSide, Symbol
from tests import test_mirror_robot_box_cycle as cycle


class MirrorLinkedAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.h = cycle.MirrorBoxCycleTests(
            "test_full_mirror_cycle_partial_take_break_even_retest_close_and_net_pnl"
        )
        self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        self.h.store.initialize_paper_account(
            cycle.ACCOUNT_ID, Decimal("5000"), updated_at_ms=1
        )
        state = self.h.store.initialize_robot_autopilot_state(
            cycle.ACCOUNT_ID, updated_at_ms=1
        )
        self.h.store.update_robot_autopilot_state(
            cycle.ACCOUNT_ID,
            mode=PAPER_AUTO_MODE,
            expected_version=state.version,
            updated_at_ms=2,
        )
        gate = patch(
            "terminal.application.robot_autopilot_shadow._daily_loss_gate",
            lambda *args, **kwargs: {
                "enabled": True,
                "latched": False,
                "data_available": True,
                "business_date_msk": "fixture",
                "transition": None,
            },
        )
        gate.start()
        self.addCleanup(gate.stop)

    def add_active_wedge(
        self, candidate_id="wedge-owner", direction="LONG", pattern="Falling Wedge"
    ):
        snapshot = cycle.wedge_snapshot()
        snapshot["pattern"] = pattern
        snapshot["scanner_formation_id"] = candidate_id
        candidate, _ = self.h.store.create_robot_candidate(
            candidate_id=candidate_id,
            trading_account_id=cycle.ACCOUNT_ID,
            symbol=Symbol(cycle.SYMBOL),
            status="APPROVED",
            signal_snapshot=snapshot,
            approved_at_ms=cycle.WEDGE_AS_OF,
            updated_at_ms=cycle.WEDGE_AS_OF,
        )
        return self.h.store.save_robot_candidate_state(
            candidate.candidate_id,
            status="APPROVED",
            robot_state={"phase": "CAMPAIGN_ACTIVE", "direction": direction},
            expected_revision=candidate.state_revision,
            updated_at_ms=cycle.WEDGE_AS_OF + 1,
        )

    def save_box(self, *, direction="LONG"):
        snapshot = copy.deepcopy(cycle.box_snapshot())
        snapshot["identity"]["symbol"] = cycle.SYMBOL
        snapshot["identity"]["direction"] = direction
        snapshot["plan"]["direction"] = direction
        return self.h.store.save_box_plan_only(snapshot=snapshot, created_at_ms=3001)[0]

    def admit(self, source):
        return admit_arrived_auto_candidate(
            self.h.store,
            cycle.ACCOUNT_ID,
            source=SOURCE_BOX_PLAN,
            candidate_ref=source.candidate_id,
            protection_healthy=lambda: True,
            candidate_fresh=lambda *_: True,
            clock_ms=lambda: cycle.NOW,
        )

    def assert_wait_without_orders(self, admission, source):
        self.assertEqual(
            (admission.result.outcome, admission.result.reason_code),
            (OUTCOME_WAIT, REASON_SYMBOL_OWNED),
        )
        self.assertIsNone(admission.candidate)
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())

    def test_same_direction_owned_wedge_reaches_attached_through_paper_auto(self):
        parent = self.add_active_wedge()
        source = self.save_box()

        admission = self.admit(source)

        self.assertEqual(
            (admission.result.outcome, admission.result.reason_code),
            (OUTCOME_ALLOW, REASON_ELIGIBLE),
        )
        self.assertIsNotNone(admission.candidate)
        self.assertEqual(
            admission.candidate.robot_state["mirror_parent_candidate_id"],
            parent.candidate_id,
        )
        monitor = self.h.monitor()
        self.assertEqual(monitor.tick(), (admission.candidate.candidate_id,))
        attached = self.h.store.get_robot_candidate(
            admission.candidate.candidate_id
        ).robot_state["execution"]["mirror"]
        self.assertEqual(attached["decision"], mirror.ATTACHED)
        self.assertEqual(attached["parent_candidate_id"], parent.candidate_id)
        portfolio = collect_portfolio_facts(self.h.store, cycle.ACCOUNT_ID)
        self.assertEqual(portfolio["occupied_ro"], 1)
        self.assertEqual(
            [item["identity"] for item in portfolio["reservations"]],
            [f"robot:{parent.candidate_id}"],
        )

    def test_opposite_direction_stays_symbol_owned_without_orders(self):
        self.add_active_wedge(direction="LONG")
        source = self.save_box(direction="SHORT")
        self.assert_wait_without_orders(self.admit(source), source)

    def test_multiple_owners_stay_symbol_owned_without_orders(self):
        self.add_active_wedge("wedge-owner-1")
        self.add_active_wedge("wedge-owner-2")
        source = self.save_box()
        self.assert_wait_without_orders(self.admit(source), source)

    def test_non_wedge_owner_stays_symbol_owned_without_orders(self):
        self.add_active_wedge("l-shape-owner", pattern="L-shape")
        source = self.save_box()
        self.assert_wait_without_orders(self.admit(source), source)

    def test_parent_working_entry_stays_symbol_owned_without_box_orders(self):
        parent = self.add_active_wedge()
        parent = self.h.store.save_robot_candidate_state(
            parent.candidate_id,
            status="APPROVED",
            robot_state={**parent.robot_state, "execution": {"limit_order_id": "wedge-entry"}},
            expected_revision=parent.state_revision,
            updated_at_ms=cycle.WEDGE_AS_OF + 2,
        )
        self.h.store.create_paper_limit(
            client_action_id="wedge-entry-create",
            request_fingerprint="wedge-entry-fingerprint",
            order_id=OrderId("wedge-entry"),
            order_link_id="wedge-entry-link",
            trading_account_id=cycle.ACCOUNT_ID,
            symbol=Symbol(cycle.SYMBOL),
            side=OrderSide.BUY,
            price=Decimal("95"),
            quantity=Decimal("1"),
            created_at_ms=cycle.WEDGE_AS_OF + 2,
        )
        source = self.save_box()
        self.assert_wait_without_orders(self.admit(source), source)

    def test_manual_position_stays_symbol_owned_without_orders(self):
        self.add_active_wedge()
        self.h.store._connection.execute(
            "INSERT INTO position_projections VALUES "
            "('paper','linear',?,0,'Long','100','2.5','0','0','250','synced',1,1)",
            (cycle.SYMBOL,),
        )
        source = self.save_box()
        self.assert_wait_without_orders(self.admit(source), source)

    def test_deferred_mirror_never_falls_back_to_plain_box(self):
        self.add_active_wedge()
        source = self.save_box()
        admission = self.admit(source)
        self.h.risk_limit = None

        monitor = self.h.monitor()
        self.assertEqual(monitor.tick(), ())
        candidate = self.h.store.get_robot_candidate(admission.candidate.candidate_id)
        self.assertEqual(candidate.status, "APPROVED")
        self.assertNotIn("mirror", candidate.robot_state.get("execution") or {})
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())
        self.assertEqual(self.h.market_submissions, [])

    def test_blocked_mirror_never_falls_back_to_plain_box(self):
        self.add_active_wedge()
        source = self.save_box()
        admission = self.admit(source)
        self.h.risk_limit = Decimal("20")

        self.h.monitor().tick()
        candidate = self.h.store.get_robot_candidate(admission.candidate.candidate_id)
        self.assertEqual(candidate.status, "INVALIDATED")
        self.assertEqual(candidate.robot_state["execution"]["mirror"]["decision"], mirror.BLOCKED)
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())
        self.assertEqual(self.h.market_submissions, [])

    def test_not_attached_link_never_falls_back_to_plain_box(self):
        self.add_active_wedge()
        source = self.save_box()
        admission = self.admit(source)
        self.h.candles.coarse = []

        self.h.monitor().tick()
        candidate = self.h.store.get_robot_candidate(admission.candidate.candidate_id)
        self.assertEqual(candidate.status, "INVALIDATED")
        self.assertEqual(
            candidate.robot_state["execution"]["mirror"]["decision"], mirror.NOT_ATTACHED
        )
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())
        self.assertEqual(self.h.market_submissions, [])

    def test_parent_disappearance_cancels_entries_before_any_fill(self):
        parent = self.add_active_wedge()
        source = self.save_box()
        admission = self.admit(source)
        monitor = self.h.monitor()
        for _ in range(3):
            self.assertEqual(monitor.tick(), (admission.candidate.candidate_id,))
        ownership = self.h.store.load_box_order_ownership(source.candidate_id)
        self.assertTrue(ownership)
        self.assertEqual(self.h.market_submissions, [])
        self.h.store.save_robot_candidate_state(
            parent.candidate_id,
            status="INVALIDATED",
            robot_state={**parent.robot_state, "phase": "INVALIDATED"},
            expected_revision=parent.state_revision,
            updated_at_ms=cycle.NOW,
        )

        self.assertEqual(monitor.tick(), (admission.candidate.candidate_id,))
        candidate = self.h.store.get_robot_candidate(admission.candidate.candidate_id)
        self.assertEqual(candidate.status, "INVALIDATED")
        for item in ownership:
            order = self.h.store.get_paper_limit(item.order_id.value, cycle.ACCOUNT_ID)
            if order is not None:
                self.assertEqual(order.status, "cancelled")
        self.assertEqual(self.h.market_submissions, [])

    def test_restart_reuses_one_attachment_and_one_link(self):
        parent = self.add_active_wedge()
        source = self.save_box()
        first = self.admit(source)
        monitor = self.h.monitor()
        self.assertEqual(monitor.tick(), (first.candidate.candidate_id,))
        attached = self.h.store.get_robot_candidate(first.candidate.candidate_id)
        decided_at = attached.robot_state["execution"]["mirror"]["decided_at_ms"]
        monitor.close()

        repeated = self.admit(source)
        self.assertFalse(repeated.candidate_created)
        self.assertEqual(repeated.candidate.candidate_id, first.candidate.candidate_id)
        restarted = self.h.monitor()
        self.assertEqual(restarted.tick(), (first.candidate.candidate_id,))
        after = self.h.store.get_robot_candidate(first.candidate.candidate_id)
        self.assertEqual(after.robot_state["execution"]["mirror"]["decided_at_ms"], decided_at)
        self.assertEqual(after.robot_state["mirror_parent_candidate_id"], parent.candidate_id)
        self.assertEqual(self.h.store.load_box_order_ownership(source.candidate_id), ())


if __name__ == "__main__":
    unittest.main()
