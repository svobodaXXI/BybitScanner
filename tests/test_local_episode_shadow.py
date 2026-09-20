"""As-of chronological proposal tests: real saved CRCL and 0G source candles.

These are diagnostic proposals, NOT independently selected wedge episodes.
"""

import base64
import hashlib
import io
from pathlib import Path
import unittest
import zlib

import pandas as pd

from pivots import detect_pivots
from tests.test_real_crcl_pair_shadow import _confirmed, _frame
from wedge.local_episode_shadow import propose_local_episodes


ZERO_G = Path(__file__).parent / "fixtures/0g_a_20260920_closed_5m.csv.zlib.b64"
ZERO_G_SHA = "ed7919a3ef95b0767009bcf42d19c60849569663914ea413a6a326cbf0ab6d8f"
STEP_MS = 300_000


def _zero_g_frame():
    raw = zlib.decompress(base64.b64decode(ZERO_G.read_text(encoding="ascii").strip()))
    if hashlib.sha256(raw).hexdigest() != ZERO_G_SHA:
        raise AssertionError("original 0G#A closed source candle checksum differs")
    result = pd.read_csv(io.BytesIO(raw))
    assert len(result) == 199 and list(result) == ["time", "open", "high", "low", "close"]
    return result


class LocalEpisodeChronology(unittest.TestCase):
    def test_crcl_both_seed_orders_derived_from_original_raw_swings(self):
        frame = _frame()
        original = frame.copy(deep=True)
        out = propose_local_episodes(
            frame, _confirmed(frame), as_of_index=198, seed_indices={114, 119}
        )
        self.assertEqual(out["status"], "OK")
        low = next(p for p in out["proposals"] if p["seed_index"] == 114)
        high = next(p for p in out["proposals"] if p["seed_index"] == 119)
        self.assertEqual((low["order"], high["order"]), ("LOW_FIRST", "HIGH_FIRST"))
        self.assertEqual([p["index"] for p in low["turns"]], [114, 119, 123, 149])
        self.assertEqual([p["index"] for p in low["competing_same_side"]],
                         [136, 140, 147])
        self.assertEqual(low["status"], "UNKNOWN")
        self.assertIn("COMPETING_SAME_SIDE_TURNS", low["reasons"])
        self.assertIsNone(low["first_complete_as_of"])
        self.assertEqual(high["status"], "UNKNOWN")
        pd.testing.assert_frame_equal(frame, original)

    def test_crcl_as_of_prefix_is_immutable_and_no_future_turn_is_used(self):
        full = _frame()
        for cutoff, expected in ((122, [114, 119]), (126, [114, 119, 123]),
                                 (152, [114, 119, 123, 149])):
            prefix = full.iloc[:cutoff + 1].copy()
            first = propose_local_episodes(
                prefix, _confirmed(prefix), as_of_index=cutoff, seed_indices={114}
            )
            # Later historical data cannot revise an old prefix verdict.
            replay = propose_local_episodes(
                full.iloc[:cutoff + 1].copy(), _confirmed(full.iloc[:cutoff + 1].copy()),
                as_of_index=cutoff, seed_indices={114}
            )
            self.assertEqual(first, replay)
            proposal = next(p for p in first["proposals"] if p["seed_index"] == 114)
            self.assertEqual([p["index"] for p in proposal["turns"]], expected)
            self.assertTrue(all(p["confirm_index"] <= cutoff for p in proposal["turns"]))
            self.assertEqual(proposal["status"],
                             "UNKNOWN" if cutoff == 152 else "INSUFFICIENT")

    def test_real_0g_coincident_source_bar_stops_both_possible_orders(self):
        frame = _zero_g_frame()
        source = _confirmed(frame)
        raw_h, raw_l = detect_pivots(frame)
        self.assertIn(87, {p["index"] for p in raw_h} & {p["index"] for p in raw_l})
        for cutoff in (89, 90, 198):
            prefix = frame.iloc[:cutoff + 1].copy()
            out = propose_local_episodes(
                prefix, _confirmed(prefix), as_of_index=cutoff,
                seed_indices={75, 87}
            )
            self.assertEqual(out["status"], "OK")
            if cutoff == 89:
                self.assertFalse(any(p["seed_index"] == 87 for p in out["proposals"]))
                continue
            low = next(p for p in out["proposals"] if p["seed_index"] == 75)
            same = [p for p in out["proposals"] if p["seed_index"] == 87]
            self.assertEqual(low["status"], "AMBIGUOUS")
            self.assertTrue(all(p["status"] == "AMBIGUOUS" for p in same))
            self.assertEqual({p["seed_side"] for p in same}, {"HIGH", "LOW"})
            self.assertTrue(all(p["first_complete_as_of"] is None for p in same))

    def test_unproven_provenance_and_gap_fail_closed(self):
        frame = _frame()
        p = _confirmed(frame)
        p[0]["confirm_time_ms"] += STEP_MS
        out = propose_local_episodes(frame, p, as_of_index=198)
        self.assertEqual(out["status"], "UNKNOWN")
        self.assertIn("CONFIRMED_LEDGER_UNPROVEN", out["reasons"])
        frame, p = _frame(), _confirmed(_frame())
        frame.loc[10, "time"] += 1
        out = propose_local_episodes(frame, p, as_of_index=198)
        self.assertEqual(out["status"], "UNKNOWN")
        self.assertIn("SOURCE_PREFIX_UNPROVEN", out["reasons"])

    def test_not_imported_by_production_path(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("analyzer/core.py", "wedge/analyzer.py", "wedge/__init__.py",
                     "geometry/engine.py", "main.py", "notification.py"):
            self.assertNotIn(
                "local_episode_shadow", (root / name).read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
