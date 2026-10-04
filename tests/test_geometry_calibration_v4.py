"""GEO-U1 H27: v4 calibration gate on the 27-case Gold population (prepared).

v4 reuses the H5 population, fixture checks, H0 objective, gates, preference,
concentration, leave-one-out and future-row determinism unchanged. The only
method change is the H16/H25/H26 forward policy: sensitivity still reports all
16 calibratable dimensions, but ``forward_active_parameters`` removes the
diagnostic-only ones, so the grid spans exactly six dimensions.

Run only when separately authorized:
    python -m tests.test_geometry_calibration_v4 --write --processes 16
"""

import hashlib
import json
import time
import unittest

import geometry.consensus_calibration as calibration
from geometry.consensus_calibration import (
    DEFAULT_SHADOW_REPORT_PARAMETERS, DIAGNOSTIC_ONLY_PARAMETERS, MAX_ACTIVE_PARAMETERS,
    baseline_table, build_calibration_result, compact_outcome_matrix, compute_outcomes,
    derived_parameter_sets, evaluate_parameter_set, expand_outcome_matrix,
    forward_active_parameters, leave_one_out, parameter_key, preferred_over_baseline,
    sensitivity_parameter_sets, summarize_sensitivity, verify_exact_future_invariance,
)
from tests.test_geometry_calibration_v3 import (
    GOLD, HISTORICAL as HISTORICAL_V3, canonical, load_population_v3, verify_fixtures,
)

RESULT_PATH = GOLD / "calibration_result_v4.json"
HISTORICAL = HISTORICAL_V3 + ("calibration_result_v3.json",)
HISTORICAL_SHA256 = "17e74751b6bfbefcc5fa6ef79558929b10a4c8d03a595ab06f738236d9c0f2fb"
FORWARD_ACTIVE = [
    "minimum_side_touch_clusters", "min_shared_support_coverage",
    "terminal_window_bars", "terminal_segments",
    "compression_max_ratio", "expansion_min_ratio",
]
# Record shape: every v3 top-level key except the H5 block, plus the v4 block.
V4_BLOCK_KEYS = (
    "historical_cases", "h3_cases", "h4a_cases", "evidence_counts",
    "historical_artifact_sha256", "material_parameters",
    "diagnostic_only_parameters", "forward_active_parameters",
    "baseline_future_row_mismatches", "baseline_class_counts",
    "baseline_no_admissible_count", "production_detected_count",
    "grid_theoretical_combinations", "grid_generated_combinations",
)


def historical_digest():
    return hashlib.sha256("".join(hashlib.sha256((GOLD / name).read_bytes()).hexdigest()
                                  for name in HISTORICAL).encode()).hexdigest()


def annotate_v4(result, *, pinned, material, evidence_counts):
    """Attach the v4 identity and block to a build_calibration_result record."""
    result = canonical(result)
    ids = result["case_ids"]
    result["version"] = "v4"
    result["based_on"] = ("GEO-U1-POP-1; Gold manifests v1-v6; metadata v1-v5; "
                          "27 eligible saved cases (same population as v3)")
    result["methodology"] = ("H0 locked method; H4-B min_alternating_touches=3 structural "
                             "freeze; H16/H25/H26 diagnostic-only exclusions")
    result["supersedes"] = ("v3 as current shadow calibration; v1/v2/v3 remain immutable "
                            "historical records")
    result["v4"] = {
        "historical_cases": 17, "h3_cases": 6, "h4a_cases": 4,
        "evidence_counts": evidence_counts,
        "historical_artifact_sha256": HISTORICAL_SHA256,
        "material_parameters": list(material),
        "diagnostic_only_parameters": {
            name: dict(policy) for name, policy in DIAGNOSTIC_ONLY_PARAMETERS.items()},
        "forward_active_parameters": result["active_parameters"],
        "baseline_future_row_mismatches": [],
        "baseline_class_counts": dict(sorted(
            result["baseline_evaluation"]["selected_trend_counts"].items())),
        "baseline_no_admissible_count": result["baseline_evaluation"]["no_admissible_retained"],
        "production_detected_count": sum(bool(pinned[c]["production_detected"]) for c in ids),
        "grid_theoretical_combinations": 3 ** len(result["active_parameters"]),
        "grid_generated_combinations": result["tested_parameter_set_count"]
                                       + result["invalid_grid_combinations"]["count"],
    }
    return canonical(result)


def generate(processes=16, log=print):
    """Full exact v4 run (expensive). Never called by the unit tests."""
    started = time.perf_counter()
    if historical_digest() != HISTORICAL_SHA256:
        raise RuntimeError("historical Gold/calibration artifacts changed")
    cases, pinned, classification = load_population_v3()
    evidence_counts = verify_fixtures(cases)
    ids = [c["case_id"] for c in cases]
    phase = {}
    t = time.perf_counter()
    outcomes, timings = compute_outcomes(
        cases, [("BASELINE", dict(DEFAULT_SHADOW_REPORT_PARAMETERS))], processes)
    table = baseline_table(cases, pinned, outcomes)
    if not all(row["matches_pinned_facts"] for row in table):
        raise RuntimeError("BASELINE_MISMATCH: calibration stopped")
    phase["baseline_s"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    future = verify_exact_future_invariance(cases, dict(DEFAULT_SHADOW_REPORT_PARAMETERS),
                                             {c: outcomes[c]["BASELINE"] for c in ids}, processes)
    if future:
        raise RuntimeError(f"BASELINE_FUTURE_ROW_MISMATCH: {future}")
    phase["baseline_future_row_check_s"] = round(time.perf_counter() - t, 1)
    log(f"baseline exact {len(ids)}/{len(ids)} and future rows checked")

    t = time.perf_counter()
    sensitivity_sets = sensitivity_parameter_sets()
    extra, extra_times = compute_outcomes(cases, sensitivity_sets[1:], processes)
    for cid in ids:
        outcomes[cid].update(extra[cid])
        timings[cid].update(extra_times[cid])
    rows, material = summarize_sensitivity(outcomes, ids)
    active = forward_active_parameters(material)
    phase["sensitivity_s"] = round(time.perf_counter() - t, 1)
    log(f"material={material} active={active}")
    if active != FORWARD_ACTIVE:
        raise RuntimeError(f"FORWARD_ACTIVE_SET_CHANGED: {active}")

    t = time.perf_counter()
    sets = dict(sensitivity_sets)
    all_sets, sweep_labels, invalid = derived_parameter_sets(active)
    known = {parameter_key(p): label for label, p in sets.items()}
    new = [(label, all_sets[label]) for label in sweep_labels
           if parameter_key(all_sets[label]) not in known]
    if new:
        grid, grid_times = compute_outcomes(cases, new, processes)
        for cid in ids:
            outcomes[cid].update(grid[cid])
            timings[cid].update(grid_times[cid])
    for label in sweep_labels:
        sets[label] = all_sets[label]
        alias = known.get(parameter_key(all_sets[label]))
        if alias is not None:
            for cid in ids:
                outcomes[cid][label] = outcomes[cid][alias]
                timings[cid][label] = 0.0
    phase["sweep_s"] = round(time.perf_counter() - t, 1)
    log(f"sweep={len(sweep_labels)}, invalid={len(invalid)}")

    t = time.perf_counter()
    base = {c: outcomes[c]["BASELINE"] for c in ids}
    base_eval = evaluate_parameter_set(base, base, ids, DEFAULT_SHADOW_REPORT_PARAMETERS)
    determinism = {}
    for label in sweep_labels:
        cand = {c: outcomes[c][label] for c in ids}
        ev = evaluate_parameter_set(base, cand, ids, sets[label])
        if (preferred_over_baseline(ev, base_eval, sets[label])
                and leave_one_out(base, cand, ids, sets[label])["robustness"] == "ROBUST"):
            determinism[label] = verify_exact_future_invariance(cases, sets[label], cand, processes)
    phase["determinism_check_s"] = round(time.perf_counter() - t, 1)
    labels = [label for label, _ in sensitivity_sets] + [
        label for label in sweep_labels if label not in dict(sensitivity_sets)]
    slowest = max(((c, l, s) for c in ids for l, s in timings[c].items()), key=lambda row: row[2])
    performance = {
        "parameter_sets_tested": len(labels),
        "exact_case_runs": sum(timings[c].get(l, 0) > 0 for c in ids for l in labels),
        "memo_alias_case_runs": sum(timings[c].get(l, 0) == 0 for c in ids for l in labels),
        "phase_wall_seconds": phase,
        "this_invocation_elapsed_seconds": round(time.perf_counter() - started, 1),
        "exact_case_run_seconds_sum": round(
            sum(timings[c].get(l, 0) for c in ids for l in labels), 1),
        "slowest_case_run": {"case_id": slowest[0], "set": slowest[1],
                             "seconds": round(slowest[2], 2)},
        "processes": processes,
        "exact_path": "merged GEO-U1-PERF with H0 per-case ExactMemo",
    }
    t = time.perf_counter()
    result = build_calibration_result(
        cases, classification, outcomes, sensitivity_rows=rows, active=active,
        sweep_labels=sweep_labels, invalid_labels=invalid, parameter_sets=sets,
        determinism=determinism, performance=performance)
    phase["leave_one_out_s"] = round(time.perf_counter() - t, 1)
    result["baseline_table"] = canonical(table)
    result["outcome_matrix"] = compact_outcome_matrix(outcomes, labels)
    return annotate_v4(result, pinned=pinned, material=material,
                       evidence_counts=evidence_counts)


class V4GatePreparationTests(unittest.TestCase):
    """Label generation and v3 outcomes only: no grid, LOO or population run."""

    @classmethod
    def setUpClass(cls):
        cls.v3 = json.loads((GOLD / "calibration_result_v3.json").read_text(encoding="utf-8"))
        cls.outcomes = expand_outcome_matrix(cls.v3["outcome_matrix"])
        cls.rows, cls.material = summarize_sensitivity(cls.outcomes, cls.v3["case_ids"])

    def test_history_is_immutable_and_v4_not_generated(self):
        self.assertEqual(historical_digest(), HISTORICAL_SHA256)
        self.assertFalse(RESULT_PATH.exists())

    def test_forward_active_set_is_exactly_six(self):
        self.assertEqual(self.material, self.v3["active_parameters"])
        self.assertEqual(len(self.material), 8)
        active = forward_active_parameters(self.material)
        self.assertEqual(active, FORWARD_ACTIVE)
        self.assertEqual(len(active), MAX_ACTIVE_PARAMETERS)

    def test_grid_has_729_raw_labels_and_deterministic_validity(self):
        first = derived_parameter_sets(FORWARD_ACTIVE)
        self.assertEqual(first, derived_parameter_sets(FORWARD_ACTIVE))
        sets, grid, invalid = first
        self.assertEqual(len(grid) + len(invalid), 3 ** 6)
        # Only terminal 24/5 and 36/5 bars fail divisibility: 2 of 9 window pairs.
        self.assertEqual((len(grid), len(invalid)), (567, 162))
        self.assertTrue(all(label.startswith("GRID:") for label in grid + invalid))
        for label in grid:
            self.assertEqual(calibration.validate_parameter_set(sets[label]), [])
        self.assertEqual(len(set(grid) | set(invalid)), 729)

    def test_diagnostic_only_parameters_never_enter_grid(self):
        sets, grid, invalid = derived_parameter_sets(FORWARD_ACTIVE)
        for label in grid + invalid:
            varied = {part.split("=")[0] for part in label[len("GRID:"):].split(",")}
            self.assertEqual(varied, set(FORWARD_ACTIVE))
        for label in grid:
            for name in DIAGNOSTIC_ONLY_PARAMETERS:
                self.assertEqual(sets[label][name], DEFAULT_SHADOW_REPORT_PARAMETERS[name])
            self.assertEqual(sets[label]["min_alternating_touches"], 3)

    def test_pre_acceptance_record_shape_keeps_cutover_false(self):
        cases, pinned, classification = load_population_v3()
        record = annotate_v4(build_calibration_result(
            cases, classification, self.outcomes, sensitivity_rows=self.rows,
            active=forward_active_parameters(self.material), sweep_labels=[],
            invalid_labels=[], parameter_sets=dict(sensitivity_parameter_sets()),
            determinism={}, performance={}), pinned=pinned, material=self.material,
            evidence_counts={"READY": 5, "EXACT_SOURCE_TIME": 22})
        expected = (set(self.v3) - {"h5", "baseline_table", "outcome_matrix"}) | {"v4"}
        self.assertEqual(set(record), expected)
        self.assertEqual(tuple(sorted(record["v4"])), tuple(sorted(V4_BLOCK_KEYS)))
        self.assertEqual(record["version"], "v4")
        self.assertEqual(record["active_parameters"], FORWARD_ACTIVE)
        self.assertEqual(record["v4"]["material_parameters"], self.v3["active_parameters"])
        self.assertEqual(sorted(record["v4"]["diagnostic_only_parameters"]),
                         sorted(DIAGNOSTIC_ONLY_PARAMETERS))
        self.assertEqual(record["v4"]["grid_theoretical_combinations"], 729)
        self.assertFalse([r for r in record["reasons"]
                          if r.startswith(calibration.CALIBRATION_UNDERDETERMINED)])
        self.assertIs(record["production_cutover_authorized"], False)
        self.assertIsNone(record["proposed_shadow_preset"])


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--processes", type=int, default=16)
    args = parser.parse_args()
    if args.write:
        record = generate(args.processes, log=lambda message: print(message, flush=True))
        RESULT_PATH.write_text(json.dumps(record, sort_keys=True, allow_nan=False,
                                          separators=(",", ":")) + "\n", encoding="utf-8")
        print("DONE", record["recommended_action"], record["reasons"], flush=True)
    else:
        unittest.main()
