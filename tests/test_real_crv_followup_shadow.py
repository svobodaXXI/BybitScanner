"""Frozen CRV 5m follow-up: as-of confirmation and explicit-pair negative control."""

import base64
import hashlib
import io
from pathlib import Path
import unittest
import zlib

import pandas as pd

from tests.test_real_crcl_pair_shadow import _confirmed
from tests.test_real_crv_pair_extension import _crv_frame, PAIRS
from wedge.local_episode_shadow import propose_local_episodes, trace_explicit_pair_checkpoints
from wedge.local_pair_shadow import evaluate_local_pair


FIXTURE = Path(__file__).parent / "fixtures/crv_20260920_followup_71_5m.csv.zlib.b64"
SHA256 = "f53af1086ab1829720443b6ae693eccc03d18454e715444491096de05c663c94"


def _extended():
    raw = zlib.decompress(base64.b64decode(FIXTURE.read_text(encoding="ascii").strip()))
    if hashlib.sha256(raw).hexdigest() != SHA256:
        raise AssertionError("CRV follow-up fixture checksum mismatch")
    newer = pd.read_csv(io.BytesIO(raw))
    old = _crv_frame()
    assert list(newer) == list(old) == ["time", "open", "high", "low", "close"]
    assert len(newer) == 71 and len(old) == 199
    pd.testing.assert_frame_equal(
        old.iloc[-31:].reset_index(drop=True),
        newer.iloc[:31].reset_index(drop=True), check_exact=True,
    )
    frame = pd.concat([old, newer.iloc[31:]], ignore_index=True)
    assert len(frame) == 239
    assert frame.time.is_unique and (frame.time.diff().iloc[1:] == 300_000).all()
    return frame


class CRVFollowupControl(unittest.TestCase):
    def test_overlap_and_closed_contiguous_followup(self):
        frame = _extended()
        self.assertEqual(int(frame.time.iloc[199]), 1789898700000)
        self.assertEqual(int(frame.time.iloc[238]), 1789910400000)

    def test_low196_never_confirms_and_low200_first_known_at_203(self):
        frame = _extended()
        self.assertNotIn(
            (196, "LOW"), {(p["index"], p["side"]) for p in _confirmed(frame)},
        )
        self.assertNotIn(
            (200, "LOW"),
            {(p["index"], p["side"]) for p in _confirmed(frame.iloc[:203].copy())},
        )
        self.assertIn(
            (200, "LOW"),
            {(p["index"], p["side"]) for p in _confirmed(frame.iloc[:204].copy())},
        )
        self.assertNotIn(
            (233, "HIGH"),
            {(p["index"], p["side"]) for p in _confirmed(frame.iloc[:236].copy())},
        )
        self.assertIn(
            (233, "HIGH"),
            {(p["index"], p["side"]) for p in _confirmed(frame.iloc[:237].copy())},
        )

    def test_post_breach_hypothesis_is_ambiguous_and_divergent(self):
        frame = _extended().iloc[:237].copy()
        raw = _confirmed(frame)
        out = propose_local_episodes(
            frame, raw, as_of_index=236, seed_indices={200}
        )
        self.assertEqual(out["status"], "OK", out)
        seed = next(p for p in out["proposals"]
                    if p["seed_index"] == 200 and p["seed_side"] == "LOW")
        self.assertEqual([p["index"] for p in seed["turns"]],
                         [200, 212, 215, 233])
        self.assertEqual([p["index"] for p in seed["competing_same_side"]],
                         [205, 210, 228])
        self.assertEqual(seed["status"], "UNKNOWN")
        self.assertIn("COMPETING_SAME_SIDE_TURNS", seed["reasons"])
        pair = evaluate_local_pair(
            frame, raw, as_of_index=236, timeframe="5", episode_start=200,
            anchors={"h1": 212, "h2": 233, "l1": 200, "l2": 215},
        )
        self.assertEqual(pair["status"], "INVALID", pair)
        self.assertIn("WIDTH_OR_CONVERGENCE_INVALID", pair["reasons"])
        self.assertGreater(pair["geometry"]["width_last_anchor"],
                           pair["geometry"]["width_start"])
        self.assertEqual(pair["episode_membership"], "CALLER_PROPOSED")


    def test_appended_bars_cannot_rewrite_original_frozen_crv_pair_history(self):
        old = _crv_frame()
        new = _extended()
        previous = trace_explicit_pair_checkpoints(
            old, _confirmed(old), as_of_index=198,
            checkpoints=(168, 178, 198), pair_specs=PAIRS,
        )
        current = trace_explicit_pair_checkpoints(
            new, _confirmed(new), as_of_index=238,
            checkpoints=(168, 178, 198, 203, 236, 238), pair_specs=PAIRS,
        )
        self.assertEqual(previous["status"], "OK", previous)
        self.assertEqual(current["status"], "OK", current)
        self.assertEqual(previous["history"], current["history"][:3])
        for checkpoint in current["history"]:
            for row in checkpoint["pairs"]:
                self.assertEqual(row["membership"], "UNPROVEN")
        later = {row["id"]: row for row in current["history"][-1]["pairs"]}
        self.assertEqual(later["CRV-A"]["baseline_checked_as_of"], 178)
        self.assertEqual(later["CRV-B"]["baseline_checked_as_of"], 168)
        self.assertIn(
            {"index": 200, "side": "LOW", "confirm_index": 203},
            later["CRV-A"]["extension_since_first"][
                "new_confirmed_post_anchor_pivots"
            ],
        )


if __name__ == "__main__":
    unittest.main()
