"""Synthetic contract tests; the uploaded S3 sources ZIP did not contain frozen OHLC."""

import unittest
from pathlib import Path

import pandas as pd

from wedge.local_pair_shadow import evaluate_local_pair


STEP = 300_000
BASE = 1_700_000_000_000


def sample():
    # Falling, contracting pair: H2/H8 10->8 and L1/L7 5->4.5.
    rows = []
    for i in range(14):
        upper = 10 + (i - 2) * (-2 / 6)
        lower = 5 + (i - 1) * (-0.5 / 6)
        middle = (upper + lower) / 2
        rows.append({"time": BASE + i * STEP, "open": middle,
                     "close": middle, "high": upper - 0.1, "low": lower + 0.1})
    for i in (2, 5, 8):
        rows[i]["high"] = 10 + (i - 2) * (-2 / 6)
    for i in (1, 4, 7):
        rows[i]["low"] = 5 + (i - 1) * (-0.5 / 6)
    frame = pd.DataFrame(rows)
    pivots = []
    for side, indices, key in (("HIGH", (2, 5, 8), "high"),
                               ("LOW", (1, 4, 7), "low")):
        for i in indices:
            pivots.append({"index": i, "side": side, "price": float(frame.iloc[i][key]),
                           "event_time_ms": BASE + i * STEP, "confirm_index": i + 3,
                           "confirm_time_ms": BASE + (i + 4) * STEP,
                           "confirmation_contiguous": True, "ambiguous_same_candle": False})
    return frame, pivots, {"h1": 2, "h2": 8, "l1": 1, "l2": 7}


def check(frame, pivots, anchors=None, **kwargs):
    return evaluate_local_pair(frame, pivots, as_of_index=kwargs.pop("as_of_index", 13),
                               timeframe=kwargs.pop("timeframe", "5"),
                               episode_start=kwargs.pop("episode_start", 1),
                               anchors=anchors or {"h1": 2, "h2": 8, "l1": 1, "l2": 7})


class LocalPairShadowContract(unittest.TestCase):
    def test_clean_research_pair_is_not_breakout_or_trading_admission(self):
        frame, pivots, anchors = sample()
        before = frame.copy(deep=True)
        result = check(frame, pivots, anchors)
        self.assertEqual(result["status"], "VALID_RESEARCH_PAIR")
        self.assertEqual(result["family"], "FALLING")
        self.assertEqual(result["completion_status"], "UNKNOWN")
        self.assertEqual(result["support"]["HIGH"]["additional"], 1)
        self.assertEqual(result["support"]["LOW"]["additional"], 1)
        self.assertEqual(result["strict"]["FULL"]["body_count"], 0)
        pd.testing.assert_frame_equal(frame, before)

    def test_post_anchor_body_crossing_cannot_be_trimmed(self):
        frame, pivots, anchors = sample()
        frame.loc[12, "open"] = 10
        frame.loc[12, "high"] = 10
        result = check(frame, pivots, anchors)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(result["strict"]["B"]["body_count"], 0)
        self.assertIn(12, result["strict"]["E"]["body_indices"])
        self.assertIn(12, result["strict"]["FULL"]["body_indices"])

    def test_anchored_body_crossing_is_invalid(self):
        frame, pivots, anchors = sample()
        frame.loc[6, "open"] = 11
        frame.loc[6, "high"] = 11
        result = check(frame, pivots, anchors)
        self.assertEqual(result["status"], "INVALID")
        self.assertIn("STRICT_BOUNDARY_VIOLATED_WITHIN_ANCHORED_EXTENT", result["reasons"])

    def test_missing_extra_high_support_is_unknown(self):
        frame, pivots, anchors = sample()
        pivots = [p for p in pivots if not (p["side"] == "HIGH" and p["index"] == 5)]
        result = check(frame, pivots, anchors)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIn("NO_ADDITIONAL_LOCAL_HIGH_SUPPORT", result["open_questions"])

    def test_same_candle_high_low_is_ambiguous(self):
        frame, pivots, anchors = sample()
        pivots[0]["ambiguous_same_candle"] = True
        result = check(frame, pivots, anchors)
        self.assertEqual(result["status"], "AMBIGUOUS")

    def test_future_confirmation_is_unknown(self):
        frame, pivots, anchors = sample()
        frame = frame.iloc[:10].copy()
        result = check(frame, pivots, anchors, as_of_index=9)
        self.assertEqual(result["status"], "UNKNOWN")

    def test_gap_or_other_timeframe_is_unknown(self):
        frame, pivots, anchors = sample()
        frame.loc[4, "time"] += 1
        self.assertEqual(check(frame, pivots, anchors)["status"], "UNKNOWN")
        fresh, pivots, anchors = sample()
        self.assertEqual(check(fresh, pivots, anchors, timeframe="1")["status"], "UNKNOWN")

    def test_missing_episode_provenance_remains_unknown(self):
        frame, pivots, anchors = sample()
        pivots[0]["confirmation_contiguous"] = False
        self.assertEqual(check(frame, pivots, anchors)["status"], "UNKNOWN")

    def test_no_existing_production_imports_new_module(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("analyzer/core.py", "wedge/analyzer.py", "wedge/__init__.py",
                     "geometry/engine.py", "main.py", "notification.py"):
            self.assertNotIn("local_pair_shadow", (root / name).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
