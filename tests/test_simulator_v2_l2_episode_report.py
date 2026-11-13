"""Pure L2 episode provenance: evidence flags and exact fee-net USDT."""
from decimal import Decimal as D
import unittest

from research.simulator_v2.l2_episode_report import episode_rows
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
