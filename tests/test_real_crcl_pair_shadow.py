"""Frozen CRCL 5m source-OHLC control: original 2026-09-20 snapshot, not synthetic.

The checked-in fixture contains only the five price/time columns of the 199 fully
closed candles, before the original 2026-09-20T10:04:52Z decision. No future bars.
"""

import base64
import hashlib
import io
from pathlib import Path
import unittest
import zlib

import pandas as pd

from pivots import detect_pivots
from wedge.local_pair_shadow import evaluate_local_pair


FIXTURE = Path(__file__).parent / "fixtures/crcl_20260920_closed_5m.csv.zlib.b64"
CANONICAL_SHA256 = "d5fd8cf3cb5b90e923186cf72c6ada44bb38853649e2c85c2df7a940480833d2"
DECISION_MS = 1789898692705  # original analysis.json analysis_started_at
STEP_MS = 300_000


def _frame():
    raw = zlib.decompress(base64.b64decode(FIXTURE.read_text(encoding="ascii").strip()))
    if hashlib.sha256(raw).hexdigest() != CANONICAL_SHA256:
        raise AssertionError("CRCL source OHLC fixture checksum mismatch")
    frame = pd.read_csv(io.BytesIO(raw))
    assert len(frame) == 199 and list(frame) == ["time", "open", "high", "low", "close"]
    assert frame.time.is_monotonic_increasing
    return frame


def _confirmed(frame):
    highs, lows = detect_pivots(frame)
    times = [int(v) for v in frame.time]
    paired = {p["index"] for p in highs} & {p["index"] for p in lows}
    return [
        {"index": p["index"], "side": side, "price": p["price"],
         "event_time_ms": times[p["index"]],
         "confirm_index": p["index"] + 3,
         "confirm_time_ms": times[p["index"] + 3] + STEP_MS,
         "confirmation_contiguous": True,
         "ambiguous_same_candle": p["index"] in paired}
        for side, points in (("HIGH", highs), ("LOW", lows)) for p in points
    ]


class RealCRCLShadowControl(unittest.TestCase):
    def test_original_as_of_discards_forming_200th_bar(self):
        frame = _frame()
        self.assertEqual(int(frame.time.iloc[-1]) + STEP_MS, 1789898400000)
        self.assertLessEqual(int(frame.time.iloc[-1]) + STEP_MS, DECISION_MS)
        self.assertGreater(int(frame.time.iloc[-1]) + 2 * STEP_MS, DECISION_MS)
        self.assertTrue(all(p["confirm_time_ms"] <= DECISION_MS for p in _confirmed(frame)))

    def test_second_upper_anchor_was_not_usable_one_bar_earlier(self):
        frame = _frame()
        earlier = _confirmed(frame.iloc[:-1].copy())
        now = _confirmed(frame)
        self.assertNotIn((195, "HIGH"), {(p["index"], p["side"]) for p in earlier})
        self.assertIn((195, "HIGH"), {(p["index"], p["side"]) for p in now})

    def test_crcl_local_pair_valid_but_legacy_lower_anchor_invalid(self):
        frame = _frame()
        raw = _confirmed(frame)
        local = evaluate_local_pair(
            frame, raw, as_of_index=198, timeframe="5", episode_start=114,
            anchors={"h1": 119, "h2": 195, "l1": 114, "l2": 185},
        )
        self.assertEqual(local["status"], "VALID_RESEARCH_PAIR", local)
        self.assertEqual(local["family"], "FALLING")
        self.assertEqual(local["completion_status"], "UNKNOWN")
        self.assertEqual(local["strict"]["FULL"]["body_count"], 0)
        old = evaluate_local_pair(
            frame, raw, as_of_index=198, timeframe="5", episode_start=119,
            anchors={"h1": 119, "h2": 195, "l1": 123, "l2": 185},
        )
        self.assertEqual(old["status"], "INVALID", old)
        self.assertIn("LOCAL_PIVOT_OUTSIDE_ANCHORED_ENVELOPE", old["reasons"])


if __name__ == "__main__":
    unittest.main()
