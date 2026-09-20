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
from tests.test_local_pair_shadow import sample
from wedge.local_episode_shadow import (propose_local_episodes, trace_episode_checkpoints,
                                       trace_explicit_pair_checkpoints)


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

    def test_crcl_late_anchor_is_only_reported_when_source_confirmed(self):
        frame = _frame()
        ledger = _confirmed(frame)
        traced = trace_episode_checkpoints(
            frame, ledger, as_of_index=198, seed_index=114, seed_side="LOW",
            checkpoints=(178, 188, 197, 198),
        )
        self.assertEqual(traced["status"], "OK", traced)
        self.assertEqual(traced["membership"], "UNPROVEN")
        self.assertTrue(all(row["membership"] == "UNPROVEN" for row in traced["history"]))
        at_197, at_198 = traced["history"][-2:]
        self.assertNotIn(
            (195, "HIGH"),
            {(p["index"], p["side"]) for row in traced["history"][:-1]
             for p in row["newly_confirmed"]},
        )
        self.assertIn(
            (195, "HIGH"),
            {(p["index"], p["side"]) for p in at_198["newly_confirmed"]},
        )
        self.assertEqual(at_197["as_of_index"], 197)
        self.assertEqual(at_198["as_of_index"], 198)
        self.assertIn(136, at_198["competing_same_side_indices"])
        self.assertIn("COMPETING_SAME_SIDE_TURNS", at_198["reasons"])

    def test_crcl_old_checkpoint_remains_identical_after_future_bars(self):
        full = _frame()
        cutoff = 178
        old = trace_episode_checkpoints(
            full.iloc[:cutoff + 1].copy(), _confirmed(full.iloc[:cutoff + 1].copy()),
            as_of_index=cutoff, seed_index=114, seed_side="LOW",
            checkpoints=(cutoff,),
        )
        current = trace_episode_checkpoints(
            full, _confirmed(full), as_of_index=198,
            seed_index=114, seed_side="LOW", checkpoints=(cutoff, 198),
        )
        self.assertEqual(old["status"], "OK", old)
        self.assertEqual(current["status"], "OK", current)
        self.assertEqual(old["history"][0], current["history"][0])
        self.assertEqual(old["history"][0]["membership"], "UNPROVEN")

    def test_0g_coincident_seed_remains_unproven_on_historical_checkpoints(self):
        frame = _zero_g_frame()
        raw = _confirmed(frame)
        traced = trace_episode_checkpoints(
            frame, raw, as_of_index=198, seed_index=87, seed_side="HIGH",
            checkpoints=(89, 90, 198),
        )
        self.assertEqual(traced["status"], "OK", traced)
        self.assertEqual(
            [row["seed_status"] for row in traced["history"]],
            ["NOT_YET_CONFIRMED", "AMBIGUOUS", "AMBIGUOUS"],
        )
        coincident = {(p["index"], p["side"]) for p in traced["history"][1]["newly_confirmed"]}
        self.assertTrue({(87, "HIGH"), (87, "LOW")} <= coincident)
        self.assertTrue(all(row["membership"] == "UNPROVEN" for row in traced["history"]))

    def test_history_rejects_impossible_checkpoint_or_future_ledger(self):
        frame = _frame()
        raw = _confirmed(frame)
        bad_order = trace_episode_checkpoints(
            frame, raw, as_of_index=198, seed_index=114, seed_side="LOW",
            checkpoints=(188, 178),
        )
        self.assertEqual(bad_order["status"], "UNKNOWN")
        self.assertIn("INVALID_CHECKPOINTS_OR_AS_OF", bad_order["reasons"])
        raw[0]["confirm_time_ms"] += STEP_MS
        bad_provenance = trace_episode_checkpoints(
            frame, raw, as_of_index=198, seed_index=114, seed_side="LOW",
            checkpoints=(178,),
        )
        self.assertEqual(bad_provenance["status"], "UNKNOWN")
        self.assertIn("CONFIRMED_LEDGER_UNPROVEN", bad_provenance["reasons"])

    def test_two_explicit_crcl_pairs_have_separate_first_knowable_verdicts(self):
        frame = _frame()
        original = frame.copy(deep=True)
        raw = _confirmed(frame)
        pair_specs = (
            {"id": "legacy-L123", "episode_start": 119,
             "anchors": {"h1": 119, "h2": 195, "l1": 123, "l2": 185}},
            {"id": "local-L114", "episode_start": 114,
             "anchors": {"h1": 119, "h2": 195, "l1": 114, "l2": 185}},
        )
        traced = trace_explicit_pair_checkpoints(
            frame, raw, as_of_index=198,
            checkpoints=(187, 188, 197, 198), pair_specs=pair_specs,
        )
        self.assertEqual(traced["status"], "OK", traced)
        self.assertEqual(traced["membership"], "UNPROVEN")
        self.assertEqual([r["as_of_index"] for r in traced["history"]],
                         [187, 188, 197, 198])
        for checkpoint in traced["history"][:-1]:
            self.assertEqual([r["id"] for r in checkpoint["pairs"]],
                             ["legacy-L123", "local-L114"])
            for pair in checkpoint["pairs"]:
                self.assertEqual(pair["pair_status"], "NOT_YET_EVALUABLE")
                self.assertIsNone(pair["pair_result"])
                self.assertEqual(pair["membership"], "UNPROVEN")
                self.assertNotIn({"index": 195, "side": "HIGH"},
                                 pair["confirmed_anchors"])
        self.assertNotIn({"index": 185, "side": "LOW"},
                         traced["history"][0]["pairs"][1]["confirmed_anchors"])
        self.assertIn({"index": 185, "side": "LOW"},
                      traced["history"][1]["pairs"][1]["confirmed_anchors"])
        old, local = traced["history"][-1]["pairs"]
        self.assertEqual((old["pair_status"], local["pair_status"]),
                         ("INVALID", "VALID_RESEARCH_PAIR"))
        self.assertIn("LOCAL_PIVOT_OUTSIDE_ANCHORED_ENVELOPE",
                      old["pair_result"]["reasons"])
        self.assertEqual(local["pair_result"]["completion_status"], "UNKNOWN")
        self.assertEqual(old["membership"], "UNPROVEN")
        self.assertEqual(local["membership"], "UNPROVEN")
        pd.testing.assert_frame_equal(frame, original)

    def test_explicit_pair_order_cannot_rewrite_a_prior_checkpoint(self):
        frame, raw = _frame(), _confirmed(_frame())
        a = {"id": "old", "episode_start": 119,
             "anchors": {"h1": 119, "h2": 195, "l1": 123, "l2": 185}}
        b = {"id": "new", "episode_start": 114,
             "anchors": {"h1": 119, "h2": 195, "l1": 114, "l2": 185}}
        early = trace_explicit_pair_checkpoints(
            frame, raw, as_of_index=198, checkpoints=(187,), pair_specs=(a, b)
        )
        full = trace_explicit_pair_checkpoints(
            frame, raw, as_of_index=198, checkpoints=(187, 198), pair_specs=(a, b)
        )
        reversed_pairs = trace_explicit_pair_checkpoints(
            frame, raw, as_of_index=198, checkpoints=(187, 198), pair_specs=(b, a)
        )
        self.assertEqual(early["status"], "OK", early)
        self.assertEqual(full["status"], "OK", full)
        self.assertEqual(reversed_pairs["status"], "OK", reversed_pairs)
        self.assertEqual(early["history"][0], full["history"][0])
        for idx in range(2):
            ordinary = {p["id"]: p for p in full["history"][idx]["pairs"]}
            reversed_set = {p["id"]: p for p in reversed_pairs["history"][idx]["pairs"]}
            self.assertEqual(ordinary, reversed_set)

    def test_explicit_pair_replay_fail_closed_on_bad_input(self):
        frame = _frame()
        raw = _confirmed(frame)
        spec = {"id": "A", "episode_start": 114,
                "anchors": {"h1": 119, "h2": 195, "l1": 114, "l2": 185}}
        for pairs in ((spec, spec), ({**spec, "episode_start": 150},)):
            out = trace_explicit_pair_checkpoints(
                frame, raw, as_of_index=198, checkpoints=(197, 198),
                pair_specs=pairs,
            )
            self.assertEqual(out["status"], "UNKNOWN")
            self.assertIn("INVALID_EXPLICIT_PAIR_REPLAY_INPUT", out["reasons"])
        no_future = trace_explicit_pair_checkpoints(
            frame.iloc[:198].copy(), _confirmed(frame.iloc[:198].copy()),
            as_of_index=197, checkpoints=(197,), pair_specs=(spec,)
        )
        self.assertEqual(no_future["status"], "OK", no_future)
        before_confirmation = no_future["history"][0]["pairs"][0]
        self.assertEqual(before_confirmation["pair_status"], "NOT_YET_EVALUABLE")
        self.assertIsNone(before_confirmation["pair_result"])
        self.assertEqual(before_confirmation["membership"], "UNPROVEN")

    def test_frozen_pair_extension_reports_new_E_body_without_rewriting_baseline(self):
        frame, ledger, anchors = sample()
        # The initial four anchors are confirmed on bar 11. Only bar 12
        # crosses the existing frozen resistance; no new pair is proposed.
        frame.loc[12, "open"] = 10.0
        frame.loc[12, "high"] = 10.0
        specs = ({"id": "synthetic-explicit-pair", "episode_start": 1,
                  "anchors": anchors},)
        first = trace_explicit_pair_checkpoints(
            frame.iloc[:12].copy(),
            [dict(p) for p in ledger if p["confirm_index"] <= 11],
            as_of_index=11, checkpoints=(10, 11), pair_specs=specs,
        )
        full = trace_explicit_pair_checkpoints(
            frame, ledger, as_of_index=13, checkpoints=(10, 11, 12, 13),
            pair_specs=specs,
        )
        self.assertEqual(first["status"], "OK", first)
        self.assertEqual(full["status"], "OK", full)
        self.assertEqual(first["history"], full["history"][:2])
        before = full["history"][0]["pairs"][0]
        frozen = full["history"][1]["pairs"][0]
        crossed = full["history"][2]["pairs"][0]
        repeated = full["history"][3]["pairs"][0]
        self.assertEqual(before["pair_status"], "NOT_YET_EVALUABLE")
        self.assertEqual(frozen["pair_status"], "VALID_RESEARCH_PAIR")
        self.assertEqual(frozen["baseline_checked_as_of"], 11)
        self.assertIsNone(frozen["extension_since_first"])
        self.assertEqual(crossed["frozen_first_status"], "VALID_RESEARCH_PAIR")
        self.assertEqual(crossed["baseline_checked_as_of"], 11)
        self.assertEqual(crossed["pair_status"], "UNKNOWN")
        self.assertEqual(crossed["extension_since_first"]["status"],
                         "EXCURSION_OBSERVED")
        self.assertEqual(crossed["extension_since_first"]["new_E_body_indices"],
                         [12])
        self.assertEqual(repeated["extension_since_first"]["new_E_body_indices"],
                         [12])
        self.assertEqual(repeated["extension_since_first"]["membership"],
                         "UNPROVEN")
        self.assertEqual(frozen["pair_result"]["strict"]["E"]["body_indices"], [])

    def test_sparse_checkpoints_do_not_claim_first_historical_pair_verdict(self):
        frame, ledger, anchors = sample()
        result = trace_explicit_pair_checkpoints(
            frame, ledger, as_of_index=13, checkpoints=(13,),
            pair_specs=({"id": "sparse", "episode_start": 1,
                         "anchors": anchors},),
        )
        self.assertEqual(result["status"], "OK", result)
        row = result["history"][0]["pairs"][0]
        self.assertEqual(row["first_knowable_as_of"], 11)
        self.assertEqual(row["baseline_checked_as_of"], 13)
        self.assertEqual(row["frozen_first_status"], "VALID_RESEARCH_PAIR")
        self.assertIsNone(row["extension_since_first"])
        self.assertEqual(row["membership"], "UNPROVEN")

    def test_no_new_excursion_is_not_evidence_of_episode_continuity(self):
        frame, ledger, anchors = sample()
        result = trace_explicit_pair_checkpoints(
            frame, ledger, as_of_index=13, checkpoints=(11, 13),
            pair_specs=({"id": "clean", "episode_start": 1,
                         "anchors": anchors},),
        )
        self.assertEqual(result["status"], "OK", result)
        initial, later = (entry["pairs"][0] for entry in result["history"])
        self.assertEqual(initial["frozen_first_status"], "VALID_RESEARCH_PAIR")
        self.assertEqual(later["pair_status"], "VALID_RESEARCH_PAIR")
        self.assertEqual(later["baseline_checked_as_of"], 11)
        self.assertEqual(later["extension_since_first"]["status"], "NO_NEW_EVIDENCE")
        self.assertEqual(later["extension_since_first"]["membership"], "UNPROVEN")
        self.assertEqual(result["membership"], "UNPROVEN")

    def test_not_imported_by_production_path(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("analyzer/core.py", "wedge/analyzer.py", "wedge/__init__.py",
                     "geometry/engine.py", "main.py", "notification.py"):
            self.assertNotIn(
                "local_episode_shadow", (root / name).read_text(encoding="utf-8")
            )


if __name__ == "__main__":
    unittest.main()
