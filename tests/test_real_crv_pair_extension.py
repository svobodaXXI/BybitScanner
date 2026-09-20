"""Real saved CRV 5m controls for observable post-anchor E excursions.

The original snapshot has 200 rows; this fixture contains only the 199 bars
closed at the source decision timestamp. The pairs here are EXPLICIT research
hypotheses, not a new-episode detector or trading-admission rules.
"""

import base64
import hashlib
import io
from pathlib import Path
import unittest
import zlib

import pandas as pd

from tests.test_real_crcl_pair_shadow import _confirmed
from wedge.local_episode_shadow import trace_explicit_pair_checkpoints


FIXTURE = Path(__file__).parent / "fixtures/crv_20260920_closed_5m.csv.zlib.b64"
SOURCE_SHA256 = "077dfdfbf6c682effcc4f4c11524536bf67e4533c892073e24dffdbff2d8e6ad"
DECISION_MS = 1789898729792  # Original CRV analysis_started_at UTC.
STEP_MS = 300_000

PAIRS = (
    {"id": "CRV-A", "episode_start": 114,
     "anchors": {"h1": 115, "h2": 175, "l1": 114, "l2": 165}},
    {"id": "CRV-B", "episode_start": 122,
     "anchors": {"h1": 124, "h2": 159, "l1": 122, "l2": 165}},
)


def _crv_frame():
    raw = zlib.decompress(base64.b64decode(FIXTURE.read_text(encoding="ascii").strip()))
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise AssertionError("CRV source-time OHLC fixture checksum mismatch")
    frame = pd.read_csv(io.BytesIO(raw))
    assert len(frame) == 199 and list(frame) == ["time", "open", "high", "low", "close"]
    return frame


def _replay(frame, checkpoints):
    return trace_explicit_pair_checkpoints(
        frame, _confirmed(frame), as_of_index=len(frame) - 1,
        checkpoints=checkpoints, pair_specs=PAIRS,
    )


class RealCRVPairExtension(unittest.TestCase):
    def test_source_decision_and_both_first_knowable_prefixes(self):
        frame = _crv_frame()
        self.assertLessEqual(int(frame.time.iloc[-1]) + STEP_MS, DECISION_MS)
        self.assertGreater(int(frame.time.iloc[-1]) + 2 * STEP_MS, DECISION_MS)
        history = _replay(frame, (167, 168, 177, 178))["history"]
        for idx in (0, 1, 2):
            self.assertEqual(history[idx]["pairs"][0]["pair_status"], "NOT_YET_EVALUABLE")
        self.assertEqual(history[0]["pairs"][1]["pair_status"], "NOT_YET_EVALUABLE")
        self.assertEqual(history[1]["pairs"][1]["first_knowable_as_of"], 168)
        self.assertEqual(history[1]["pairs"][1]["baseline_checked_as_of"], 168)
        self.assertEqual(history[3]["pairs"][0]["first_knowable_as_of"], 178)
        self.assertEqual(history[3]["pairs"][0]["baseline_checked_as_of"], 178)
        self.assertEqual(history[3]["pairs"][0]["pair_result"]["strict"]["E"]["body_indices"], [])
        self.assertEqual(history[1]["pairs"][1]["pair_result"]["strict"]["E"]["body_indices"], [])

    def test_later_E_body_crossings_are_new_evidence_not_rewritten_baselines(self):
        frame = _crv_frame()
        before = frame.copy(deep=True)
        checkpoints = (168, 178, 190, 194, 195, 196, 197, 198)
        result = _replay(frame, checkpoints)
        self.assertEqual(result["status"], "OK", result)
        by_cutoff = {entry["as_of_index"]: {p["id"]: p for p in entry["pairs"]}
                     for entry in result["history"]}
        first_a, first_b = by_cutoff[178]["CRV-A"], by_cutoff[168]["CRV-B"]
        for pid, first in (("CRV-A", first_a), ("CRV-B", first_b)):
            self.assertEqual(first["pair_result"]["strict"]["E"]["body_indices"], [])
            self.assertIsNone(first["extension_since_first"])
            self.assertEqual(first["membership"], "UNPROVEN")
            self.assertEqual(by_cutoff[198][pid]["frozen_first_status"],
                             first["pair_status"])
            self.assertEqual(by_cutoff[198][pid]["membership"], "UNPROVEN")
        self.assertEqual(by_cutoff[194]["CRV-A"]["pair_result"]["strict"]["E"]["body_indices"], [])
        self.assertEqual(by_cutoff[195]["CRV-A"]["pair_result"]["strict"]["E"]["body_indices"], [195])
        self.assertEqual(by_cutoff[198]["CRV-A"]["pair_result"]["strict"]["E"]["body_indices"],
                         [195, 196, 197, 198])
        self.assertEqual(by_cutoff[198]["CRV-B"]["pair_result"]["strict"]["E"]["body_indices"],
                         [196, 197])
        self.assertIn(198, by_cutoff[198]["CRV-B"]["pair_result"]["strict"]["E"]["wick_indices"])
        self.assertEqual(by_cutoff[195]["CRV-A"]["extension_since_first"]["new_E_body_indices"],
                         [195])
        self.assertEqual(by_cutoff[198]["CRV-B"]["extension_since_first"]["new_E_body_indices"],
                         [196, 197])
        self.assertEqual(by_cutoff[198]["CRV-A"]["extension_since_first"]["status"],
                         "EXCURSION_OBSERVED")
        self.assertEqual(by_cutoff[198]["CRV-B"]["extension_since_first"]["status"],
                         "EXCURSION_OBSERVED")
        pd.testing.assert_frame_equal(frame, before)

    def test_future_bars_do_not_rewrite_past_prefix(self):
        full = _crv_frame()
        original = full.iloc[:191].copy()
        past = _replay(original, (168, 178, 190))
        extended = _replay(full, (168, 178, 190, 198))
        self.assertEqual(past["status"], "OK", past)
        self.assertEqual(extended["status"], "OK", extended)
        self.assertEqual(past["history"], extended["history"][:3])
        self.assertTrue(all(p["membership"] == "UNPROVEN"
                            for entry in extended["history"] for p in entry["pairs"]))


if __name__ == "__main__":
    unittest.main()
