"""GEO-U1 Slice H2: H0 calibration rerun on the 17-case crypto population.

The methodology is the unchanged ``geometry/consensus_calibration.py`` (H0):
same objective, hard gates, preference order, LOW/CURRENT/HIGH domain,
active-parameter rule, concentration rule and leave-one-out. The only change
is the population: GEO-U1-POP-1 over Gold manifests v1-v4 (H1 added NXPCUSDT
5m). That module's ``load_target_population`` stays the historical 16-case v1
loader, so the 17-case population is loaded here and passed to the same
functions. The exact computation runs on the merged GEO-U1-PERF path.

Regenerate (expensive):  python -m tests.test_geometry_calibration_v2 --write
"""

import hashlib
import json
import re
import time
import unittest

import geometry.consensus_calibration as calibration
from geometry.consensus_calibration import (
    DEFAULT_SHADOW_REPORT_PARAMETERS,
    MAX_ACTIVE_PARAMETERS,
    NO_ADMISSIBLE,
    PERSISTENT_COMPRESSION,
    EXPANSION,
    baseline_table,
    build_calibration_result,
    compact_outcome_matrix,
    compute_outcomes,
    concentration_summary,
    derived_parameter_sets,
    evaluate_parameter_set,
    evidence_class,
    expand_outcome_matrix,
    leave_one_out,
    parameter_key,
    preferred_over_baseline,
    sensitivity_parameter_sets,
    summarize_sensitivity,
    verify_exact_future_invariance,
)
from geometry.consensus_calibration_population import (
    CRYPTO_LINEAR_PERPETUAL,
    POLICY_V1,
    classify_cases,
)
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
RESULT_PATH = GOLD / "calibration_result_v2.json"
NXPC = "NXPCUSDT-5m-src1789996800000"
MANIFESTS = ("manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
             "source_time_manifest_v3.json", "source_time_manifest_v4.json")
METADATA = ("instrument_metadata_v1.json", "instrument_metadata_v2.json",
            "instrument_metadata_v3.json")
CHEAP = ("BILLUSDT-1m-src1789759080000", "GOATUSDT-1m-src1789850640000", NXPC)
# Semantic hashes of every Gold manifest/fixture/metadata, calibration_result_v1
# and perf_parity_v1 at base c59840d.
GOLD_SEMANTIC_SHA256 = "a0a4bf72c39fbca59171dadbee91808c2d516de1cfa3f5167611d28b9903a1c0"
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


def load_population_v2():
    """(cases, pinned v4 facts, classification) for GEO-U1-POP-1 over v1-v4."""
    manifests = [load_manifest(GOLD / name) for name in MANIFESTS]
    metas = [json.loads((GOLD / name).read_text(encoding="utf-8")) for name in METADATA]
    classification = classify_cases(sum((m["case_instruments"] for m in metas), []),
                                    {k: v for m in metas for k, v in m["instruments"].items()})
    pinned = {f["case_id"]: f for f in manifests[-1]["observed_slice_d_case_facts"]}
    cases = sorted((c for m in manifests for c in m["cases"]
                    if classification[c["case_id"]]["calibration_eligible"]),
                   key=lambda c: c["case_id"])
    return cases, pinned, classification


def nxpc_removal_fold(base, outcomes, ids, labels, parameter_sets):
    """Explicit NXPC-removal fold for every gate-passing set (same functions)."""
    rest = [c for c in ids if c != NXPC]
    base_full = evaluate_parameter_set(base, base, ids, DEFAULT_SHADOW_REPORT_PARAMETERS)
    base_rest = evaluate_parameter_set(base, base, rest, DEFAULT_SHADOW_REPORT_PARAMETERS)
    rows = {}
    for label in labels:
        params = parameter_sets[label]
        cand = {c: outcomes[c][label] for c in ids}
        full = evaluate_parameter_set(base, cand, ids, params)
        fold = evaluate_parameter_set(base, cand, rest, params)
        rows[label] = {
            "nxpc_class": evidence_class(cand[NXPC]),
            "gates_passed_full": full["gates_passed"],
            "gates_passed_without_nxpc": fold["gates_passed"],
            "preferred_full": preferred_over_baseline(full, base_full, params),
            "preferred_without_nxpc": preferred_over_baseline(fold, base_rest, params),
        }
    return rows


def h0_v1_comparison(rows_v2):
    v1 = json.loads((GOLD / "calibration_result_v1.json").read_text(encoding="utf-8"))
    before = {r["parameter"]: r["sensitivity"] for r in v1["sensitivity_summary"]}
    after = {r["parameter"]: r["sensitivity"] for r in rows_v2}
    return {
        "v1_active_parameters": v1["active_parameters"],
        "v1_recommended_action": v1["recommended_action"],
        "status_changes": {p: [before[p], after[p]] for p in after if before[p] != after[p]},
        "sensitivity_v1": before,
    }


def h2_extras(cases, classification, outcomes, rows, active, sets, sweep_labels, gate_passing):
    ids = sorted(c["case_id"] for c in cases)
    base = {c: outcomes[c]["BASELINE"] for c in ids}
    by_tf = {}
    for case in cases:
        role = evidence_class(base[case["case_id"]])
        by_tf.setdefault(role, {}).setdefault(str(case["timeframe"]), 0)
        by_tf[role][str(case["timeframe"])] += 1
    return {
        "population_size": len(ids),
        "baseline_class_counts": dict(sorted({
            k: sum(evidence_class(base[c]) == k for c in ids)
            for k in {evidence_class(base[c]) for c in ids}}.items())),
        "baseline_class_by_timeframe": {k: dict(sorted(v.items())) for k, v in sorted(by_tf.items())},
        "h0_v1_comparison": h0_v1_comparison(rows),
        "nxpc_removal_fold": nxpc_removal_fold(base, outcomes, ids, gate_passing, sets),
    }


def generate(processes=16, cache_dir=None, log=print):
    """Historical H2 runner; unavailable once H4-B policy is active."""
    if "min_alternating_touches" in calibration.FROZEN_STRUCTURAL_PARAMETERS:
        raise RuntimeError("H2 calibration_result_v2.json is historical and immutable after H4-B")
    started = time.perf_counter()
    cases, pinned, classification = load_population_v2()
    ids = [c["case_id"] for c in cases]
    phase = {}
    t = time.perf_counter()
    outcomes, timings = compute_outcomes(
        cases, [("BASELINE", dict(DEFAULT_SHADOW_REPORT_PARAMETERS))], processes, cache_dir)
    table = baseline_table(cases, pinned, outcomes)
    if not all(r["matches_pinned_facts"] for r in table):
        raise RuntimeError("BASELINE_MISMATCH: calibration stopped")
    phase["baseline_s"] = round(time.perf_counter() - t, 1)
    t = time.perf_counter()
    future = verify_exact_future_invariance(
        cases, dict(DEFAULT_SHADOW_REPORT_PARAMETERS),
        {c: outcomes[c]["BASELINE"] for c in ids}, processes)
    if future:
        raise RuntimeError(f"BASELINE_FUTURE_ROW_MISMATCH: {future}")
    phase["baseline_future_row_check_s"] = round(time.perf_counter() - t, 1)
    log(f"baseline exact 17/17 + future rows in {time.perf_counter() - started:.0f}s")

    t = time.perf_counter()
    sens_sets = sensitivity_parameter_sets()
    more, more_t = compute_outcomes(cases, sens_sets[1:], processes, cache_dir)
    for cid in ids:
        outcomes[cid].update(more[cid])
        timings[cid].update(more_t[cid])
    rows, active = summarize_sensitivity(outcomes, ids)
    phase["sensitivity_s"] = round(time.perf_counter() - t, 1)
    log(f"active={active}")

    t = time.perf_counter()
    parameter_sets = dict(sens_sets)
    sweep_labels, invalid = [], []
    if len(active) <= MAX_ACTIVE_PARAMETERS:
        all_sets, sweep_labels, invalid = derived_parameter_sets(active)
        known = {parameter_key(p): l for l, p in parameter_sets.items()}
        new = [(l, all_sets[l]) for l in sweep_labels if parameter_key(all_sets[l]) not in known]
        if new:
            grid, grid_t = compute_outcomes(cases, new, processes, cache_dir)
            for cid in ids:
                outcomes[cid].update(grid[cid])
                timings[cid].update(grid_t[cid])
        for label in sweep_labels:
            parameter_sets[label] = all_sets[label]
            alias = known.get(parameter_key(all_sets[label]))
            if alias is not None:
                for cid in ids:
                    outcomes[cid][label] = outcomes[cid][alias]
                    timings[cid][label] = 0.0
    phase["sweep_s"] = round(time.perf_counter() - t, 1)
    log(f"sweep {len(sweep_labels)} sets at {time.perf_counter() - started:.0f}s")

    t = time.perf_counter()
    ids_sorted = sorted(ids)
    base = {c: outcomes[c]["BASELINE"] for c in ids_sorted}
    base_eval = evaluate_parameter_set(base, base, ids_sorted, DEFAULT_SHADOW_REPORT_PARAMETERS)
    determinism = {}
    for label in sweep_labels:
        cand = {c: outcomes[c][label] for c in ids_sorted}
        ev = evaluate_parameter_set(base, cand, ids_sorted, parameter_sets[label])
        if (preferred_over_baseline(ev, base_eval, parameter_sets[label])
                and leave_one_out(base, cand, ids_sorted,
                                  parameter_sets[label])["robustness"] == "ROBUST"):
            determinism[label] = verify_exact_future_invariance(
                cases, parameter_sets[label], cand, processes)
    phase["determinism_check_s"] = round(time.perf_counter() - t, 1)

    labels = [l for l, _ in sens_sets] + [l for l in sweep_labels if l not in dict(sens_sets)]
    slowest = max(((c, l, s) for c in ids for l, s in timings[c].items()), key=lambda x: x[2])
    performance = {
        "parameter_sets_tested": len(labels),
        "exact_case_runs": sum(1 for c in ids for l in labels if timings[c].get(l, 0.0) > 0.0),
        "memo_alias_case_runs": sum(1 for c in ids for l in labels if timings[c].get(l, 0.0) == 0.0),
        "phase_wall_seconds": phase,
        "this_invocation_elapsed_seconds": round(time.perf_counter() - started, 1),
        "exact_case_run_seconds_sum": round(sum(timings[c].get(l, 0.0)
                                                for c in ids for l in labels), 1),
        "per_set_case_seconds_by_matrix_label": [
            round(sum(timings[c].get(l, 0.0) for c in ids), 1) for l in labels],
        "per_case_seconds": {c: round(sum(timings[c].get(l, 0.0) for l in labels), 1)
                             for c in ids},
        "slowest_case_run": {"case_id": slowest[0], "set": slowest[1],
                             "seconds": round(slowest[2], 2)},
        "processes": processes,
        "exact_path": "merged GEO-U1-PERF (c59840d) with the H0 per-case ExactMemo",
    }
    result = build_calibration_result(
        cases, classification, outcomes, sensitivity_rows=rows, active=active,
        sweep_labels=sweep_labels, invalid_labels=invalid, parameter_sets=parameter_sets,
        determinism=determinism, performance=performance)
    result = json.loads(_dumps(result))
    result["version"] = "v2"
    result["based_on"] = ("GEO-U1-POP-1 over Gold manifests v1-v4 + instrument metadata "
                          "v1-v3 (17 crypto cases; H1 added NXPCUSDT 5m)")
    result["methodology"] = ("H0 unchanged: geometry/consensus_calibration.py objective, "
                             "gates, preference order, domain, active rule, concentration "
                             "rule and leave-one-out at c59840d")
    result["supersedes"] = ("calibration_result_v1.json for the current calibration state; "
                            "v1 remains the historical 16-case H0 record")
    result["h2"] = json.loads(_dumps(h2_extras(cases, classification, outcomes, rows, active,
                                                parameter_sets, sweep_labels,
                                                result["gate_passing_sets"])))
    result["baseline_table"] = json.loads(_dumps(table))
    result["outcome_matrix"] = compact_outcome_matrix(outcomes, labels)
    return json.loads(_dumps(result))


# --- tests --------------------------------------------------------------------

RESULT = (json.loads(RESULT_PATH.read_text(encoding="utf-8"))
          if RESULT_PATH.exists() else None)


@unittest.skipIf(RESULT is None, "calibration_result_v2.json not generated")
class CalibrationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases, cls.pinned, cls.classification = load_population_v2()
        cls.ids = sorted(c["case_id"] for c in cls.cases)
        cls.outcomes = expand_outcome_matrix(RESULT["outcome_matrix"])
        cls.sets = dict(sensitivity_parameter_sets())
        cls.sweep_labels, cls.invalid = [], []
        cls.base = {c: cls.outcomes[c]["BASELINE"] for c in cls.ids}

    def _rebuild(self, cases, outcomes):
        rows, active = summarize_sensitivity(outcomes, [c["case_id"] for c in cases])
        determinism = {k: v["mismatches"] for k, v in RESULT["determinism_future_rows"].items()}
        record = build_calibration_result(
            cases, self.classification, outcomes, sensitivity_rows=rows, active=active,
            sweep_labels=self.sweep_labels, invalid_labels=self.invalid,
            parameter_sets=self.sets, determinism=determinism,
            performance=RESULT["performance"])
        record = json.loads(_dumps(record))
        record["h2"] = json.loads(_dumps(h2_extras(
            cases, self.classification, outcomes, rows, active, self.sets,
            self.sweep_labels, record["gate_passing_sets"])))
        return record

    def _strip(self, record):
        skip = ("baseline_table", "outcome_matrix", "version", "based_on", "methodology",
                "supersedes")
        return {k: v for k, v in record.items() if k not in skip}

    def test_baseline_17_exact(self):                                       # A
        self.assertEqual(len(RESULT["baseline_table"]), 17)
        fields = ("selection_status", "terminal_width_trend", "candidate_count",
                  "admissible_count", "selected_pair_identity", "terminal_compression_ratio",
                  "realized_contraction_ratio")
        for row in RESULT["baseline_table"]:
            self.assertTrue(row["matches_pinned_facts"], row["case_id"])
            for f in fields:
                self.assertEqual(self.base[row["case_id"]][f], self.pinned[row["case_id"]][f])
        by_id = {c["case_id"]: c for c in self.cases}
        for case_id in CHEAP:
            outcome = calibration.case_outcome(by_id[case_id], _load_frame(by_id[case_id]),
                                               dict(DEFAULT_SHADOW_REPORT_PARAMETERS))
            self.assertEqual(outcome, self.base[case_id])
        nxpc = self.base[NXPC]
        self.assertEqual((nxpc["selection_status"], nxpc["terminal_width_trend"],
                          nxpc["deciding_component"]),
                         ("SELECTED", PERSISTENT_COMPRESSION, "IDENTITY_TIE_BREAK"))

    def test_population_is_geo_u1_pop_1_with_17_cases(self):               # B
        eligible = sorted(k for k, v in self.classification.items() if v["calibration_eligible"])
        self.assertEqual(RESULT["case_ids"], eligible)
        self.assertEqual(len(eligible), 17)
        self.assertTrue(RESULT["population_matches_policy"])
        self.assertEqual(RESULT["population_policy"], "GEO-U1-POP-1")
        for case_id in eligible:
            self.assertEqual(self.classification[case_id]["instrument_class"],
                             CRYPTO_LINEAR_PERPETUAL)

    def test_class_counts_and_concentration(self):                         # C, D, E, F
        h2 = RESULT["h2"]
        self.assertEqual(h2["baseline_class_counts"], {
            EXPANSION: 2, NO_ADMISSIBLE: 2, "NO_PERSISTENT_WIDTH_TREND": 9,
            PERSISTENT_COMPRESSION: 4})
        self.assertEqual(h2["baseline_class_by_timeframe"][PERSISTENT_COMPRESSION],
                         {"1": 3, "5": 1})
        self.assertEqual(sum(self.pinned[c]["production_detected"] for c in self.ids), 4)
        conc = concentration_summary(self.cases, self.classification, self.base)
        self.assertEqual(json.loads(_dumps(conc)), RESULT["concentration_summary"])
        self.assertFalse(conc["data_concentration_blocker"])
        self.assertEqual(conc["triggers"], [])

    def test_sensitivity_and_active_parameters_deterministic(self):        # G, H
        rows, active = summarize_sensitivity(self.outcomes, self.ids)
        historical = [r for r in RESULT["sensitivity_summary"]
                      if r["parameter"] != "min_alternating_touches"]
        self.assertEqual(json.loads(_dumps(rows)), historical)
        self.assertEqual([p for p in RESULT["active_parameters"]
                          if p != "min_alternating_touches"], active)
        self.assertIn("min_alternating_touches", RESULT["active_parameters"])
        self.assertEqual(len(active), 6)
        self.assertNotIn("min_alternating_touches", active)
        self.assertEqual(summarize_sensitivity(self.outcomes, list(reversed(self.ids)))[1], active)
        by_id = {c["case_id"]: c for c in self.cases}
        computed, _ = compute_outcomes([by_id[CHEAP[0]], by_id[NXPC]],
                                       sensitivity_parameter_sets(), processes=1)
        for case_id, by_label in computed.items():
            for label, outcome in by_label.items():
                self.assertEqual(outcome, self.outcomes[case_id][label], (case_id, label))

    def test_sweep_and_result_deterministic(self):                          # I
        historical_labels = ["BASELINE"] + [f"{name}={tag}"
                             for name, _, _, _ in calibration.PARAMETER_DOMAIN
                             for tag in ("LOW", "HIGH")]
        self.assertEqual(RESULT["outcome_matrix"]["labels"],
                         historical_labels)
        self.assertEqual(RESULT["tested_parameter_set_count"], 0)
        self.assertEqual(RESULT["candidate_presets"], [])
        self.assertEqual(RESULT["recommended_action"], "MORE_EVIDENCE_REQUIRED")
        self.assertTrue(any("CALIBRATION_UNDERDETERMINED" in reason
                            for reason in RESULT["reasons"]))

    def test_case_order_does_not_change_result(self):                      # J
        reordered = {k: self.outcomes[k] for k in reversed(self.ids)}
        self.assertEqual(self._strip(self._rebuild(list(reversed(self.cases)), reordered)),
                         self._strip(self._rebuild(self.cases, self.outcomes)))

    def test_surviving_sets_keep_every_hard_gate_case(self):               # K, L, M
        roles = {c: evidence_class(self.base[c]) for c in self.ids}
        compression = [c for c in self.ids if roles[c] == PERSISTENT_COMPRESSION]
        expansion = [c for c in self.ids if roles[c] == EXPANSION]
        negatives = [c for c in self.ids if roles[c] == NO_ADMISSIBLE]
        self.assertEqual((len(compression), len(expansion), len(negatives)), (4, 2, 2))
        self.assertIn(NXPC, compression)
        for label in RESULT["gate_passing_sets"]:
            for c in compression:
                self.assertEqual(evidence_class(self.outcomes[c][label]),
                                 PERSISTENT_COMPRESSION, (label, c))
            for c in expansion:
                self.assertEqual(evidence_class(self.outcomes[c][label]), EXPANSION, (label, c))
            for c in negatives:
                self.assertNotEqual(self.outcomes[c][label]["selection_status"], "SELECTED")
        lost = dict(self.base)
        lost[NXPC] = dict(self.base[NXPC], terminal_width_trend="NO_PERSISTENT_WIDTH_TREND")
        verdict = evaluate_parameter_set(self.base, lost, self.ids,
                                         DEFAULT_SHADOW_REPORT_PARAMETERS)
        self.assertIn(f"COMPRESSION_CASE_LOST: {NXPC}", verdict["gate_failures"])

    def test_leave_one_out_17_and_nxpc_fold(self):                         # N, O
        summary = RESULT["leave_one_out_summary"]
        self.assertEqual(summary["sets_evaluated"], len(RESULT["gate_passing_sets"]))
        for label in RESULT["gate_passing_sets"]:
            cand = {c: self.outcomes[c][label] for c in self.ids}
            loo = leave_one_out(self.base, cand, self.ids, self.sets[label])
            self.assertEqual(loo, leave_one_out(self.base, cand, list(reversed(self.ids)),
                                                self.sets[label]))
            if loo["robustness"] == "FRAGILE":
                self.assertEqual(summary["fragile"][label], loo["conclusion_flips_when_removed"])
            else:
                self.assertIn(label, summary["robust"])
        fold = nxpc_removal_fold(self.base, self.outcomes, self.ids,
                                 RESULT["gate_passing_sets"], self.sets)
        self.assertEqual(json.loads(_dumps(fold)), RESULT["h2"]["nxpc_removal_fold"])
        self.assertEqual(set(fold), set(RESULT["gate_passing_sets"]))

    def test_defaults_v1_gold_unchanged(self):                              # P, Q, R
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, DEFAULTS_AT_BASE)
        paths = [GOLD / n for n in MANIFESTS] + [GOLD / n for n in METADATA]
        paths += [GOLD / "calibration_result_v1.json", GOLD / "perf_parity_v1.json"]
        for name in MANIFESTS:
            paths += [ROOT / c["fixture_ref"] for c in load_manifest(GOLD / name)["cases"]]

        def semantic(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        joined = "".join(semantic(p) for p in paths)
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(), GOLD_SEMANTIC_SHA256)
        self.assertEqual(POLICY_V1.policy_version, "GEO-U1-POP-1")

    def test_cutover_never_authorized_and_no_production_import(self):      # S, T
        self.assertIs(RESULT["production_cutover_authorized"], False)
        self.assertIn(RESULT["recommended_action"], (
            "KEEP_BASELINE", "CANDIDATE_PRESET_FOR_SHADOW_VALIDATION",
            "MORE_EVIDENCE_REQUIRED"))
        pattern = re.compile(r"calibration_result_v\d|consensus_calibration(?!_population)")
        offenders = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if (rel.startswith(("tests/", ".git/", "runtime/", ".venv/", "venv/"))
                    or rel == "geometry/consensus_calibration.py"):
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_no_screenshot_derived_oracle(self):                            # U
        for case in self.cases:
            self.assertIn(case["evidence_class"], ("READY", "EXACT_SOURCE_TIME"))
            self.assertTrue(case["fixture_ref"].endswith(".json"))
        for case in self.cases:
            if case["evidence_class"] == "EXACT_SOURCE_TIME":
                payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
                self.assertTrue(payload["provenance"]["validation"]
                                ["recorded_anchor_prices_match_fixture"], case["case_id"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GEO-U1 H2 calibration rerun (diagnostic)")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--processes", type=int, default=16)
    parser.add_argument("--cache-dir", default=None)
    args = parser.parse_args()
    if not args.write:
        unittest.main()
    else:
        record = generate(args.processes, args.cache_dir, log=lambda m: print(m, flush=True))
        RESULT_PATH.write_text(json.dumps(record, sort_keys=True, allow_nan=False,
                                          separators=(",", ":")) + "\n", encoding="utf-8")
        print("DONE", record["recommended_action"], record["reasons"], flush=True)
