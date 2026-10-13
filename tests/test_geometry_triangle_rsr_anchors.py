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
from geometry.pair_metrics import calculate_pair_metrics
from geometry.triangle_boundaries import (
    anchor_order_possible,
    build_triangle_only_lines,
    local_alternation_pivots,
)
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

    def test_anchor_order_precheck_matches_pair_metrics(self):
        # TRI-PERF-1: the pre-evaluation skip is exactly the secondary==expected
        # part of anchor_sequence.valid, so no skipped pair could be admitted.
        frame = _load_frame(_case())
        highs, lows = find_pivots(frame.copy())
        current = len(frame) - 1
        base_upper, base_lower = build_candidate_lines(highs), build_candidate_lines(lows)
        upper, lower = build_triangle_only_lines(
            highs, lows, base_upper, base_lower, current, candles=frame,
        )
        checked = skipped = 0
        for u in base_upper + upper:
            for w in base_lower + lower:
                if not (u.get("triangle_only") or w.get("triangle_only")):
                    continue
                if not (u["line"]["slope"] < 0 < w["line"]["slope"]):
                    continue
                metrics = calculate_pair_metrics(u, w, current, highs=highs, lows=lows, candles=frame)
                if metrics is None:
                    continue
                sequence = metrics["anchor_sequence"]
                expected = (
                    sequence["secondary_anchor"] is not None
                    and sequence["secondary_anchor"] == sequence["expected_secondary_index"]
                )
                possible = anchor_order_possible(u["line"], w["line"], highs, lows)
                self.assertEqual(possible, expected, (u["anchor_index"], w["anchor_index"]))
                checked += 1
                skipped += not possible
        self.assertGreater(skipped, 0)
        self.assertGreater(checked, skipped)


if __name__ == "__main__":
    unittest.main()
