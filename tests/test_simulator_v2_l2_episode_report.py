"""Pure L2 episode provenance: evidence flags and exact fee-net USDT."""
from decimal import Decimal as D
import unittest

from research.simulator_v2.l2_episode_report import episode_rows
from robot_entry_flow_evidence import ImpulseProtectedPlan, ImpulseSignal
from research.simulator_v2.virtual_account import VirtualFill
from research.simulator_v2.virtual_exchange import OrderEvent


def fill(oid, at, side, price, fee, quantity="10"):
    return VirtualFill(
        "test_l2_report", "ICNTUSDT", oid, at, side,
        D(quantity), D(price), D(fee),
    )


def event(oid, kind, at):
    return OrderEvent(oid, kind, at, order_type="STOP" if "STOP" in kind else "LIMIT")


class L2EpisodeReportTests(unittest.TestCase):
    def test_two_closed_virtual_episodes_exact_fee_net_and_flags(self):
        fills = (
            fill("one_fill", 100, "BUY", "100", "0.6"),
            fill("one_stop_fill", 140, "SELL", "98", "0.588"),
            fill("two_fill", 200, "SELL", "100", "0.2"),
            fill("two_take_fill", 240, "BUY", "95", "0.19"),
        )
        events = (
            event("one", "DEPTH_UNPROVEN", 90),
            event("one", "STOP_TRIGGER_DEFERRED", 130),
            event("one", "STOP_FILLED", 140),
            event("two", "TAKE_FILLED", 240),
        )
        rows = episode_rows(fills, events)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["net_pnl_usdt"], "-21.188")
        self.assertEqual(rows[1]["net_pnl_usdt"], "49.61")
        self.assertEqual(rows[0]["deferred_stop_ms"], 10)
        self.assertEqual(rows[0]["evidence_flags"], [
            "ENTRY_DEPTH_UNPROVEN", "STOP_SETTLED_FROM_LATER_BOOK",
        ])
        self.assertEqual(rows[0]["model_certainty"], "CONDITIONAL_MODEL")
        self.assertEqual(rows[1]["model_certainty"], "MODEL_ONLY_NOT_REAL_EXCHANGE_FILL")
        self.assertEqual(
            sum((D(row["net_pnl_usdt"]) for row in rows), D("0")),
            D("28.422"),
        )

    def test_original_plan_explains_stop_level_and_signal_structure(self):
        plan = ImpulseProtectedPlan(
            ImpulseSignal("LONG", 80, D("100"), D("99")),
            D("100"), D("99"), D("103"), D("10"),
            D("2.5"), D("15"),
        )
        rows = episode_rows(
            (
                fill("IMPULSE_80_fill", 100, "BUY", "100", "0.6"),
                fill("IMPULSE_80_stop_fill", 140, "SELL", "98", "0.588"),
            ),
            (event("IMPULSE_80", "STOP_FILLED", 140),),
            {"IMPULSE_80": plan},
        )
        self.assertEqual(rows[0]["signal_ms"], 80)
        self.assertEqual(rows[0]["planned_stop_price"], "99")
        self.assertEqual(rows[0]["planned_take_price"], "103")
        self.assertEqual(rows[0]["signal_structural_extreme"], "99")
        self.assertEqual(rows[0]["exit_reason"], "STOP")
        self.assertEqual(rows[0]["net_pnl_usdt"], "-21.188")

    def test_partial_and_residual_stop_reconcile_exact_fee_net(self):
        rows = episode_rows((
            fill("one_fill", 100, "BUY", "100", "0.6"),
            fill("one_partial_fill", 120, "SELL", "102", "0.306", "2.5"),
            fill("one_stop_fill", 160, "SELL", "100.1", "0.45045", "7.5"),
        ), (
            event("one", "PARTIAL_TAKE_FILLED", 120),
            event("one", "STOP_AMENDED_BE", 130),
            event("one", "STOP_FILLED", 160),
        ))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["partial_quantity"], "2.5")
        self.assertEqual(rows[0]["partial_price"], "102")
        self.assertEqual(rows[0]["gross_pnl_usdt"], "5.75")
        self.assertEqual(rows[0]["net_pnl_usdt"], "4.39355")
        self.assertEqual(rows[0]["evidence_flags"], [
            "BE_STOP_AMENDED_AFTER_PARTIAL", "L2_PARTIAL_TAKE_SIMULATED",
        ])

    def test_partial_requires_event_and_exact_residual(self):
        fills = (
            fill("one_fill", 100, "BUY", "100", "0.6"),
            fill("one_partial_fill", 120, "SELL", "102", "0.306", "2.5"),
            fill("one_take_fill", 160, "SELL", "103", "0.4635", "7.5"),
        )
        with self.assertRaisesRegex(ValueError, "lacks original event"):
            episode_rows(fills, ())
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            episode_rows((
                fills[0], fills[1],
                fill("one_take_fill", 160, "SELL", "103", "0.5", "10"),
            ), (event("one", "PARTIAL_TAKE_FILLED", 120),))
        with self.assertRaisesRegex(ValueError, "BE mutation"):
            episode_rows((
                fills[0], fills[2],
            ), (event("one", "STOP_AMENDED_BE", 130),))

    def test_open_episode_no_invented_exit_or_net_pnl(self):
        rows = episode_rows((fill("one_fill", 100, "BUY", "100", "0.6"),), ())
        self.assertEqual(rows[0]["exit_reason"], "OPEN")
        self.assertIsNone(rows[0]["exit_price"])
        self.assertIsNone(rows[0]["net_pnl_usdt"])
        self.assertEqual(rows[0]["model_certainty"], "CONDITIONAL_MODEL")

    def test_invalid_or_out_of_order_exit_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unpaired"):
            episode_rows((fill("one_stop_fill", 140, "SELL", "98", "0.588"),), ())
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            episode_rows((
                fill("one_fill", 100, "BUY", "100", "0.6"),
                fill("one_stop_fill", 90, "SELL", "98", "0.588"),
            ), ())
        with self.assertRaisesRegex(ValueError, "250ms"):
            episode_rows((
                fill("one_fill", 100, "BUY", "100", "0.6"),
                fill("one_stop_fill", 900, "SELL", "98", "0.588"),
            ), (event("one", "STOP_TRIGGER_DEFERRED", 110),))


if __name__ == "__main__":
    unittest.main()
