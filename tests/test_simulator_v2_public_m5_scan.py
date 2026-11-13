"""Native Scanner research on public closed M5: provenance and zero trading IO."""
import unittest
from unittest.mock import patch

from geometry.ikigai_box import IkigaiBoxFormation
from research.simulator_v2.public_m5_scan import scan_public_closed_m5
from research.simulator_v2.wedge_observer import WedgeObservation


def public_doc(n=60):
    return {
        "source": "SIMULATION", "simulation_run_id": "m5test",
        "mode": "MARKET_ONLY", "market_data_source": "BYBIT_PUBLIC_KLINE",
        "symbol": "BTCUSDT", "timeframe": "5m",
        "events": [
            {"kind": "CANDLE_CLOSED", "time_ms": (i+1)*300000,
             "candle": {
                 "start_ms": i*300000, "end_ms": (i+1)*300000,
                 "open": 100, "high": 102, "low": 98,
                 "close": 100, "volume": 10,
             }}
            for i in range(n)
        ],
    }


class PublicM5ScannerResearchTests(unittest.TestCase):
    def test_exact_native_scanner_identity_and_causal_dedup(self):
        def wedge(self, *, simulation_run_id, symbol, closed_at_ms, bars):
            self.assert_contract = None  # only a fixture, not a Robot operation
            if len(bars) < 50 or closed_at_ms < 50 * 300000:
                return None
            return WedgeObservation(
                simulation_run_id=simulation_run_id, symbol=symbol,
                source_candle_start_ms=bars[-1].start_ms,
                available_at_ms=closed_at_ms,
                pattern="Falling Wedge",
                formation_id=f"{10*300000}:{20*300000}", final_score=65.,
                quality="Valid", scanner_filter_approved=True,
                scanner_filter_reason="RESEARCH_PASS",
                robot_geometry_ready=False, robot_geometry=None,
            )

        formation = IkigaiBoxFormation(
            direction="LONG", impulse_start_index=3, impulse_end_index=7,
            box_start_index=8, box_end_index=11,
            second_start_index=12, as_of_index=31,
            anchor_start_index=3, anchor_end_index=7,
            anchor_start_price=100., anchor_end_price=90.,
            box_low=94., box_high=98., second_extreme=88.,
            fibonacci_1_0=90., fibonacci_1_618=83.82, fibonacci_2_618=73.82,
        )
        import copy
        doc = public_doc()
        before = copy.deepcopy(doc)
        calls = []
        def box_detector(df):
            calls.append(len(df))
            return formation if len(df) >= 32 else None
        with patch("research.simulator_v2.wedge_observer.ReadOnlyWedgeScanner.evaluate_closed_m5_window",
                   wedge), patch("geometry.ikigai_box.detect_ikigai_box", side_effect=box_detector):
            result = scan_public_closed_m5(
                doc, ("WEDGE_FALLING", "IKIGAI_BOX"),
            )
        self.assertEqual(doc, before)
        self.assertEqual(len(result), 2)  # same candidate never counted repeatedly
        self.assertEqual([x["strategy"] for x in result], ["IKIGAI_BOX", "WEDGE_FALLING"])
        self.assertEqual(result[0]["available_at_ms"], 32*300000)
        self.assertEqual(result[0]["box_start_ms"], 8*300000)
        self.assertEqual(result[0]["box_end_ms"], 11*300000)
        self.assertEqual(result[0]["status"], "CONFIRMED_STRUCTURE_ONLY")
        self.assertEqual(result[1]["status"], "FILTER_APPROVED")
        self.assertEqual(result[1]["available_at_ms"], 50*300000)
        self.assertGreater(len(calls), 0)
        self.assertTrue(all(x["available_at_ms"] <= doc["events"][-1]["time_ms"] for x in result))
        self.assertFalse(any("trade_id" in x or "order_id" in x or "pnl" in x for x in result))

    def test_fail_closed_without_approved_source_or_complete_m5(self):
        doc = public_doc(52)
        for key, value in (
            ("mode", "STRATEGY"), ("source", "PAPER"),
            ("market_data_source", "PRIVATE"),
        ):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    scan_public_closed_m5({**doc, key: value}, ("WEDGE_FALLING",))
        self.assertEqual(scan_public_closed_m5(doc, ()), [])
        with self.assertRaises(ValueError):
            scan_public_closed_m5(doc, ("IKIGAI_BOX", "IKIGAI_BOX"))
        with self.assertRaises(ValueError):
            scan_public_closed_m5(doc, ("NAKED_RETEST",))
        broken = public_doc(52)
        broken["events"][50]["candle"]["start_ms"] += 300000
        with self.assertRaises(ValueError):
            scan_public_closed_m5(broken, ("IKIGAI_BOX",))
        future = public_doc(289)
        with self.assertRaises(ValueError):
            scan_public_closed_m5(future, ("WEDGE_FALLING",))

    def test_early_candles_do_not_trigger_native_wedge_or_box(self):
        doc = public_doc(30)
        with patch("research.simulator_v2.wedge_observer.ReadOnlyWedgeScanner.evaluate_closed_m5_window") as w, \
             patch("geometry.ikigai_box.detect_ikigai_box") as box:
            result = scan_public_closed_m5(doc, ("WEDGE_RISING", "IKIGAI_BOX"))
        self.assertEqual(result, [])
        w.assert_not_called()
        box.assert_not_called()


if __name__ == "__main__":
    unittest.main()
