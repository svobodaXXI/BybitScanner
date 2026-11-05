"""No-look-ahead, fees, adverse OPEN execution and isolation of blue scenario."""
from copy import deepcopy
from decimal import Decimal
import unittest

from research.historical_candle_feed import FIVE_MINUTES_MS
from research.h017_blue_execution_scenario import simulate_blue_open_scenario


M5 = FIVE_MINUTES_MS


def market(ohlc, previews, *, run="hypo"):
    events = [
        {"source": "SIMULATION", "simulation_run_id": run,
         "sequence": i + 1, "kind": "CANDLE_CLOSED", "time_ms": (i + 1) * M5,
         "candle": {"start_ms": i * M5, "end_ms": (i + 1) * M5,
                    "open": str(o), "high": str(h), "low": str(lo),
                    "close": str(c), "volume": "10"}}
        for i, (o, h, lo, c) in enumerate(ohlc)
    ]
    built = []
    for at, side, target in previews:
        open_price = Decimal(str(ohlc[at][0]))
        stop = open_price * (Decimal("0.993") if side == "LONG" else Decimal("1.007"))
        target = Decimal(str(target))
        r = target - open_price if side == "LONG" else open_price - target
        eligible = r >= abs(stop - open_price)
        p = {"source": "SIMULATION", "kind": "BLUE_5M_OPEN",
             "classification": "UNVALIDATED_GEOMETRY_ONLY",
             "time_ms": (at + 1) * M5, "open_ms": at * M5,
             "blue_available_at_ms": 0, "trend_version": 0,
             "side": side, "entry_price": str(open_price),
             "target_price": str(target),
             "risk_status": "RISK_PASS" if eligible else "RISK_BELOW_1R"}
        if eligible:
            p.update(stop_price=str(stop), quantity=str(Decimal(10) / open_price))
        built.append(p)
    return {"source": "SIMULATION", "simulation_run_id": run,
            "mode": "MARKET_ONLY", "events": events,
            "h017_blue_risk_previews": built}


class H017BlueExecutionScenarioTests(unittest.TestCase):
    def test_reuses_actual_open_and_charges_fees_and_slippage(self):
        doc = market([
            ("100", "101.5", "99.8", "100.8"),
        ], [(0, "LONG", "101")])
        before = deepcopy(doc)
        result = simulate_blue_open_scenario(doc)
        self.assertEqual(doc, before)
        self.assertEqual(result["source"], "SIMULATION")
        self.assertFalse(result["geometry_owner_verified"])
        self.assertFalse(result["production_ready"])
        self.assertEqual(result["counts"]["hypothetical_fills"], 1)
        self.assertEqual(result["counts"]["takes"], 1)
        self.assertEqual(result["open_slots_end"], 0)
        trade = result["closed_simulated_trades"][0]
        self.assertEqual(Decimal(trade["entry"]), Decimal("100.0200"))
        self.assertEqual(Decimal(trade["exit"]), Decimal("100.9798"))
        self.assertLess(Decimal(trade["net_pnl_usdt"]),
                        (Decimal("101") - Decimal("100")) * Decimal("0.1"))
        self.assertGreater(Decimal(trade["net_pnl_usdt"]), Decimal(0))
        self.assertEqual(
            Decimal(result["realized_cash_usdt"]),
            Decimal("200") + Decimal(result["net_pnl_closed_trades_usdt"]),
        )

    def test_same_candle_target_and_stop_is_adverse_and_gap_stop_worse(self):
        doc = market([("100", "101.5", "98.9", "100")],
                     [(0, "LONG", "101")])
        both = simulate_blue_open_scenario(doc, adverse_slippage_rate=0)
        self.assertEqual(both["counts"]["ambiguous_both_stop_first"], 1)
        self.assertEqual(both["closed_simulated_trades"][0]["reason"], "STOP_BOTH_SAME_M5")
        self.assertLess(Decimal(both["net_pnl_closed_trades_usdt"]), 0)
        gapped = market([
            ("100", "100.3", "99.8", "100"),
            ("98.5", "99.2", "98.2", "98.8"),
        ], [(0, "LONG", "101")])
        gap = simulate_blue_open_scenario(gapped, adverse_slippage_rate=0)
        self.assertEqual(Decimal(gap["closed_simulated_trades"][0]["exit"]), Decimal("98.5"))
        self.assertEqual(gap["counts"]["stops"], 1)

    def test_price_slippage_rechecks_one_r_and_does_not_fabricate_target(self):
        doc = market([("100", "101", "99.9", "100")], [(0, "LONG", "100.7")])
        s = simulate_blue_open_scenario(doc, adverse_slippage_rate="0.002")
        self.assertEqual(s["counts"]["hypothetical_fills"], 0)
        self.assertEqual(s["counts"]["rejected_after_slippage_1r"], 1)
        self.assertEqual(s["realized_cash_usdt"], "200")
        self.assertEqual(s["closed_simulated_trades"], [])

    def test_twenty_slots_budget_and_historical_prefix(self):
        bars = [("100", "100.2", "99.8", "100")] * 24
        doc = market(bars, [(i, "LONG", "105") for i in range(24)])
        full = simulate_blue_open_scenario(doc)
        self.assertEqual(full["peak_simultaneous_slots"], 20)
        self.assertEqual(full["counts"]["hypothetical_fills"], 20)
        self.assertEqual(full["counts"]["skipped_slots_full"], 4)
        self.assertEqual(full["open_slots_end"], 20)
        self.assertEqual(full["counts"]["hypothetical_exits"], 0)
        prefix = market(bars[:5], [(i, "LONG", "105") for i in range(5)])
        p = simulate_blue_open_scenario(prefix)
        self.assertEqual(p["counts"]["hypothetical_fills"], 5)
        self.assertEqual(
            full["open_simulated_positions"][:5],
            p["open_simulated_positions"],
        )
        self.assertTrue(all(x["trade_id"].startswith("SIMULATION:") for x in full["open_simulated_positions"]))

    def test_fractional_short_roundtrip_never_leaves_negative_reservation(self):
        # Repeated entry/exit near a real low-priced instrument forces
        # nonterminating 10-USDT position sizes, then exact FLAT reserves.
        bars = [("0.3166", "0.319", "0.315", "0.318")] * 4
        doc = market(bars, [(i, "SHORT", "0.313") for i in range(4)])
        result = simulate_blue_open_scenario(doc)
        self.assertEqual(result["counts"]["hypothetical_exits"], 4)
        self.assertEqual(result["counts"]["stops"], 4)
        self.assertEqual(result["open_slots_end"], 0)
        self.assertEqual(result["peak_simultaneous_slots"], 1)
        self.assertLess(Decimal(result["realized_cash_usdt"]), Decimal("200"))

    def test_short_and_rejected_preview_never_hardcode_a_win(self):
        doc = market([
            ("100", "100.3", "98.5", "99"),
            ("100", "100.3", "99.5", "100"),
        ], [(0, "SHORT", "99"), (1, "LONG", "100.2")])
        result = simulate_blue_open_scenario(doc, adverse_slippage_rate=0)
        self.assertEqual(result["counts"]["takes"], 1)
        self.assertEqual(result["counts"]["rejected_preview_below_1r"], 1)
        self.assertEqual(result["counts"]["hypothetical_fills"], 1)

    def test_rejects_foreign_provenance_malformed_bars_and_risk_fabrication(self):
        doc = market([("100", "100.5", "99.5", "100")], [(0, "LONG", "101")])
        for key, value in [("source", "PAPER"), ("mode", "STRATEGY")]:
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "SIMULATION"):
                simulate_blue_open_scenario({**doc, key: value})
        broken = deepcopy(doc)
        broken["events"][0]["candle"]["high"] = "97"
        with self.assertRaisesRegex(ValueError, "OHLC"):
            simulate_blue_open_scenario(broken)
        broken = deepcopy(doc)
        broken["events"][0]["kind"] = "ENTRY_FILLED"
        with self.assertRaisesRegex(ValueError, "executable"):
            simulate_blue_open_scenario(broken)
        broken = deepcopy(doc)
        broken["h017_blue_risk_previews"][0]["entry_price"] = "101"
        with self.assertRaisesRegex(ValueError, "OPEN"):
            simulate_blue_open_scenario(broken)
        broken = deepcopy(doc)
        broken["h017_blue_risk_previews"][0]["stop_price"] = "80"
        with self.assertRaisesRegex(ValueError, "fixed stop"):
            simulate_blue_open_scenario(broken)
        with self.assertRaises(ValueError):
            simulate_blue_open_scenario(doc, taker_fee_rate=-1)


if __name__ == "__main__":
    unittest.main()
