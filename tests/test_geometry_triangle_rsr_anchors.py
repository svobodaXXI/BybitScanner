"""RSR-ANCHORS-4: exact owner Triangle Compression anchors on frozen RSRUSDT 5m.

Owner reference H144->H192 / L148->L178 (RSR-ANCHORS-2). H192 is a raw pivot the
global filter drops and L148->L178 has a single confirmation, so the reference is
reachable only through the Triangle-only T/Q lines plus R1 own-point support.
No exchange, Scanner, Telegram or Robot calls.
"""
import json
import unittest

import pandas as pd

from geometry.candidate import build_candidate_lines
from geometry.envelope_metrics import _with_own_points
from geometry.triangle_boundaries import build_triangle_only_lines, local_alternation_pivots
from pivots import find_pivots
from tests.geometry_gold import ROOT, _load_frame, load_manifest, run_geometry_gold

MANIFEST = ROOT / "tests" / "fixtures" / "geometry_gold" / "manifest_rsr_anchors.json"
DECISION_OPEN_MS = 1791798300000  # 2026-10-12 09:45 UTC
BREAKDOWN_OPEN_MS = 1791799200000  # 2026-10-12 10:00 UTC


def _case():
    return load_manifest(MANIFEST)["cases"][0]


def _full_frame():
    payload = json.loads((ROOT / _case()["fixture_ref"]).read_text(encoding="utf-8"))
    return pd.DataFrame(payload["candles"], columns=payload["columns"])


class RsrOwnerReferenceTest(unittest.TestCase):
    def test_exact_owner_identity_and_detection(self):
        (result,) = run_geometry_gold(MANIFEST)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["observed"]["geometry_identity"], [144, 192, 148, 178, 144, 192])
        self.assertTrue(result["observed"]["detected"])

    def test_post_decision_breakdown_is_not_used(self):
        full, frame = _full_frame(), _load_frame(_case())
        self.assertEqual(int(frame["time"].iloc[-1]), DECISION_OPEN_MS)
        self.assertEqual(int(full["time"].iloc[-1]), BREAKDOWN_OPEN_MS)
        self.assertEqual(len(full) - len(frame), 3)
        # Q pivots read candles only up to current_index, whatever follows.
        self.assertEqual(
            local_alternation_pivots(full, len(frame) - 1),
            local_alternation_pivots(frame, len(frame) - 1),
        )

    def test_global_pivots_unchanged_and_h192_is_local_only(self):
        frame = _load_frame(_case())
        highs, lows = find_pivots(frame.copy())
        local_highs, _ = local_alternation_pivots(frame, len(frame) - 1)
        self.assertEqual([p["index"] for p in highs][-3:], [175, 184, 188])
        self.assertIn(192, [p["index"] for p in local_highs])

    def test_extra_lines_are_triangle_only_and_triangle_sloped(self):
        frame = _load_frame(_case())
        highs, lows = find_pivots(frame.copy())
        upper, lower = build_triangle_only_lines(
            highs, lows, build_candidate_lines(highs), build_candidate_lines(lows),
            len(frame) - 1, candles=frame,
        )
        self.assertIn((144, 192), {(c["anchor_index"], c["second_index"]) for c in upper})
        self.assertIn((148, 178), {(c["anchor_index"], c["second_index"]) for c in lower})
        self.assertTrue(all(c["triangle_only"] for c in upper + lower))
        self.assertTrue(all(c["line"]["slope"] < 0 for c in upper))
        self.assertTrue(all(c["line"]["slope"] > 0 for c in lower))

    def test_r1_is_a_no_op_for_regular_candidates(self):
        frame = _load_frame(_case())
        highs, lows = find_pivots(frame.copy())
        for points in (highs, lows):
            for candidate in build_candidate_lines(points):
                self.assertEqual(_with_own_points(points, candidate), points)


if __name__ == "__main__":
    unittest.main()
