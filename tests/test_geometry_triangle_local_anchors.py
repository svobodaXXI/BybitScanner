"""G-TRI-3: Triangle Compression anchors belong to the local post-impulse formation.

The universal anchor rule (DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md) now also
admits triangle pairs: first anchor = extreme ending the preceding impulse, second
anchor = next confirmed opposite-side pivot, plus the owner swing criterion.
Recovered owner cases come from tests/fixtures/geometry_gold/manifest_g_tri_2.json
(PR #479); the synthetic cases prove both impulse directions. No exchange, Scanner,
Telegram or Robot calls.
"""
import unittest

import pandas as pd

from geometry.pair_metrics import calculate_pair_metrics
from tests.geometry_gold import ROOT, run_geometry_gold

G_TRI_2_MANIFEST = ROOT / "tests" / "fixtures" / "geometry_gold" / "manifest_g_tri_2.json"


class RecoveredOwnerTriangleCasesTest(unittest.TestCase):
    def test_pre_impulse_anchors_rejected_and_mega_preserved(self):
        results = {result["symbol"]: result for result in run_geometry_gold(G_TRI_2_MANIFEST)}
        self.assertEqual(set(results), {"KASUSDT", "LITUSDT", "MANAUSDT", "MEGAUSDT"})
        failures = [result for result in results.values() if not result["passed"]]
        self.assertEqual(failures, [], failures)
        self.assertEqual(
            results["MEGAUSDT"]["observed"]["geometry_identity"], [119, 178, 131, 172, 119, 186]
        )


def _triangle_sequence(highs, lows, upper, lower, current_index=60):
    frame = pd.DataFrame([dict(high=104., low=101.) for _ in range(current_index + 1)])
    for point in highs:
        frame.loc[point["index"], "high"] = point["price"]
    for point in lows:
        frame.loc[point["index"], "low"] = point["price"]
    metrics = calculate_pair_metrics(
        {"line": upper}, {"line": lower}, current_index, highs=highs, lows=lows, candles=frame
    )
    return metrics["anchor_sequence"]


class TriangleImpulseDirectionSymmetryTest(unittest.TestCase):
    # After DOWN: terminal LOW10 first, next HIGH40 second, next LOW50 contracts.
    DOWN_UPPER = dict(slope=-.1, intercept=109., anchor_index=40, anchor_price=105., structure_span=20)
    DOWN_LOWER = dict(slope=.05, intercept=99.5, anchor_index=10, anchor_price=100., structure_span=40)

    def test_after_down_impulse_lower_anchor_first_is_valid(self):
        sequence = _triangle_sequence(
            highs=[dict(index=0, price=110.), dict(index=40, price=105.)],
            lows=[dict(index=10, price=100.), dict(index=50, price=102.)],
            upper=self.DOWN_UPPER, lower=self.DOWN_LOWER,
        )
        self.assertEqual(sequence["family"], "triangle")
        self.assertEqual((sequence["primary_anchor"], sequence["secondary_anchor"]), (10, 40))
        self.assertTrue(sequence["first_anchor_terminal"])
        self.assertTrue(sequence["swing_contraction_valid"])
        self.assertTrue(sequence["valid"])

    def test_after_down_impulse_skipped_opposite_pivot_is_rejected(self):
        # HIGH25 is the neighbouring opposite pivot; HIGH40 belongs to a later swing.
        sequence = _triangle_sequence(
            highs=[dict(index=0, price=110.), dict(index=25, price=103.), dict(index=40, price=105.)],
            lows=[dict(index=10, price=100.), dict(index=50, price=102.)],
            upper=self.DOWN_UPPER, lower=self.DOWN_LOWER,
        )
        self.assertEqual(sequence["expected_secondary_index"], 25)
        self.assertFalse(sequence["valid"])

    def test_after_up_impulse_upper_anchor_first_is_valid(self):
        sequence = _triangle_sequence(
            highs=[dict(index=10, price=110.), dict(index=50, price=106.)],
            lows=[dict(index=0, price=95.), dict(index=40, price=100.)],
            upper=dict(slope=-.1, intercept=111., anchor_index=10, anchor_price=110., structure_span=40),
            lower=dict(slope=.05, intercept=98., anchor_index=40, anchor_price=100., structure_span=20),
        )
        self.assertEqual(sequence["family"], "triangle")
        self.assertEqual((sequence["primary_anchor"], sequence["secondary_anchor"]), (10, 40))
        self.assertTrue(sequence["valid"])

    def test_after_up_impulse_lower_anchor_from_older_leg_is_rejected(self):
        # LOW5 precedes the impulse-ending HIGH30: as the chronological first anchor it
        # does not end its leg (LOW0 is lower), and HIGH30 is not its next high.
        sequence = _triangle_sequence(
            highs=[dict(index=15, price=104.5), dict(index=30, price=110.), dict(index=50, price=106.)],
            lows=[dict(index=0, price=95.), dict(index=5, price=97.), dict(index=20, price=99.)],
            upper=dict(slope=-.1, intercept=113., anchor_index=30, anchor_price=110., structure_span=20),
            lower=dict(slope=.05, intercept=96.75, anchor_index=5, anchor_price=97., structure_span=15),
        )
        self.assertEqual(sequence["family"], "triangle")
        self.assertEqual(sequence["primary_anchor"], 5)
        self.assertNotEqual(sequence["expected_secondary_index"], 30)
        self.assertFalse(sequence["valid"])


if __name__ == "__main__":
    unittest.main()
