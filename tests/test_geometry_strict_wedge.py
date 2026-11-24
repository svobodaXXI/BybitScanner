"""Frozen real-price regression; no historical runtime replay claim."""
import hashlib
import json
from pathlib import Path
import unittest

import pandas as pd
from geometry.candidate import build_candidate_lines
from geometry.filter import filter_candidates
from geometry.evaluation import evaluate_candidate_pair
from geometry.engine import analyze_geometry
from pivots import find_pivots
from wedge.analyzer import _freshness_predicate

FIXTURE = Path(__file__).parent / "fixtures" / "geometry_gold" / "XANUSDT_5m_strict_lower_20261124.json"


class StrictWedgeFrozenTest(unittest.TestCase):
    def test_original_rising_wedge_pair_cannot_be_constructed(self):
        case = json.loads(FIXTURE.read_text())
        encoded = json.dumps(case["ohlc_int"], separators=(",", ":")).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), case["ohlc_int_sha256"])
        frame = pd.DataFrame(case["ohlc_int"], columns=["open", "high", "low", "close"]) / case["price_scale"]
        frame["time"] = [case["first_open_ms"] + i * case["step_ms"] for i in range(len(frame))]
        frame["volume"] = 0.
        frame = frame.iloc[:case["as_of_index"] + 1].copy()
        highs, lows = find_pivots(frame.copy())
        a, b, c, d = case["original_anchors"]
        def pick(points, start, second):
            candidates = filter_candidates(build_candidate_lines(points))
            return next((item for item in candidates if (item["anchor_index"], item["second_index"]) == (start, second)), None)
        upper, lower = pick(highs, a, b), pick(lows, c, d)
        self.assertIsNotNone(upper, "archived upper pair not generated on this cutoff")
        self.assertIsNotNone(lower, "archived lower pair not generated on this cutoff")
        end = max(upper["points"][-1]["index"], lower["points"][-1]["index"])
        line = lower["line"]
        protrusions = [i for i in range(c, end + 1) if float(frame.iloc[i]["low"]) < line["slope"] * i + line["intercept"] - 1e-12]
        self.assertIn(178, protrusions)
        self.assertIn(179, protrusions)
        original = evaluate_candidate_pair(upper, lower, highs=highs, lows=lows, current_index=len(frame)-1, candles=frame)
        winner = analyze_geometry(highs, lows, len(frame)-1, frame, _freshness_predicate)
        print("ARCHIVED_PAIR", case["original_anchors"], "END", end, "PROTRUSIONS", protrusions,
              "PAIR_VALIDATION", None if original is None else original.validation,
              "PAIR_ANCHORS", None if original is None else original.pair_metrics.get("anchor_sequence"),
              "NATIVE_WINNER", None if winner is None else [winner.upper_line["anchor_index"], winner.upper_line["second_index"], winner.lower_line["anchor_index"], winner.lower_line["second_index"]])
        self.assertIsNone(original, "strict lower wick protrusions must prevent pair construction")


if __name__ == "__main__":
    unittest.main()
