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


if __name__ == "__main__":
    unittest.main()
