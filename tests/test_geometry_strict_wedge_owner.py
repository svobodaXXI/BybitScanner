"""Source-time owner CLUSDT Gold case: strict Rising Wedge lower boundary.

Only market OHLC and necessary anchor indices are retained. The archived
upper anchor 196 is not 3-right confirmed at the 199-bar frozen cutoff.
Use the independently generated, confirmed upper 140/189 to isolate the
lower-ray defect; do not claim exact historical signal replay.
"""
import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd

from geometry.candidate import build_candidate_lines
from geometry.evaluation import evaluate_candidate_pair
from geometry.envelope_metrics import evaluate_strict_wedge_wicks
from geometry.filter import filter_candidates
from pivots import find_pivots

FIXTURE = Path(__file__).parent / "fixtures/geometry_gold/CLUSDT_5m_strict_lower_20261112.json"


class StrictWedgeOwnerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        f = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = f["candles"]
        digest = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
        if digest != f["ohlc_sha256"] or len(rows) != 199:
            raise AssertionError("frozen OHLC changed")
        cls.frame = pd.DataFrame(rows, columns=f["columns"]) / f["price_scale"]
        cls.frame["time"] = [f["first_open_time_ms"] + i * 300_000 for i in range(len(rows))]
        cls.highs, cls.lows = find_pivots(cls.frame.copy())
        cls.upper = filter_candidates(build_candidate_lines(cls.highs))
        cls.lower = filter_candidates(build_candidate_lines(cls.lows))

    def pick(self, candidates, a, b):
        matches = [c for c in candidates if (c["anchor_index"], c["second_index"]) == (a, b)]
        self.assertEqual(len(matches), 1, (a, b))
        return matches[0]

    def evaluate(self, upper, lower):
        return evaluate_candidate_pair(upper, lower, highs=self.highs, lows=self.lows,
                                       current_index=len(self.frame)-1, candles=self.frame)

    def test_owner_strict_lower_rejects_generated_protruding_pair(self):
        upper = self.pick(self.upper, 140, 189)
        lower = self.pick(self.lower, 138, 185)
        end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
        line = lower["line"]
        breaches = [i for i in range(138, end+1)
                    if line["slope"]*i+line["intercept"]-self.frame.iloc[i].low > 1e-10]
        self.assertEqual(breaches, [169, 178, 179])
        self.assertGreater(lower["line"]["slope"], upper["line"]["slope"])
        self.assertIsNone(self.evaluate(upper, lower),
                          "strict lower wick protrusions must reject the pair during construction")

    def test_clean_owner_lower_ray_is_not_rejected_for_wicks(self):
        upper = self.pick(self.upper, 140, 189)
        lower = self.pick(self.lower, 138, 178)
        end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
        line = lower["line"]
        self.assertTrue(all(line["slope"]*i+line["intercept"]-self.frame.iloc[i].low <= 1e-10
                            for i in range(138, end+1)))
        self.assertIsNotNone(self.evaluate(upper, lower))


    def test_mirrored_falling_wedge_native_pairs(self):
        # Reflection preserves time, all actual candle distances and pivot order.
        frame = self.frame.copy()
        ceiling = 200.0
        frame["open"] = ceiling - self.frame["open"]
        frame["close"] = ceiling - self.frame["close"]
        frame["high"] = ceiling - self.frame["low"]
        frame["low"] = ceiling - self.frame["high"]
        # Reflect the identical confirmed input pivots, not the relative-price
        # noise filter (which is not invariant under additive reflection).
        highs = [{**p, "price": ceiling - p["price"], "type": "high"} for p in self.lows]
        lows = [{**p, "price": ceiling - p["price"], "type": "low"} for p in self.highs]
        upper = build_candidate_lines(highs)
        lower = self.pick(build_candidate_lines(lows), 140, 189)
        for a, b, rejected in ((138, 185, True), (138, 178, False)):
            with self.subTest(second=b):
                candidate = self.pick(upper, a, b)
                result = evaluate_candidate_pair(candidate, lower, highs=highs, lows=lows,
                                                 current_index=len(frame)-1, candles=frame)
                self.assertEqual(result is None, rejected)

    def test_strict_side_measurement_excludes_post_end_and_pre_anchor(self):
        lower = self.pick(self.lower, 138, 178)["line"]
        frame = self.frame.copy()
        end = 189
        baseline = evaluate_strict_wedge_wicks(lower, frame, "lower", end, 198)
        self.assertEqual(baseline, [])
        for index in (137, 190, 198):
            frame.loc[index, "low"] = 1.0
        self.assertEqual(evaluate_strict_wedge_wicks(lower, frame, "lower", end, 198), [])
        self.assertIsNone(evaluate_strict_wedge_wicks(lower, frame, "lower", end, 188))
        # A new single excursion inside the formation is measured explicitly.
        frame.loc[179, "low"] = lower["slope"] * 179 + lower["intercept"] - 0.01
        self.assertEqual(evaluate_strict_wedge_wicks(lower, frame, "lower", end, 198), [179])


class PonsStrictSupportCase(unittest.TestCase):
    def test_missing_local_high_is_available_as_strict_support(self):
        from geometry.wedge_boundaries import build_strict_wedge_support_lines, strict_support_pair_allowed
        from geometry.triangle_boundaries import local_alternation_pivots
        fixture = Path(__file__).parent / "fixtures/geometry_formation_fit/historical_cases.json"
        case = json.loads(fixture.read_text(encoding="utf-8"))["cases"]["PONS"]
        frame = pd.DataFrame(case["candles"], columns=["time", "open", "high", "low", "close", "volume"])
        highs, lows = find_pivots(frame.copy())
        upper = filter_candidates(build_candidate_lines(highs))
        lower = filter_candidates(build_candidate_lines(lows))
        self.assertNotIn(167, [p["index"] for p in highs])
        local_highs, _ = local_alternation_pivots(frame, len(frame)-1)
        self.assertIn(167, [p["index"] for p in local_highs])
        extra, _ = build_strict_wedge_support_lines(highs, lows, upper, lower, frame, len(frame)-1)
        matches = [c for c in extra if (c["anchor_index"], c["second_index"]) == (143, 167)]
        self.assertEqual(len(matches), 1)
        candidate = matches[0]
        self.assertGreaterEqual(candidate["structure_span"], 30)
        self.assertEqual(evaluate_strict_wedge_wicks(candidate["line"], frame, "upper", 186, len(frame)-1), [])
        opposite = next(c for c in lower if (c["anchor_index"], c["second_index"]) == (145, 186))
        self.assertTrue(strict_support_pair_allowed(candidate, opposite))
        self.assertFalse(strict_support_pair_allowed(candidate, {**opposite, "triangle_only": True}))
        self.assertFalse(strict_support_pair_allowed(candidate, {"line": {"slope": 1}}))
        geometry = evaluate_candidate_pair(candidate, opposite, highs=highs, lows=lows,
                                           candles=frame, current_index=len(frame)-1)
        self.assertIsNotNone(geometry)
        self.assertTrue(geometry.pair_metrics["anchor_sequence"]["valid"])
        self.assertEqual(geometry.start_index, 143)
        self.assertEqual(geometry.end_index, 186)


class SingleWickOwnerEvidence(unittest.TestCase):
    def test_axl_manual_boundary_has_only_one_wick_not_body_crossing(self):
        # Manual geometry evidence only, NOT a native signal replay.
        f = json.loads((FIXTURE.parent / "AXLUSDT_5m_single_wick_20261107.json").read_text())
        rows = f["candles"]
        self.assertEqual(hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest(),
                         f["ohlc_sha256"])
        frame = pd.DataFrame(rows, columns=f["columns"]) / f["price_scale"]
        offset = f["source_index_offset"]
        a, b = (i-offset for i in f["corrected_upper"])
        pa, pb = frame.iloc[a].high, frame.iloc[b].high
        slope = (pb-pa)/(b-a)
        line = dict(anchor_index=a, second_index=b, slope=slope, intercept=pa-slope*a)
        outside = evaluate_strict_wedge_wicks(line, frame, "upper", b, len(frame)-1)
        self.assertEqual([i+offset for i in outside], f["expected_strict_breach"])
        i = outside[0]
        self.assertLessEqual(max(frame.iloc[i].open, frame.iloc[i].close),
                             slope*i+line["intercept"])
        self.assertEqual(evaluate_strict_wedge_wicks(
            dict(anchor_index=a, slope=(frame.iloc[i].high-pa)/(i-a),
                 intercept=pa-(frame.iloc[i].high-pa)/(i-a)*a),
            frame, "upper", b, len(frame)-1), [])
        # Manual second contact is not a confirmed 3/3 pivot; do not claim
        # automatic recovery or relax structural anchor confirmation.
        highs, _ = find_pivots(frame.copy(), min_change=0)
        self.assertNotIn(b, [p["index"] for p in highs])


class SingleWickAcceptanceContract(unittest.TestCase):
    """Controlled perturbations of the frozen native CLUSDT geometry.

    The artificial wick is not a claimed historical owner annotation.
    Re-run native pivot generation and keep the exact candidate anchors.
    """
    @classmethod
    def setUpClass(cls):
        StrictWedgeOwnerCase.setUpClass()
        cls.frame = StrictWedgeOwnerCase.frame

    def pair(self, frame):
        highs, lows = find_pivots(frame.copy())
        def pick(points, a, b):
            matches = [c for c in build_candidate_lines(points)
                       if (c["anchor_index"], c["second_index"]) == (a, b)]
            self.assertEqual(len(matches), 1)
            return matches[0]
        upper, lower = pick(highs, 140, 189), pick(lows, 138, 178)
        end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
        breaches = evaluate_strict_wedge_wicks(lower["line"], frame, "lower", end, len(frame)-1)
        result = evaluate_candidate_pair(upper, lower, highs=highs, lows=lows,
                                         candles=frame, current_index=len(frame)-1)
        return breaches, result

    def test_isolated_wick_with_clean_support_is_lower_quality_candidate(self):
        frame = self.frame.copy()
        frame.loc[160, "low"] = 85.03
        breaches, geometry = self.pair(frame)
        self.assertEqual(breaches, [160])
        self.assertIsNotNone(geometry, "single body-contained wick must not erase otherwise supported pair")
        self.assertEqual(geometry.pair_metrics["strict_wick_exception_index"], 160)
        self.assertEqual((geometry.lower_line["anchor_index"], geometry.lower_line["second_index"]),
                         (138, 178))

    def test_body_crossing_and_two_wicks_remain_rejected(self):
        frame = self.frame.copy()
        frame.loc[160, "low"] = 85.03
        frame.loc[160, "open"] = 85.03
        breaches, geometry = self.pair(frame)
        self.assertEqual(breaches, [160])
        self.assertIsNone(geometry)
        frame = self.frame.copy()
        frame.loc[160, "low"] = 85.03
        frame.loc[161, "low"] = 85.06
        breaches, geometry = self.pair(frame)
        self.assertEqual(breaches, [160, 161])
        self.assertIsNone(geometry)

    def test_clean_candidate_beats_higher_score_single_wick(self):
        from tests.test_geometry_candidate_selection_freshness import _StubGeometry, _select
        clean = _StubGeometry("clean", 1., mode="CANONICAL")
        anomaly = _StubGeometry("single_wick", 999., mode="CANONICAL")
        anomaly.pair_metrics["strict_wick_exception_index"] = 160
        self.assertIs(_select([anomaly, clean]), clean)
        self.assertIs(_select([clean, anomaly]), clean)


if __name__ == "__main__":
    unittest.main()
