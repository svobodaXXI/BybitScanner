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


if __name__ == "__main__":
    unittest.main()
