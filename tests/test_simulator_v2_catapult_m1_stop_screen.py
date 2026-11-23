"""The STOP-only M1 study is diagnostic, not a profitable trading-policy test."""
import copy
import unittest
from decimal import Decimal as D

from research.simulator_v2.catapult_m1_stop_screen import (
    FixedM1Probe, M1ScreenBlocked, screen_stop_only_wedge_episodes,
)


def fixture(direction="SHORT"):
    is_long = direction == "LONG"
    entry, close = "100", ("98" if is_long else "102")
    qty = "1"
    pnl = "-2.1212"
    open_side, close_side = ("Buy", "Sell") if is_long else ("Sell", "Buy")
    episode = {
        "facts_status": 200, "wedge_status": 200,
        "facts": {
            "namespace": "PAPER_READ_ONLY", "source": "PAPER_EXECUTIONS_ATTRIBUTED",
            "owner": "ROBOT", "cohort": "ROBOT", "source_revision": 559,
            "trade_episode_id": "te_fixture", "symbol": "TESTUSDT",
            "side": direction, "opened_at_ms": 15000, "closed_at_ms": 210000,
            "pnl_usdt": pnl,
            "execution_allocations": [
                {"allocation_role": "OPEN", "controller": "ROBOT",
                 "order_side": open_side, "execution_price": entry,
                 "allocated_quantity": qty, "allocated_fee": ".06",
                 "occurred_at_ms": 15000},
                {"allocation_role": "CLOSE", "controller": "ROBOT",
                 "order_side": close_side, "execution_price": close,
                 "allocated_quantity": qty,
                 "allocated_fee": ".0588" if is_long else ".0612",
                 "occurred_at_ms": 210000},
            ],
        },
        "wedge": {
            "source_revision": 559, "trade_episode_id": "te_fixture",
            "symbol": "TESTUSDT", "exit_reason": "STOP",
        },
    }
    if is_long:
        # Ensure -2 - .06 - .0588 = -2.1188, not the SHORT fee.
        episode["facts"]["pnl_usdt"] = "-2.1188"
    bars = [
        [0, "100", "100.01", "99.99", "100"],
        [60000, "100", "100.02", "99.97", "100.01"],
        [120000, "100.1", "101", "90", "100.2"],
        [180000, "100.2", "102", "98", "101"],
        [240000, "101", "101", "100", "101"],
    ]
    return (
        {"source_revision": 559, "episodes": [episode]},
        {"source": "BYBIT_V5_PUBLIC_LINEAR_M1",
         "source_revision_reference": 559,
         "items": [{"symbol": "TESTUSDT", "status": "COUNT_MATCH",
                    "expected_count": 5,
                    "candles": [[str(v) for v in bar] for bar in bars]}]},
    )


class CatapultM1StopScreenTests(unittest.TestCase):
    def test_short_early_exit_uses_only_closed_history_and_costs(self):
        f, m1 = fixture()
        r = screen_stop_only_wedge_episodes(
            f, m1, FixedM1Probe(1, D("10"), D("5")),
        )
        self.assertEqual(r["episode_count"], 1)
        self.assertEqual(r["conditional_early_exits"], 1)
        self.assertEqual(D(r["baseline_realized_net_usdt"]), D("-2.1212"))
        self.assertEqual(D(r["conditional_proxy_net_usdt"]), D("-.270140030"))
        self.assertFalse(r["trading_authorized"])
        self.assertFalse(r["source_complete_l2_publictrade"])
        self.assertIn("NOT_EXECUTABLE", r["status"])

    def test_future_low_at_decision_open_cannot_cancel_timeout(self):
        f, m1 = fixture()
        # The minute opening at the hypothetical fill has a future low of 90.
        # It MUST NOT count as favorable followthrough at minute OPEN.
        res = screen_stop_only_wedge_episodes(
            f, m1, FixedM1Probe(1, D("10"), D("0")),
        )
        self.assertEqual(res["conditional_early_exits"], 1)

    def test_followthrough_with_smaller_threshold_retains_real_stop(self):
        f, m1 = fixture()
        # The last COMPLETE pre-decision bar had a 3 bp favorable excursion.
        res = screen_stop_only_wedge_episodes(
            f, m1, FixedM1Probe(1, D("2"), D("5")),
        )
        self.assertEqual(res["followthrough_observed"], 1)
        self.assertEqual(res["conditional_early_exits"], 0)
        self.assertEqual(res["conditional_proxy_net_usdt"],
                         res["baseline_realized_net_usdt"])

    def test_recorded_stop_precedes_hypothetical_decision(self):
        f, m1 = fixture()
        res = screen_stop_only_wedge_episodes(
            f, m1, FixedM1Probe(4, D("10"), D("5")),
        )
        self.assertEqual(res["baseline_stop_first"], 1)
        self.assertEqual(res["conditional_early_exits"], 0)

    def test_long_and_short_costs(self):
        for direction in ("LONG", "SHORT"):
            with self.subTest(direction=direction):
                f, m1 = fixture(direction)
                res = screen_stop_only_wedge_episodes(
                    f, m1, FixedM1Probe(1, D("10"), D("5")),
                )
                self.assertEqual(res["episode_count"], 1)
                self.assertEqual(res["conditional_early_exits"], 1)

    def test_source_gap_fee_identity_and_provenance_fail_closed(self):
        def bad(change):
            f, m1 = fixture()
            change(f, m1)
            with self.assertRaises(M1ScreenBlocked):
                screen_stop_only_wedge_episodes(
                    f, m1, FixedM1Probe(1, D("10"), D("5")),
                )

        bad(lambda f, m: m.update(source_revision_reference=558))
        bad(lambda f, m: m.update(source="UNTRUSTED_M1"))
        bad(lambda f, m: m["items"][0]["candles"].pop(1))
        bad(lambda f, m: m["items"][0]["candles"][1].__setitem__(0, "180000"))
        bad(lambda f, m: f["episodes"][0]["facts"].update(pnl_usdt="-3"))
        bad(lambda f, m: f["episodes"][0]["facts"].update(side="LONG"))
        bad(lambda f, m: f["episodes"][0]["wedge"].update(exit_reason="TAKE"))
        bad(lambda f, m: f["episodes"].append(copy.deepcopy(f["episodes"][0])))

    def test_settings_reject_invalid_thresholds(self):
        with self.assertRaises(M1ScreenBlocked):
            FixedM1Probe(0, D("10"), D("5"))
        with self.assertRaises(M1ScreenBlocked):
            FixedM1Probe(1, D("0"), D("5"))
        with self.assertRaises(M1ScreenBlocked):
            FixedM1Probe(1, D("10"), D("-1"))


if __name__ == "__main__":
    unittest.main()
