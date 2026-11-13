"""Targeted offline 25/50/75 percent partial-TAKE feasibility tests."""
from decimal import Decimal as D
import unittest

from research.simulator_v2.compare_partial_be_icnt import (
    _be_plan, _full_depth, evaluate,
)
from research.simulator_v2.historical_orderbook import BookState
from robot_entry_flow_evidence import TakerPrint


def book(at, bid="100.8", bid_qty="100"):
    return BookState(
        "ICNTUSDT", at, at, at, at,
        ((D(bid), D(bid_qty)), (D("99.9"), D("100"))),
        ((D("103.1"), D("100")),),
    )


def episode(index):
    at = 1000 + index * 1000
    return {
        "entry_ms": at, "exit_ms": at + 500,
        "entry_price": D("100"), "planned_stop_price": D("99"),
        "planned_take_price": D("103"), "entry_fee": D("6"),
        "quantity": D("100"), "direction": "LONG",
        "order_id": f"o{index}", "evidence_flags": [],
    }


class TestPartialBEFeasibility(unittest.TestCase):
    def test_existing_break_even_formula_is_reused(self):
        ep = episode(0)
        snapshot = book(1200)
        policy = _be_plan(ep, D("100.8"), D("25"), snapshot)
        self.assertEqual(policy.decision, "NET_BREAK_EVEN_STOP")
        self.assertGreaterEqual(policy.worst_case_net_pnl_usdt, 0)
        self.assertTrue(ep["planned_stop_price"] < policy.stop_price < snapshot.best_bid[0])

    def test_partial_full_depth_and_fees_not_fabricated(self):
        episodes = [episode(i) for i in range(4)]
        tape = [TakerPrint("ICNTUSDT", f"t{i}", ep["entry_ms"] + 30,
                            "Buy", D("100.9"), D("1"))
                for i, ep in enumerate(episodes)]
        books = [book(ep["entry_ms"] + 35) for ep in episodes]
        outcome = evaluate(episodes, tape, books)
        self.assertEqual([s["full_25pct_partial_depth_candidate_count"]
                          for s in outcome["summary"]], [4, 0, 0])
        self.assertEqual([s["aggressive_tape_through_count"]
                          for s in outcome["summary"]], [4, 0, 0])
        self.assertEqual([s["be_price_placeable_candidate_count"]
                          for s in outcome["summary"]], [4, 0, 0])
        self.assertTrue(all(s["scenario_net_pnl_usdt"] is None for s in outcome["summary"]))
        self.assertTrue(all(not s["partial_fill_confirmed"] for s in outcome["episodes"]))

    def test_insufficient_depth_never_counts_as_partial_fill(self):
        episodes = [episode(i) for i in range(4)]
        shallow = [book(ep["entry_ms"] + 20, bid_qty="5") for ep in episodes]
        outcome = evaluate(episodes, [], shallow)
        self.assertEqual(
            [s["full_25pct_partial_depth_candidate_count"] for s in outcome["summary"]],
            [0, 0, 0],
        )
        self.assertEqual(
            [s["be_price_placeable_candidate_count"] for s in outcome["summary"]],
            [0, 0, 0],
        )
        self.assertFalse(_full_depth(shallow[0], "LONG", D("100.8"), D("25")))


if __name__ == "__main__":
    unittest.main()
