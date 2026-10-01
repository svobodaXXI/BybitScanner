"""GEO-U1-PERF: exact semantic parity of the optimized SHADOW geometry path.

BEFORE references (never recomputed on the slow base code here):
- ``perf_parity_v1.json``: canonical report sha256 of all 17 target crypto
  cases under DEFAULT_SHADOW_REPORT_PARAMETERS, captured on untouched base
  3b9ea49 in fresh processes;
- ``calibration_result_v1.json``: the pinned H0 outcome matrix (16 cases x 602
  parameter sets) for the representative H0 parameter matrix.
"""

import hashlib
import json
import unittest

import pandas as pd

import geometry.consensus_calibration_population as population
import geometry.consensus_pair as consensus_pair
from geometry.consensus_boundary import build_boundary_consensus
from geometry.consensus_calibration import (
    case_outcome,
    derived_parameter_sets,
    expand_outcome_matrix,
)
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS, build_gold_case_report
from geometry.consensus_pair import build_envelope_pair_consensus
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
PARITY = json.loads((GOLD / "perf_parity_v1.json").read_text(encoding="utf-8"))
H0 = json.loads((GOLD / "calibration_result_v1.json").read_text(encoding="utf-8"))
H0_OUTCOMES = expand_outcome_matrix(H0["outcome_matrix"])
SETS, _, _ = derived_parameter_sets(H0["active_parameters"])
CASES = {c["case_id"]: c for name in (
    "manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
    "source_time_manifest_v3.json", "source_time_manifest_v4.json")
    for c in load_manifest(GOLD / name)["cases"]}
# Semantic hashes of every Gold manifest/fixture/metadata and the H0 result at base 3b9ea49.
GOLD_SEMANTIC_SHA256 = "7bac80af68c80c1d3bf9b9ec45eee10cba302bafa2563fed7d7eef6bf3320d42"
DEFAULTS_AT_BASE = {
    "inlier_band_atr": 0.2, "separation_atr": 0.75, "touch_band_atr": 0.2,
    "minimum_swing_width_fraction": 0.30, "minimum_swing_atr": 0.5,
    "minimum_side_touch_clusters": 2, "min_cross_boundary_traversals": 1,
    "min_alternating_touches": 3, "min_touch_balance": 0.25,
    "min_shared_support_coverage": 0.25, "max_support_gap_fraction": 0.5,
    "terminal_window_bars": 30, "terminal_segments": 3,
    "compression_max_ratio": 0.9, "expansion_min_ratio": 1.1,
    "segment_tolerance": 0.05, "single_bar_narrow_ratio": 0.5,
}


def _sha(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _gold_paths():
    names = ["manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
             "source_time_manifest_v3.json", "source_time_manifest_v4.json"]
    paths = [GOLD / n for n in names] + [GOLD / f"instrument_metadata_v{i}.json" for i in (1, 2, 3)]
    paths.append(GOLD / "calibration_result_v1.json")
    for name in names:
        paths += [ROOT / c["fixture_ref"] for c in load_manifest(GOLD / name)["cases"]]
    return paths


def _semantic(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class DefaultParityTests(unittest.TestCase):
    def test_all_17_default_canonical_reports_unchanged(self):              # A, C, D, E
        self.assertEqual(len(PARITY["defaults"]), 17)
        for case_id, before in sorted(PARITY["defaults"].items()):
            report = build_gold_case_report(CASES[case_id], _load_frame(CASES[case_id]))
            self.assertEqual(_sha(report), before["sha256"], case_id)
            shadow = report["shadow"]
            self.assertEqual((shadow["candidate_count"], shadow["admissible_count"],
                              shadow["deciding_component"]),
                             (before["candidate_count"], before["admissible_count"],
                              before["deciding_component"]), case_id)

    def test_tie_break_and_no_admissible_cases_are_pinned(self):            # F, G
        defaults = PARITY["defaults"]
        self.assertEqual(sorted(k for k, v in defaults.items()
                                if v["deciding_component"] == "IDENTITY_TIE_BREAK"),
                         ["1000XECUSDT-no-local-formation", "CASHCATUSDT-5m-src1790002800000",
                          "NXPCUSDT-5m-src1789996800000"])
        self.assertEqual(sorted(k for k, v in defaults.items() if v["admissible_count"] == 0),
                         ["1000XECUSDT-no-local-formation", "ENAUSDT-1m-src1789759320000"])

    def test_pinned_reproducibility_hashes_and_future_rows(self):           # H
        for name in ("source_time_manifest_v2.json", "source_time_manifest_v3.json",
                     "source_time_manifest_v4.json"):
            for case_id, record in load_manifest(GOLD / name)["reproducibility"].items():
                if case_id not in PARITY["future_row_cases"]:
                    continue
                expected = {run["canonical_report_sha256"] for run in record["runs"]}
                self.assertEqual(len(expected), 1)
                frame = _load_frame(CASES[case_id])
                future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
                extended = pd.concat([frame, future], ignore_index=True)
                for candles in (frame, extended):
                    self.assertEqual({_sha(build_gold_case_report(CASES[case_id], candles))},
                                     expected, case_id)


class MatrixParityTests(unittest.TestCase):
    def test_representative_h0_matrix_matches_pinned_outcomes(self):        # B, C, D, E, F, G
        labels = PARITY["representative_h0_labels"]
        self.assertTrue(set(labels) <= set(H0["outcome_matrix"]["labels"]))
        for case_id in PARITY["matrix_test_cases"]:
            frame = _load_frame(CASES[case_id])
            for label in labels:
                self.assertEqual(case_outcome(CASES[case_id], frame, SETS[label]),
                                 H0_OUTCOMES[case_id][label], (case_id, label))

    def test_matrix_covers_tie_break_and_no_admissible(self):
        seen = {(H0_OUTCOMES[c][l]["selection_status"], H0_OUTCOMES[c][l]["deciding_component"])
                for c in PARITY["matrix_test_cases"] for l in PARITY["representative_h0_labels"]}
        self.assertIn("NO_ADMISSIBLE_PAIR", {status for status, _ in seen})
        self.assertIn("IDENTITY_TIE_BREAK", {deciding for _, deciding in seen})


class DeterminismAndInvarianceTests(unittest.TestCase):
    def test_candidate_order_and_repetition_do_not_change_pairs(self):     # I, J, P
        case = CASES["NXPCUSDT-5m-src1789996800000"]
        frame = _load_frame(case)
        boundary = dict(as_of_index=198, episode_start_index=0, inlier_band_atr=0.2,
                        separation_atr=0.75)
        uppers = build_boundary_consensus(frame, side="upper", **boundary)
        lowers = build_boundary_consensus(frame, side="lower", **boundary)
        kwargs = dict(as_of_index=198, episode_start_index=0, episode_end_index=198,
                      touch_band_atr=0.2, minimum_swing_width_fraction=0.3,
                      minimum_swing_atr=0.5)
        first = build_envelope_pair_consensus(frame, uppers, lowers, **kwargs)
        again = build_envelope_pair_consensus(frame, uppers, lowers, **kwargs)
        reordered = build_envelope_pair_consensus(frame, uppers[::-1], lowers[::-1], **kwargs)
        self.assertEqual(first, again)
        self.assertEqual(first, reordered)

    def test_no_module_level_cache_state(self):                             # P
        mutable = [name for name, value in vars(consensus_pair).items()
                   if isinstance(value, (dict, list, set)) and not name.startswith("__")]
        self.assertEqual(mutable, [])

    def test_gold_h0_h1_defaults_and_policy_unchanged(self):                # K, L, M, N
        joined = "".join(_semantic(p) for p in _gold_paths())
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(), GOLD_SEMANTIC_SHA256)
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, DEFAULTS_AT_BASE)
        self.assertEqual(population.POLICY_V1.policy_version, "GEO-U1-POP-1")
        self.assertEqual(population.POLICY_V1.eligible_instrument_classes,
                         ("CRYPTO_LINEAR_PERPETUAL",))


if __name__ == "__main__":
    unittest.main()
