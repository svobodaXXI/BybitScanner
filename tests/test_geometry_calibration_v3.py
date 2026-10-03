"""GEO-U1 H5: exact, shadow-only calibration on the 27-case Gold population.

Regenerate once: python -m tests.test_geometry_calibration_v3 --write
The H0 objective, gates, domain, preference, concentration and LOO stay in
geometry.consensus_calibration; H4-B freezes min_alternating_touches=3.
"""

import hashlib
import json
import time
import unittest

import geometry.consensus_calibration as calibration
from geometry.consensus_calibration import (
    DEFAULT_SHADOW_REPORT_PARAMETERS, MAX_ACTIVE_PARAMETERS, baseline_table,
    build_calibration_result, compact_outcome_matrix, compute_outcomes,
    derived_parameter_sets, evaluate_parameter_set, expand_outcome_matrix,
    leave_one_out, parameter_key, preferred_over_baseline,
    sensitivity_parameter_sets, summarize_sensitivity, verify_exact_future_invariance,
)
from geometry.consensus_calibration_population import POLICY_V1, classify_cases
from geometry.consensus_evidence_readiness import exact_source_time_case_problems
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
RESULT_PATH = GOLD / "calibration_result_v3.json"
MANIFESTS = ("manifest_v1.json",) + tuple(f"source_time_manifest_v{i}.json" for i in range(1, 7))
METADATA = tuple(f"instrument_metadata_v{i}.json" for i in range(1, 6))
HISTORICAL = MANIFESTS + METADATA + ("calibration_result_v1.json", "calibration_result_v2.json", "perf_parity_v1.json")
HISTORICAL_SHA256 = "0d2ab1484625bde598bd1351153a55e2f13923f2bddddeb26fe1c86609b49f5e"
RESULT_SHA256 = "2145b183743dfa7419ac34f98fa3bacb29508460da483e70225af241d5c71e8a"


def canonical(value):
    return json.loads(json.dumps(value, sort_keys=True, allow_nan=False))


def historical_digest():
    return hashlib.sha256("".join(hashlib.sha256((GOLD / name).read_bytes()).hexdigest()
                                  for name in HISTORICAL).encode()).hexdigest()


def load_population_v3():
    manifests = [load_manifest(GOLD / name) for name in MANIFESTS]
    metadata = [json.loads((GOLD / name).read_text(encoding="utf-8")) for name in METADATA]
    all_cases = [c for manifest in manifests for c in manifest["cases"]]
    ids = [c["case_id"] for c in all_cases]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate Gold case ID")
    instruments = {k: v for meta in metadata for k, v in meta["instruments"].items()}
    classification = classify_cases(sum((m["case_instruments"] for m in metadata), []),
                                    instruments)
    if set(classification) != set(ids):
        raise ValueError("metadata/manifest population mismatch")
    cases = sorted((c for c in all_cases if classification[c["case_id"]]["calibration_eligible"]),
                   key=lambda c: c["case_id"])
    facts = (manifests[4]["observed_slice_d_case_facts"]
             + manifests[5]["observed_slice_d_case_facts"]
             + manifests[6]["observed_slice_d_case_facts"])
    if len({f["case_id"] for f in facts}) != len(facts):
        raise ValueError("duplicate pinned facts")
    pinned = {f["case_id"]: f for f in facts if classification[f["case_id"]]["calibration_eligible"]}
    if set(pinned) != {c["case_id"] for c in cases}:
        raise ValueError("pinned facts are not exactly the eligible population")
    historical_ids = set(json.loads((GOLD / "calibration_result_v2.json").read_text(encoding="utf-8"))["case_ids"])
    added = {c["case_id"] for m in manifests[5:] for c in m["cases"]}
    if len(cases) != 27 or len(historical_ids) != 17 or len(added) != 10 or historical_ids & added:
        raise ValueError("H5 population must be 17 historical + 6 H3 + 4 H4-A")
    if set(pinned) != historical_ids | added:
        raise ValueError("H5 population membership differs from exact evidence")
    return cases, pinned, classification


def verify_fixtures(cases):
    counts = {"READY": 0, "EXACT_SOURCE_TIME": 0}
    for case in cases:
        payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
        frame = _load_frame(case)
        if frame.empty or len(frame) != case["as_of_index"] + 1:
            raise ValueError(f"missing decision-time candles: {case['case_id']}")
        kind = case["evidence_class"]
        if kind not in counts:
            raise ValueError(f"unexpected evidence class: {case['case_id']}")
        counts[kind] += 1
        if kind == "EXACT_SOURCE_TIME":
            problems = exact_source_time_case_problems(case, payload)
            if problems or len(frame) != 199 or case["as_of_index"] != 198:
                raise ValueError(f"invalid exact source-time fixture: {case['case_id']} {problems}")
            provenance = payload["provenance"]
            source = provenance["scanner_record"]["scanner_source_candle_time_ms"]
            if provenance["excluded_forming_candle_open_ms"] != source:
                raise ValueError(f"forming candle included: {case['case_id']}")
    if counts != {"READY": 5, "EXACT_SOURCE_TIME": 22}:
        raise ValueError(f"unexpected evidence distribution: {counts}")
    return counts


def enrich_record(result, pinned):
    ids = result["case_ids"]
    result["h5"].update({
        "baseline_future_row_mismatches": [],
        "baseline_class_counts": dict(sorted(result["baseline_evaluation"]["selected_trend_counts"].items())),
        "baseline_no_admissible_count": result["baseline_evaluation"]["no_admissible_retained"],
        "production_detected_count": sum(bool(pinned[c]["production_detected"]) for c in ids),
        "grid_theoretical_combinations_if_uncapped": 3 ** len(result["active_parameters"]),
        "grid_generated_combinations": result["tested_parameter_set_count"]
                                        + result["invalid_grid_combinations"]["count"],
    })
    result["performance"]["phase_wall_seconds"].setdefault("leave_one_out_s", 0.0)
    return result


def generate(processes=16, log=print):
    started = time.perf_counter()
    if historical_digest() != HISTORICAL_SHA256:
        raise RuntimeError("historical Gold/calibration artifacts changed")
    cases, pinned, classification = load_population_v3()
    evidence_counts = verify_fixtures(cases)
    ids = [c["case_id"] for c in cases]
    phase = {}
    t = time.perf_counter()
    outcomes, timings = compute_outcomes(cases, [("BASELINE", dict(DEFAULT_SHADOW_REPORT_PARAMETERS))], processes)
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
    rows, active = summarize_sensitivity(outcomes, ids)
    phase["sensitivity_s"] = round(time.perf_counter() - t, 1)
    log(f"active={active}")

    t = time.perf_counter()
    sets = dict(sensitivity_sets)
    sweep_labels, invalid = [], []
    if len(active) <= MAX_ACTIVE_PARAMETERS:
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
    phase["leave_one_out_s"] = 0.0 if not sweep_labels else None
    labels = [label for label, _ in sensitivity_sets] + [label for label in sweep_labels
                                                          if label not in dict(sensitivity_sets)]
    slowest = max(((c, l, s) for c in ids for l, s in timings[c].items()), key=lambda row: row[2])
    performance = {
        "parameter_sets_tested": len(labels),
        "exact_case_runs": sum(timings[c].get(l, 0) > 0 for c in ids for l in labels),
        "memo_alias_case_runs": sum(timings[c].get(l, 0) == 0 for c in ids for l in labels),
        "phase_wall_seconds": phase,
        "this_invocation_elapsed_seconds": round(time.perf_counter() - started, 1),
        "exact_case_run_seconds_sum": round(sum(timings[c].get(l, 0) for c in ids for l in labels), 1),
        "slowest_case_run": {"case_id": slowest[0], "set": slowest[1], "seconds": round(slowest[2], 2)},
        "processes": processes,
        "exact_path": "merged GEO-U1-PERF with H0 per-case ExactMemo",
    }
    t = time.perf_counter()
    result = build_calibration_result(
        cases, classification, outcomes, sensitivity_rows=rows, active=active,
        sweep_labels=sweep_labels, invalid_labels=invalid, parameter_sets=sets,
        determinism=determinism, performance=performance)
    phase["leave_one_out_s"] = round(time.perf_counter() - t, 1) if sweep_labels else 0.0
    result = canonical(result)
    result["version"] = "v3"
    result["based_on"] = "GEO-U1-POP-1; Gold manifests v1-v6; metadata v1-v5; 27 eligible saved cases"
    result["methodology"] = "H0 locked method with H4-B min_alternating_touches=3 structural freeze"
    result["supersedes"] = "v2 as current shadow calibration; v1/v2 remain immutable historical records"
    result["h5"] = {"historical_cases": 17, "h3_cases": 6, "h4a_cases": 4,
                    "evidence_counts": evidence_counts, "historical_artifact_sha256": HISTORICAL_SHA256}
    result["baseline_table"] = canonical(table)
    result["outcome_matrix"] = compact_outcome_matrix(outcomes, labels)
    return canonical(enrich_record(result, pinned))


RESULT = json.loads(RESULT_PATH.read_text(encoding="utf-8")) if RESULT_PATH.exists() else None


class PopulationPreflight(unittest.TestCase):
    def test_exact_population_and_immutable_history(self):
        cases, pinned, classification = load_population_v3()
        self.assertEqual(len(cases), 27)
        self.assertEqual(set(pinned), {c["case_id"] for c in cases})
        self.assertEqual(set(classification), {c["case_id"] for c in cases} | {
            c["case_id"] for m in MANIFESTS for c in load_manifest(GOLD / m)["cases"]
            if not classification[c["case_id"]]["calibration_eligible"]})
        self.assertEqual(verify_fixtures(cases), {"READY": 5, "EXACT_SOURCE_TIME": 22})
        self.assertEqual(historical_digest(), HISTORICAL_SHA256)
        self.assertEqual(POLICY_V1.policy_version, "GEO-U1-POP-1")

    def test_structural_freeze_and_domain(self):
        self.assertEqual(calibration.FROZEN_STRUCTURAL_PARAMETERS["min_alternating_touches"]["value"], 3)
        self.assertNotIn("min_alternating_touches", [row[0] for row in calibration.CALIBRATABLE_PARAMETER_DOMAIN])
        self.assertEqual(len(calibration.CALIBRATABLE_PARAMETER_DOMAIN), 16)
        for _, params in sensitivity_parameter_sets():
            self.assertEqual(params["min_alternating_touches"], 3)


@unittest.skipIf(RESULT is None, "calibration_result_v3.json not generated")
class CalibrationV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.pinned, cls.classification = load_population_v3()
        cls.ids = [c["case_id"] for c in cls.cases]
        cls.outcomes = expand_outcome_matrix(RESULT["outcome_matrix"])

    def test_baseline_and_source_time(self):
        self.assertEqual(RESULT["case_ids"], self.ids)
        self.assertEqual(len(RESULT["baseline_table"]), 27)
        self.assertTrue(all(row["matches_pinned_facts"] for row in RESULT["baseline_table"]))
        self.assertEqual(RESULT["h5"]["evidence_counts"], verify_fixtures(self.cases))
        self.assertEqual(RESULT["h5"]["historical_artifact_sha256"], historical_digest())
        self.assertEqual(RESULT["population_policy"], "GEO-U1-POP-1")
        self.assertTrue(RESULT["population_matches_policy"])
        self.assertEqual(RESULT["h5"]["baseline_future_row_mismatches"], [])
        self.assertEqual(RESULT["h5"]["production_detected_count"],
                         sum(bool(self.pinned[c]["production_detected"]) for c in self.ids))

    def test_sensitivity_grid_and_freeze(self):
        rows, active = summarize_sensitivity(self.outcomes, self.ids)
        self.assertEqual(canonical(rows), RESULT["sensitivity_summary"])
        self.assertEqual(active, RESULT["active_parameters"])
        self.assertEqual(active, summarize_sensitivity(self.outcomes, list(reversed(self.ids)))[1])
        self.assertNotIn("min_alternating_touches", active)
        self.assertEqual(len(active), 8)
        self.assertGreater(len(active), MAX_ACTIVE_PARAMETERS)
        self.assertEqual(RESULT["recommended_action"], "MORE_EVIDENCE_REQUIRED")
        self.assertEqual(RESULT["tested_parameter_set_count"], 0)
        self.assertEqual(RESULT["candidate_presets"], [])
        self.assertEqual(RESULT["proposed_shadow_preset"], None)
        historical = json.loads((GOLD / "calibration_result_v2.json").read_text(encoding="utf-8"))
        old = {r["parameter"]: r["sensitivity"] for r in historical["sensitivity_summary"]}
        changed = {r["parameter"]: (old[r["parameter"]], r["sensitivity"])
                   for r in rows if old[r["parameter"]] != r["sensitivity"]}
        self.assertEqual(changed, {
            "minimum_swing_width_fraction": ("INSENSITIVE", "MATERIAL"),
            "max_support_gap_fraction": ("IDENTITY_ONLY", "MATERIAL"),
        })
        sets, labels, invalid = derived_parameter_sets(active)
        self.assertEqual(len(labels), RESULT["tested_parameter_set_count"])
        self.assertEqual(len(invalid), RESULT["invalid_grid_combinations"]["count"])
        self.assertEqual(RESULT["h5"]["grid_theoretical_combinations_if_uncapped"], 3 ** len(active))
        self.assertEqual(RESULT["h5"]["grid_generated_combinations"], len(labels) + len(invalid))
        self.assertEqual(RESULT["outcome_matrix"]["labels"], [l for l, _ in sensitivity_parameter_sets()] + labels)
        for params in sets.values():
            self.assertEqual(params["min_alternating_touches"], 3)

    def test_rebuild_case_order_loo_and_cutover(self):
        rows, active = summarize_sensitivity(self.outcomes, self.ids)
        sets, labels, invalid = derived_parameter_sets(active)
        determinism = {k: v["mismatches"] for k, v in RESULT["determinism_future_rows"].items()}
        def rebuild(cases, outcomes):
            return canonical(build_calibration_result(
                cases, self.classification, outcomes, sensitivity_rows=rows, active=active,
                sweep_labels=labels, invalid_labels=invalid, parameter_sets=sets,
                determinism=determinism, performance=RESULT["performance"]))
        rebuilt = rebuild(self.cases, self.outcomes)
        self.assertEqual(rebuilt, rebuild(list(reversed(self.cases)),
                                          {k: self.outcomes[k] for k in reversed(self.ids)}))
        for key, value in rebuilt.items():
            self.assertEqual(value, RESULT[key], key)
        base = {c: self.outcomes[c]["BASELINE"] for c in self.ids}
        for label in RESULT["gate_passing_sets"]:
            candidate = {c: self.outcomes[c][label] for c in self.ids}
            self.assertEqual(leave_one_out(base, candidate, self.ids, sets[label]),
                             leave_one_out(base, candidate, list(reversed(self.ids)), sets[label]))
        self.assertFalse(RESULT["production_cutover_authorized"])
        self.assertFalse(calibration.PRODUCTION_CUTOVER_AUTHORIZED)

    def test_canonical_serialization(self):
        expected = json.dumps(RESULT, sort_keys=True, allow_nan=False, separators=(",", ":")) + "\n"
        self.assertEqual(RESULT_PATH.read_text(encoding="utf-8"), expected)
        self.assertEqual(hashlib.sha256(RESULT_PATH.read_bytes()).hexdigest(), RESULT_SHA256)


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
