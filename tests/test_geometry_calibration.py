"""GEO-U1 Slice H0: SHADOW-only calibration methodology contracts (focused).

The full exact run (all 16 cases x every tested parameter set) is pinned in
``calibration_result_v1.json`` by ``python -m geometry.consensus_calibration``.
These tests re-derive every conclusion from the pinned outcome matrix (pure
and fast) and recompute exact outcomes only for the cheap cases.
"""

import hashlib
import json
import re
import unittest

import geometry.consensus_calibration as calibration
from geometry.consensus_calibration import (
    DEFAULT_SHADOW_REPORT_PARAMETERS,
    NO_ADMISSIBLE,
    build_calibration_result,
    case_outcome,
    derived_parameter_sets,
    evaluate_parameter_set,
    expand_outcome_matrix,
    leave_one_out,
    load_target_population,
    summarize_sensitivity,
)
from geometry.consensus_calibration_population import CRYPTO_LINEAR_PERPETUAL
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
RESULT = json.loads((GOLD / "calibration_result_v1.json").read_text(encoding="utf-8"))
CASES, PINNED, CLASSIFICATION = load_target_population()
IDS = sorted(c["case_id"] for c in CASES)
OUTCOMES = expand_outcome_matrix(RESULT["outcome_matrix"])
CHEAP = ("BILLUSDT-1m-src1789759080000", "GOATUSDT-1m-src1789850640000",
         "ENSUSDT-1m-src1789759320000")
# Semantic hashes of every pre-existing Gold manifest/fixture/metadata at base 3e7b453.
EXISTING_SEMANTIC_SHA256 = "567e97521346acdc641891ae71819bd1db4568b451194546f768820f5efb4f3e"
FACT_FIELDS = ("selection_status", "terminal_width_trend", "candidate_count",
               "admissible_count", "selected_pair_identity",
               "terminal_compression_ratio", "realized_contraction_ratio")
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


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


SETS, SWEEP_LABELS, INVALID_LABELS = derived_parameter_sets(RESULT["active_parameters"])


def _rebuild(cases, outcomes):
    determinism = {k: v["mismatches"] for k, v in RESULT["determinism_future_rows"].items()}
    rows, active = summarize_sensitivity(outcomes, [c["case_id"] for c in cases])
    record = build_calibration_result(
        cases, CLASSIFICATION, outcomes, sensitivity_rows=rows, active=active,
        sweep_labels=SWEEP_LABELS, invalid_labels=INVALID_LABELS, parameter_sets=SETS,
        determinism=determinism, performance=RESULT["performance"])
    return json.loads(_dumps(record))


def _without_extras(record):
    return {k: v for k, v in record.items()
            if k not in ("baseline_table", "outcome_matrix")}


class BaselineAndPopulationTests(unittest.TestCase):
    def test_baseline_matches_pinned_facts(self):                          # A
        self.assertEqual(len(RESULT["baseline_table"]), 16)
        for row in RESULT["baseline_table"]:
            self.assertTrue(row["matches_pinned_facts"], row["case_id"])
            for field in FACT_FIELDS:
                self.assertEqual(OUTCOMES[row["case_id"]]["BASELINE"][field],
                                 PINNED[row["case_id"]][field])
            self.assertEqual(row["production_detected"],
                             PINNED[row["case_id"]]["production_detected"])
        by_id = {c["case_id"]: c for c in CASES}
        for case_id in CHEAP:
            outcome = case_outcome(by_id[case_id], _load_frame(by_id[case_id]),
                                   dict(DEFAULT_SHADOW_REPORT_PARAMETERS))
            self.assertEqual(outcome, OUTCOMES[case_id]["BASELINE"])

    def test_population_is_geo_u1_pop_1(self):                              # B
        self.assertEqual(RESULT["population_policy"], "GEO-U1-POP-1")
        self.assertTrue(RESULT["population_matches_policy"])
        eligible = sorted(k for k, v in CLASSIFICATION.items() if v["calibration_eligible"])
        self.assertEqual(RESULT["case_ids"], eligible)
        self.assertEqual(IDS, eligible)
        self.assertEqual(len(IDS), 16)
        self.assertEqual(sorted(RESULT["outcome_matrix"]["cases"]), IDS)

    def test_no_tradfi_case_enters_calibration(self):                       # C
        self.assertNotIn("MCDUSDT-5m-src1790004300000", RESULT["case_ids"])
        for case_id in RESULT["case_ids"]:
            self.assertEqual(CLASSIFICATION[case_id]["instrument_class"],
                             CRYPTO_LINEAR_PERPETUAL)


class SensitivityAndSweepTests(unittest.TestCase):
    def test_sensitivity_table_deterministic(self):                         # D
        rows, active = summarize_sensitivity(OUTCOMES, IDS)
        self.assertEqual(json.loads(_dumps(rows)), RESULT["sensitivity_summary"])
        self.assertEqual(active, RESULT["active_parameters"])
        self.assertEqual(len(rows), 17)
        by_id = {c["case_id"]: c for c in CASES}
        sets = calibration.sensitivity_parameter_sets()
        self.assertEqual(len(sets), 35)
        computed, _ = calibration.compute_outcomes(
            [by_id[CHEAP[0]], by_id[CHEAP[1]]], sets, processes=1)
        for case_id, rows_by_label in computed.items():
            for label, outcome in rows_by_label.items():
                self.assertEqual(outcome, OUTCOMES[case_id][label], (case_id, label))

    def test_sweep_and_result_deterministic(self):                          # E
        self.assertEqual(RESULT["outcome_matrix"]["labels"],
                         [l for l, _ in calibration.sensitivity_parameter_sets()]
                         + SWEEP_LABELS)
        self.assertEqual(RESULT["tested_parameter_set_count"], len(SWEEP_LABELS))
        self.assertEqual(RESULT["invalid_grid_combinations"]["count"], len(INVALID_LABELS))
        self.assertEqual(_rebuild(CASES, OUTCOMES), _without_extras(RESULT))

    def test_case_order_does_not_change_result(self):                       # F
        reordered = {k: OUTCOMES[k] for k in reversed(IDS)}
        self.assertEqual(_rebuild(list(reversed(CASES)), reordered),
                         _without_extras(RESULT))

    def test_surviving_sets_keep_every_qualifying_case(self):               # G, H
        base = {c: OUTCOMES[c]["BASELINE"] for c in IDS}
        roles = {c: calibration.evidence_class(base[c]) for c in IDS}
        self.assertEqual(sum(r == "PERSISTENT_COMPRESSION" for r in roles.values()), 3)
        self.assertEqual(sum(r == "EXPANSION" for r in roles.values()), 2)
        columns = RESULT["sweep_table"]["columns"]
        for row in RESULT["sweep_table"]["rows"]:
            record = dict(zip(columns, row))
            if record["gates_passed"]:
                self.assertEqual(record["compression_retained"], 3, record["label"])
                self.assertEqual(record["expansion_retained"], 2, record["label"])
        for label, record in RESULT["gate_passing_evaluations"].items():
            cand = {c: OUTCOMES[c][label] for c in IDS}
            self.assertEqual(evaluate_parameter_set(base, cand, IDS, SETS[label])
                             ["class_changes"], record["class_changes"])
        lost = dict(base)
        victim = next(c for c in IDS if roles[c] == "PERSISTENT_COMPRESSION")
        lost[victim] = dict(base[victim], terminal_width_trend="NO_PERSISTENT_WIDTH_TREND")
        verdict = evaluate_parameter_set(base, lost, IDS, DEFAULT_SHADOW_REPORT_PARAMETERS)
        self.assertFalse(verdict["gates_passed"])
        self.assertIn("COMPRESSION_CASE_LOST", verdict["gate_failures"][0])

    def test_negative_controls_never_silently_selected(self):               # I
        base = {c: OUTCOMES[c]["BASELINE"] for c in IDS}
        negatives = [c for c in IDS if base[c]["selection_status"] == NO_ADMISSIBLE]
        self.assertEqual(len(negatives), 2)
        for label in RESULT["gate_passing_sets"]:
            for case_id in negatives:
                self.assertNotEqual(OUTCOMES[case_id][label]["selection_status"],
                                    "SELECTED", (label, case_id))
        for row in RESULT["sensitivity_summary"]:
            for tag in ("low_effect", "high_effect"):
                admitted = [c for c in row[tag]["newly_selected"] if c in negatives]
                self.assertEqual(row[tag]["negative_controls_admitted"], admitted)
        flipped = dict(base)
        flipped[negatives[0]] = dict(base[negatives[0]], selection_status="SELECTED")
        verdict = evaluate_parameter_set(base, flipped, IDS, DEFAULT_SHADOW_REPORT_PARAMETERS)
        self.assertFalse(verdict["gates_passed"])

    def test_leave_one_out_deterministic(self):                             # J
        base = {c: OUTCOMES[c]["BASELINE"] for c in IDS}
        summary = RESULT["leave_one_out_summary"]
        for label in RESULT["gate_passing_sets"]:
            cand = {c: OUTCOMES[c][label] for c in IDS}
            params = SETS[label]
            first = leave_one_out(base, cand, IDS, params)
            self.assertEqual(first, leave_one_out(base, cand, list(reversed(IDS)), params))
            if first["robustness"] == "ROBUST":
                self.assertIn(label, summary["robust"])
            else:
                self.assertEqual(summary["fragile"][label],
                                 first["conclusion_flips_when_removed"])


class InvarianceTests(unittest.TestCase):
    def test_defaults_unchanged(self):                                       # K
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, DEFAULTS_AT_BASE)
        self.assertEqual(RESULT["baseline_parameters"], DEFAULTS_AT_BASE)

    def test_existing_fixtures_manifests_metadata_unchanged(self):           # L
        names = ["manifest_v1.json", "source_time_manifest_v1.json",
                 "source_time_manifest_v2.json", "source_time_manifest_v3.json"]
        paths = [GOLD / n for n in names] + [GOLD / "instrument_metadata_v1.json",
                                             GOLD / "instrument_metadata_v2.json"]
        for name in names:
            paths += [ROOT / c["fixture_ref"] for c in load_manifest(GOLD / name)["cases"]]

        def semantic(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

        joined = "".join(semantic(p) for p in paths)
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(),
                         EXISTING_SEMANTIC_SHA256)

    def test_no_production_module_imports_calibration(self):                 # M
        pattern = re.compile(r"consensus_calibration(?!_population)")
        offenders = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if (rel.startswith(("tests/", ".git/", "runtime/", ".venv/", "venv/"))
                    or rel == "geometry/consensus_calibration.py"):
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_production_cutover_never_authorized(self):                     # N
        self.assertIs(RESULT["production_cutover_authorized"], False)
        self.assertIs(calibration.PRODUCTION_CUTOVER_AUTHORIZED, False)
        self.assertIn(RESULT["recommended_action"], (
            "KEEP_BASELINE", "CANDIDATE_PRESET_FOR_SHADOW_VALIDATION",
            "MORE_EVIDENCE_REQUIRED"))
        self.assertIsNone(RESULT["objective"]["scalar_score"])

    def test_no_screenshot_derived_numeric_oracle(self):                    # O
        source = open(calibration.__file__, encoding="utf-8").read().lower()
        for forbidden in ("screenshot", ".png", "visual", "image"):
            self.assertNotIn(forbidden, source)
        for case in CASES:
            self.assertIn(case["evidence_class"], ("READY", "EXACT_SOURCE_TIME"))
            self.assertTrue(case["fixture_ref"].endswith(".json"))


if __name__ == "__main__":
    unittest.main()
