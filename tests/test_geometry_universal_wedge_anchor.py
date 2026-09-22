"""Universal wedge anchor rule (owner authority; see
DOCUMENTS/SCANNER_GEOMETRY_CURRENT_COURSE.md, "Universal wedge anchor rule").

One negative control (the recovered original BONK 0..198 window that produced
the wrong U81/L128 Rising Wedge) and one existing positive control (PONS, from
the already-frozen tests/fixtures/geometry_formation_fit/historical_cases.json
eleven-case fixture) reused rather than duplicated. No exchange, Scanner,
Telegram or Robot calls.
"""
import json
from pathlib import Path
import unittest

import pandas as pd

from geometry.engine import analyze_geometry
from pivots import find_pivots
from wedge import analyze_wedge
from wedge.analyzer import _freshness_predicate

BONK_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "geometry_universal_anchor"
    / "bonk_0_198.json"
)

FORMATION_FIT_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "geometry_formation_fit"
    / "historical_cases.json"
)


class BonkAnchorLocalityNegativeTest(unittest.TestCase):
    """The recovered original 1000BONKUSDT as-of 0..198 window must never
    again select U81/L128, END191 as a wedge: U81 is the terminal high of an
    unrelated preceding impulse (window peak is HIGH70), and L128 belongs to
    a later, separate recovery leg -- not the impulse's next confirmed
    opposite-side pivot (that is LOW85).
    """

    @classmethod
    def setUpClass(cls):
        payload = json.loads(BONK_FIXTURE.read_text(encoding="utf-8"))
        cls.frame = pd.DataFrame(payload["candles"], columns=payload["columns"])
        cls.highs, cls.lows = find_pivots(cls.frame.copy())

    def test_original_pivots_reproduced(self):
        # Same evidence the earlier diagnosis recorded: 16 confirmed HIGH and
        # 17 confirmed LOW pivots on the exact recovered as-of window.
        self.assertEqual(len(self.highs), 16)
        self.assertEqual(len(self.lows), 17)

    def test_wrong_u81_l128_pair_is_not_admitted(self):
        current_index = len(self.frame) - 1
        geometry = analyze_geometry(
            self.highs,
            self.lows,
            current_index=current_index,
            candles=self.frame,
            freshness_predicate=_freshness_predicate,
        )
        if geometry is not None:
            self.assertNotEqual(
                (geometry.upper_line["anchor_index"], geometry.lower_line["anchor_index"]),
                (81, 128),
            )

    def test_wrong_u81_l128_pair_is_not_emitted_as_a_wedge(self):
        current_index = len(self.frame) - 1
        result = analyze_wedge(
            self.highs,
            self.lows,
            current_index=current_index,
            candles=self.frame,
        )
        geometry = result.get("geometry")
        if geometry is not None:
            self.assertNotEqual(
                (geometry["upper_line"]["anchor_index"], geometry["lower_line"]["anchor_index"]),
                (81, 128),
            )
        if geometry is not None and (
            geometry["upper_line"]["anchor_index"], geometry["lower_line"]["anchor_index"]
        ) == (81, 128):
            self.fail("wrong U81/L128 pair reached the Wedge layer")
        self.assertNotEqual(result.get("pattern"), "Rising Wedge")


class FirstAnchorMustEndPrecedingImpulseTest(unittest.TestCase):
    """False-positive pair: anchors in the right order and the second anchor
    IS the next confirmed opposite-side pivot, but the first anchor does not
    end the preceding impulse -- a higher HIGH20 follows it inside the same
    leg LOW0 -> LOW40. Changing only HIGH20 into a lower high must make the
    same pair valid, so the terminal-extreme check is the discriminator.
    """

    def _anchor_sequence(self, high20_price):
        from geometry.pair_metrics import calculate_pair_metrics

        frame = pd.DataFrame([dict(high=98., low=96.) for _ in range(61)])
        frame.loc[0, "low"] = 90.
        frame.loc[10, "high"] = 100.
        frame.loc[20, "high"] = high20_price
        frame.loc[40, "low"] = 95.
        highs = [dict(index=10, price=100.), dict(index=20, price=high20_price)]
        lows = [dict(index=0, price=90.), dict(index=40, price=95.)]
        upper = {"line": dict(slope=.1, intercept=99., anchor_index=10,
                              anchor_price=100., structure_span=30)}
        lower = {"line": dict(slope=.2, intercept=87., anchor_index=40,
                              anchor_price=95., structure_span=20)}
        metrics = calculate_pair_metrics(upper, lower, 60, highs=highs, lows=lows, candles=frame)
        return metrics["anchor_sequence"]

    def test_first_anchor_not_ending_the_impulse_is_rejected(self):
        sequence = self._anchor_sequence(high20_price=105.)
        self.assertEqual(sequence["family"], "rising")
        self.assertEqual(sequence["primary_anchor"], 10)
        self.assertEqual(sequence["secondary_anchor"], 40)
        self.assertEqual(sequence["expected_secondary_index"], 40)
        self.assertEqual(sequence["impulse_origin_index"], 0)
        self.assertFalse(sequence["first_anchor_terminal"])
        self.assertFalse(sequence["valid"])

        control = self._anchor_sequence(high20_price=99.)
        self.assertTrue(control["first_anchor_terminal"])
        self.assertTrue(control["valid"])


class PonsUniversalAnchorPositiveControlTest(unittest.TestCase):
    """PONS is the one wedge (not triangle) case in the frozen eleven-case
    fixture whose already-selected anchors satisfy the universal rule
    exactly: first anchor U143 (a HIGH) is chronologically before L145, and
    L145 is the immediate next confirmed LOW pivot after 143 -- a genuine
    single local episode. The fix must not disturb it.
    """

    @classmethod
    def setUpClass(cls):
        cases = json.loads(FORMATION_FIT_FIXTURE.read_text(encoding="utf-8"))["cases"]
        case = cases["PONS"]
        cls.frame = pd.DataFrame(
            case["candles"], columns=["time", "open", "high", "low", "close", "volume"]
        )
        cls.expected = case["expected"]
        highs, lows = find_pivots(cls.frame.copy())
        cls.geometry = analyze_geometry(
            highs,
            lows,
            len(cls.frame) - 1,
            cls.frame,
            _freshness_predicate,
        )

    def test_pons_wedge_anchors_unchanged(self):
        want = self.expected["geometry"]
        self.assertIsNotNone(self.geometry)
        self.assertEqual(self.geometry.upper_line["anchor_index"], want["anchors"][0])
        self.assertEqual(self.geometry.upper_line["second_index"], want["anchors"][1])
        self.assertEqual(self.geometry.lower_line["anchor_index"], want["anchors"][2])
        self.assertEqual(self.geometry.lower_line["second_index"], want["anchors"][3])
        self.assertEqual(self.geometry.start_index, want["start"])
        self.assertEqual(self.geometry.end_index, want["end"])
        self.assertEqual(self.geometry.pair_metrics["geometry_mode"], want["mode"])

    def test_pons_anchor_sequence_is_the_immediate_next_opposite_pivot(self):
        anchor_sequence = self.geometry.pair_metrics["anchor_sequence"]
        self.assertEqual(anchor_sequence["family"], "falling")
        self.assertEqual(anchor_sequence["primary_anchor"], 143)
        self.assertEqual(anchor_sequence["secondary_anchor"], 145)
        self.assertEqual(anchor_sequence["expected_secondary_index"], 145)
        self.assertTrue(anchor_sequence["valid"])


if __name__ == "__main__":
    unittest.main()
