"""GEO-U1 H13/H14: source-time lifecycle of pinned TOSHI and OGN pairs."""

import json
import unittest

import pandas as pd

from geometry.consensus_boundary import build_boundary_consensus
from geometry.consensus_calibration import MAX_ACTIVE_PARAMETERS
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS
from geometry.consensus_lifecycle import (
    COMPLETED,
    CONTINUING,
    INTERNAL_DRIFT,
    derive_envelope_lifecycle,
)
from geometry.consensus_pair import build_envelope_pair_consensus
from geometry.consensus_selection import select_envelope_pair_shadow
from tests.geometry_gold import ROOT, load_manifest


CASE_ID = "1000TOSHIUSDT-locality-invariant"
IDENTITY = (("upper", (14, 78, 137)), ("lower", (45, 108)))


class DerivedLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        case = next(item for item in load_manifest()["cases"]
                    if item["case_id"] == CASE_ID)
        payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
        cls.frame = pd.DataFrame(payload["candles"])
        cls.parameters = dict(DEFAULT_SHADOW_REPORT_PARAMETERS)

    def _pair(self, cutoff, candles=None):
        candles = self.frame if candles is None else candles
        p = self.parameters
        common = dict(as_of_index=cutoff, episode_start_index=0,
                      inlier_band_atr=p["inlier_band_atr"],
                      separation_atr=p["separation_atr"])
        uppers = build_boundary_consensus(candles, side="upper", **common)
        lowers = build_boundary_consensus(candles, side="lower", **common)
        upper = next(item for item in uppers
                     if (item.side, item.inlier_pivot_indices) == IDENTITY[0])
        lower = next(item for item in lowers
                     if (item.side, item.inlier_pivot_indices) == IDENTITY[1])
        pair = build_envelope_pair_consensus(
            candles, [upper], [lower], as_of_index=cutoff,
            episode_start_index=0, episode_end_index=cutoff,
            touch_band_atr=p["touch_band_atr"],
            minimum_swing_width_fraction=p["minimum_swing_width_fraction"],
            minimum_swing_atr=p["minimum_swing_atr"],
            minimum_side_touch_clusters=p["minimum_side_touch_clusters"],
        )[0]
        return pair, uppers, lowers

    def _lifecycle(self, cutoff, candles=None):
        candles = self.frame if candles is None else candles
        pair, _, _ = self._pair(cutoff, candles)
        return derive_envelope_lifecycle(
            candles, pair, evidence_as_of_index=cutoff,
            legacy_max_support_gap_fraction=self.parameters["max_support_gap_fraction"],
        )

    def test_same_pair_chronology_and_future_rows(self):
        early = self._lifecycle(140)
        ambiguous = self._lifecycle(144)
        transition = self._lifecycle(147)
        final = self._lifecycle(199)
        results = (early, ambiguous, transition, final)

        self.assertTrue(all(item.pair_identity_ref == IDENTITY for item in results))
        self.assertEqual(early.lifecycle_state, CONTINUING)
        self.assertEqual(early.last_boundary_relative_event, ("upper", 137))
        self.assertEqual(early.post_boundary_event_chain, ())

        self.assertIsNone(ambiguous.lifecycle_state)
        self.assertEqual(ambiguous.transition_reason, "INTERNAL_CHAIN_INCOMPLETE")
        self.assertEqual(ambiguous.shadow_admission_disposition,
                         "DEFER_NEW_ADMISSION")
        self.assertEqual([(event.side, event.index, event.relation)
                          for event in ambiguous.post_boundary_event_chain],
                         [("lower", 141, "INTERNAL")])
        self.assertIsNone(ambiguous.decisive_event)

        for item in (transition, final):
            self.assertEqual(item.lifecycle_state, INTERNAL_DRIFT)
            self.assertEqual(item.transition_reason,
                             "INTERNAL_SWING_CHAIN_CONFIRMED")
            self.assertEqual([(event.side, event.index, event.relation)
                              for event in item.decisive_event],
                             [("lower", 141, "INTERNAL"),
                              ("upper", 144, "INTERNAL")])
        for item in results:
            self.assertLessEqual(item.last_boundary_relative_event[1],
                                 item.evidence_as_of_index)
            self.assertTrue(all(event.index <= item.evidence_as_of_index
                                for event in item.post_boundary_event_chain))
            self.assertEqual(item.legacy_support_gap_diagnostic.stale_shared_support,
                             False)

        self.assertEqual(early, self._lifecycle(140, self.frame.iloc[:141].copy()))
        self.assertEqual(ambiguous,
                         self._lifecycle(144, self.frame.iloc[:145].copy()))
        self.assertEqual(transition,
                         self._lifecycle(147, self.frame.iloc[:148].copy()))

    def test_diagnostic_call_does_not_change_selection_or_legacy_gate(self):
        pair, uppers, lowers = self._pair(199)
        parameters_before = dict(DEFAULT_SHADOW_REPORT_PARAMETERS)
        active_cap_before = MAX_ACTIVE_PARAMETERS
        selection_parameters = {name: value for name, value in self.parameters.items()
                                if name not in ("inlier_band_atr", "separation_atr")}

        def select():
            return select_envelope_pair_shadow(
                self.frame, uppers, lowers, as_of_index=199,
                episode_start_index=0, episode_end_index=199,
                **selection_parameters)

        before = select()
        lifecycle = derive_envelope_lifecycle(
            self.frame, pair, evidence_as_of_index=199,
            legacy_max_support_gap_fraction=self.parameters["max_support_gap_fraction"],
        )
        after = select()
        self.assertEqual(before, after)
        self.assertEqual(before.selection_status, "SELECTED")
        self.assertEqual(before.selected_pair_identity, IDENTITY)
        self.assertTrue(any("STALE_SHARED_SUPPORT" in row.rejection_reasons
                            for row in before.selection_trace))
        self.assertFalse(lifecycle.legacy_support_gap_diagnostic.stale_shared_support)
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, parameters_before)
        self.assertEqual(MAX_ACTIVE_PARAMETERS, active_cap_before)


class ExternalTransitionLifecycleTests(unittest.TestCase):
    IDENTITY = (("upper", (48, 154)), ("lower", (63, 120)))

    @classmethod
    def setUpClass(cls):
        manifest = load_manifest(
            ROOT / "tests/fixtures/geometry_gold/source_time_manifest_v6.json")
        case = next(item for item in manifest["cases"]
                    if item["case_id"] == "OGNUSDT-5m-src1789996800000")
        payload = json.loads((ROOT / case["fixture_ref"]).read_text(
            encoding="utf-8"))
        cls.frame = pd.DataFrame(payload["candles"], columns=payload["columns"])
        cls.parameters = dict(DEFAULT_SHADOW_REPORT_PARAMETERS)

    def _pair_and_lifecycle(self, cutoff, candles=None):
        candles = self.frame if candles is None else candles
        p = self.parameters
        common = dict(as_of_index=cutoff, episode_start_index=0,
                      inlier_band_atr=p["inlier_band_atr"],
                      separation_atr=p["separation_atr"])
        upper = next(item for item in build_boundary_consensus(
            candles, side="upper", **common)
            if (item.side, item.inlier_pivot_indices) == self.IDENTITY[0])
        lower = next(item for item in build_boundary_consensus(
            candles, side="lower", **common)
            if (item.side, item.inlier_pivot_indices) == self.IDENTITY[1])
        pair = build_envelope_pair_consensus(
            candles, [upper], [lower], as_of_index=cutoff,
            episode_start_index=0, episode_end_index=cutoff,
            touch_band_atr=p["touch_band_atr"],
            minimum_swing_width_fraction=p["minimum_swing_width_fraction"],
            minimum_swing_atr=p["minimum_swing_atr"],
            minimum_side_touch_clusters=p["minimum_side_touch_clusters"],
        )[0]
        lifecycle = derive_envelope_lifecycle(
            candles, pair, evidence_as_of_index=cutoff,
            legacy_max_support_gap_fraction=p["max_support_gap_fraction"],
        )
        return pair, lifecycle

    def test_same_pair_external_transition_and_source_time(self):
        checkpoints = {cutoff: self._pair_and_lifecycle(cutoff)
                       for cutoff in (157, 174, 181, 182, 198)}
        before_pair, before = checkpoints[157]
        _, isolated = checkpoints[174]
        _, unconfirmed = checkpoints[181]
        _, transition = checkpoints[182]
        final_pair, final = checkpoints[198]

        self.assertEqual(before_pair.alternating_touch_sequence,
                         (("upper", 48), ("lower", 120), ("upper", 154)))
        self.assertEqual(before.lifecycle_state, CONTINUING)
        self.assertEqual(before.last_boundary_relative_event, ("upper", 154))
        self.assertEqual(before.post_boundary_event_chain, ())
        self.assertIsNone(before.decisive_event)
        # The lower-side 126-139 excursion precedes U154 and did not complete
        # the old structure; no distance or bar-count threshold is involved.
        lower_at_126 = (before_pair.lower_boundary.slope * 126
                        + before_pair.lower_boundary.intercept)
        self.assertLess(float(self.frame.loc[126, "low"]), lower_at_126)

        for item in (isolated, unconfirmed):
            self.assertIsNone(item.lifecycle_state)
            self.assertEqual(item.transition_reason, "EXTERNAL_TRANSITION_UNPROVEN")
            self.assertIsNone(item.decisive_event)
        self.assertEqual([(event.side, event.index, event.external_side)
                          for event in isolated.post_boundary_event_chain
                          if event.relation == "EXTERNAL"],
                         [("upper", 171, "above_upper")])

        decisive = [(event.side, event.index, event.relation, event.external_side)
                    for event in transition.decisive_event]
        self.assertEqual(decisive, [
            ("upper", 171, "EXTERNAL", "above_upper"),
            ("lower", 179, "EXTERNAL", "above_upper"),
        ])
        for item in (transition, final):
            self.assertEqual(item.lifecycle_state, COMPLETED)
            self.assertEqual(item.transition_reason,
                             "EXTERNAL_SWING_CHAIN_CONFIRMED")
            self.assertEqual(item.decisive_event, transition.decisive_event)

        # Both final closes are back inside the old envelope; the completed
        # external chain remains in the same historical pair's lifecycle.
        for index in (197, 198):
            close = float(self.frame.loc[index, "close"])
            lower = (final_pair.lower_boundary.slope * index
                     + final_pair.lower_boundary.intercept)
            upper = (final_pair.upper_boundary.slope * index
                     + final_pair.upper_boundary.intercept)
            self.assertLess(lower, close)
            self.assertLess(close, upper)

        for cutoff, (_, item) in checkpoints.items():
            self.assertEqual(item.pair_identity_ref, self.IDENTITY)
            self.assertEqual(item.evidence_as_of_index, cutoff)
            self.assertLessEqual(item.last_boundary_relative_event[1], cutoff)
            self.assertTrue(all(event.index <= cutoff
                                for event in item.post_boundary_event_chain))
            self.assertTrue(all(event.index <= cutoff
                                for event in item.decisive_event or ()))
            self.assertEqual(
                item, self._pair_and_lifecycle(
                    cutoff, self.frame.iloc[:cutoff + 1].copy())[1])


if __name__ == "__main__":
    unittest.main()
