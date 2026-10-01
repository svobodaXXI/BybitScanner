"""GEO-U1 Slice H4-A: exact non-compression alternation-3 evidence."""

import hashlib
import json
import re
import unittest

import pandas as pd

from geometry.consensus_calibration import (
    DEFAULT_SHADOW_REPORT_PARAMETERS,
    case_outcome,
    evidence_class,
)
from geometry.consensus_calibration_population import CRYPTO_LINEAR_PERPETUAL, POLICY_V1, classify_cases
from geometry.consensus_evidence_readiness import case_facts, exact_source_time_case_problems
from geometry.consensus_gold_report import build_gold_case_report
from tests.geometry_gold import ROOT, _analyze, _load_frame, geometry_identity, load_manifest
from wedge.detector import detect_structure

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
V5 = load_manifest(GOLD / "source_time_manifest_v5.json")
V6 = load_manifest(GOLD / "source_time_manifest_v6.json")
METAS = [json.loads((GOLD / f"instrument_metadata_v{i}.json").read_text(encoding="utf-8"))
         for i in (1, 2, 3, 4, 5)]
CASES = {c["case_id"]: c for c in V6["cases"]}
IDS = [c["case_id"] for c in V6["cases"]]
FACTS = {f["case_id"]: f for f in V6["observed_slice_d_case_facts"]}
PAIR = V6["observed_h4a_pair_facts"]
DIAG = V6["observed_min_alternating_touches_diagnostic"]
SUBSET = V6["search"]["candidate_subset_before_admission"]
# Semantic hashes of every pre-existing Gold manifest/fixture/metadata, the
# v1/v2 calibration results and perf parity at base e417912.
EXISTING_SEMANTIC_SHA256 = "55834363d68ef6be2c98cb252bbdeece6b835b329dbb0d8299e4b0e8abfebed9"
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
INTERVAL = {"1": 60000, "5": 300000}


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _sha(report):
    return hashlib.sha256(_dumps(report).encode()).hexdigest()


def _classification():
    return classify_cases(sum((m["case_instruments"] for m in METAS), []),
                          {k: v for m in METAS for k, v in m["instruments"].items()})


class SubsetAndAdmissionTests(unittest.TestCase):
    def test_subset_counts_reconstruct_from_pinned_h3_screen(self):
        rows = V5["search"]["screened_all_rows"]["rows"]
        alt3 = [r for r in rows if r[2] == "SELECTED" and r[4] == 3]
        self.assertEqual(SUBSET["alternation_3_selected_total"], len(alt3))
        self.assertEqual(SUBSET["by_trend"], {
            "EXPANSION": 18, "NO_PERSISTENT_WIDTH_TREND": 25, "PERSISTENT_COMPRESSION": 7})
        self.assertEqual(len(SUBSET["non_compression_candidates"]), 43)
        self.assertEqual(sorted(SUBSET["already_accepted_in_h3"]),
                         ["BNTUSDT-5m-src1789994700000", "LDOUSDT-1m-src1789759560000"])
        self.assertTrue(V6["search"]["target_met"])
        self.assertFalse(V6["search"]["bounded_class_exhaustion"])

    def test_admission_rule_reproduces_the_accepted_cases(self):
        gold_symbols = set()
        for m in ("manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
                  "source_time_manifest_v3.json", "source_time_manifest_v4.json",
                  "source_time_manifest_v5.json"):
            for c in load_manifest(GOLD / m)["cases"]:
                gold_symbols.add(c["symbol"] if c["symbol"].endswith("USDT") else c["symbol"] + "USDT")
        picked, used = [], set()
        for cls in ("EXPANSION", "NO_PERSISTENT_WIDTH_TREND"):
            for tf in ("1", "5"):
                cands = sorted((c for c in SUBSET["non_compression_candidates"]
                                if c[2] == cls and c[0].split("-")[1] == f"{tf}m"
                                and c[0].split("-")[0] not in gold_symbols | {"CASHCATUSDT", "ENAUSDT"}
                                and c[0].split("-")[0] not in used), key=lambda c: (c[1], c[0]))
                picked.append(cands[0][0])
                used.add(cands[0][0].split("-")[0])
        self.assertEqual(sorted(picked), sorted(IDS))

    def test_four_cases_cover_both_classes_and_timeframes(self):             # C, D
        self.assertEqual(sorted((FACTS[c]["terminal_width_trend"], CASES[c]["timeframe"]) for c in IDS),
                         [("EXPANSION", "1"), ("EXPANSION", "5"),
                          ("NO_PERSISTENT_WIDTH_TREND", "1"), ("NO_PERSISTENT_WIDTH_TREND", "5")])
        for case_id in IDS:
            self.assertEqual(PAIR[case_id]["alternating_touches"], 3)
            self.assertNotEqual(FACTS[case_id]["terminal_width_trend"], "PERSISTENT_COMPRESSION")
        self.assertEqual(len({CASES[c]["symbol"] for c in IDS}), 4)


class EvidenceTests(unittest.TestCase):
    def test_eligible_from_pinned_metadata(self):                            # B
        classification = _classification()
        self.assertEqual(METAS[4]["observed_case_classification"],
                         [classification[c] for c in IDS])
        for case_id in IDS:
            self.assertEqual(classification[case_id]["instrument_class"], CRYPTO_LINEAR_PERPETUAL)
            self.assertTrue(classification[case_id]["calibration_eligible"])

    def test_fixtures_exact_continuous_anchored_forming_excluded(self):      # A, E, F, G, H
        for case_id, case in CASES.items():
            payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(exact_source_time_case_problems(case, payload), (), case_id)
            provenance, interval = payload["provenance"], INTERVAL[case["timeframe"]]
            times = [row[0] for row in payload["candles"]]
            self.assertEqual(len(set(times)), 199)
            self.assertEqual(times, [times[0] + i * interval for i in range(199)])
            source = provenance["scanner_record"]["scanner_source_candle_time_ms"]
            self.assertEqual(provenance["excluded_forming_candle_open_ms"], source)
            self.assertEqual(source, times[-1] + interval)
            self.assertNotIn(source, times)
            self.assertEqual(case_id, f"{case['symbol']}-{case['timeframe']}m-src{source}")
            frame = _load_frame(case)
            for key, check in provenance["validation"]["anchor_price_checks"].items():
                column = "high" if key.startswith("upper_line") else "low"
                self.assertEqual(float(frame[column].iloc[int(key.split("=")[1])]), check["recorded"])

    def test_shadow_facts_pinned_and_reproducible(self):                     # I-N
        for case_id, case in CASES.items():
            frame = _load_frame(case)
            future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
            reports = [build_gold_case_report(case, frame), build_gold_case_report(case, frame),
                       build_gold_case_report(case, pd.concat([frame, future], ignore_index=True))]
            self.assertEqual({_sha(r) for r in reports}, {PAIR[case_id]["canonical_report_sha256"]}, case_id)
            runs = V6["reproducibility"][case_id]["runs"]
            self.assertEqual(len(runs), 3)
            self.assertTrue(any(r["future_rows_appended"] for r in runs))
            self.assertEqual({r["canonical_report_sha256"] for r in runs},
                             {PAIR[case_id]["canonical_report_sha256"]})
            facts = json.loads(_dumps(case_facts(reports[0])))
            self.assertEqual(facts, FACTS[case_id])
            shadow, pair = reports[0]["shadow"], reports[0]["shadow"]["pair"]
            self.assertEqual(facts["selection_status"], "SELECTED")
            self.assertEqual(pair["alternating_touch_count"], 3)
            self.assertEqual(pair["cross_boundary_traversal_count"], PAIR[case_id]["cross_boundary_traversals"])
            self.assertEqual((pair["upper_touch_count"], pair["lower_touch_count"]),
                             (PAIR[case_id]["upper_touch_clusters"], PAIR[case_id]["lower_touch_clusters"]))
            self.assertEqual(pair["shared_support_coverage_ratio"], PAIR[case_id]["shared_support_coverage"])
            self.assertEqual(shadow["deciding_component"], PAIR[case_id]["deciding_component"])
            _, _, geometry = _analyze(frame)
            self.assertEqual(geometry_identity(geometry), case["expectation"]["production_geometry_identity"])
            detected = detect_structure(geometry, candles=frame) if geometry else None
            self.assertEqual(bool(detected and detected.get("detected")),
                             case["expectation"]["production_detected"])


class DiagnosticTests(unittest.TestCase):
    def test_alternation_diagnostic_deterministic_and_order_invariant(self):  # O, P
        values = {"low": 2, "current": 3, "high": 4}
        for order in (IDS, list(reversed(IDS))):
            for case_id in order:
                case, frame = CASES[case_id], _load_frame(CASES[case_id])
                for tag, v in values.items():
                    o = case_outcome(case, frame, {**DEFAULT_SHADOW_REPORT_PARAMETERS,
                                                   "min_alternating_touches": v})
                    pinned = DIAG["new_h4a"]["per_case"][case_id][tag]
                    self.assertEqual({k: o[k] for k in ("selection_status", "terminal_width_trend",
                                                         "selected_pair_identity", "candidate_count",
                                                         "admissible_count", "deciding_component")},
                                     {k: pinned[k] for k in ("selection_status", "terminal_width_trend",
                                                              "selected_pair_identity", "candidate_count",
                                                              "admissible_count", "deciding_component")},
                                     (case_id, tag))

    def test_diagnostic_facts_and_label(self):
        new = DIAG["new_h4a"]
        self.assertEqual(sorted(c[0] for c in new["class_changes"]), sorted(IDS))
        self.assertTrue(all(c[1] == "HIGH" and c[3] == "NO_ADMISSIBLE_PAIR" for c in new["class_changes"]))
        self.assertEqual(new["pair_only_changes"], [])
        for case_id in IDS:
            self.assertEqual(new["per_case"][case_id]["low"], new["per_case"][case_id]["current"])
        self.assertEqual(len(DIAG["combined_27"]["class_changes"]), 7)
        self.assertEqual(DIAG["combined_27"]["pair_only_changes"], [])
        self.assertTrue(all(c[1] == "HIGH" for c in DIAG["combined_27"]["class_changes"]))
        self.assertEqual(DIAG["classes_where_no_alt3_case_fails_at_high"], [])
        self.assertEqual(DIAG["classes_where_every_alt3_case_fails_at_high"],
                         ["EXPANSION", "NO_PERSISTENT_WIDTH_TREND", "PERSISTENT_COMPRESSION"])
        self.assertEqual(DIAG["label"], "CROSS_CLASS_MATERIALITY_SUPPORTED")


class InvarianceTests(unittest.TestCase):
    def test_old_gold_v1_v2_defaults_policy_unchanged(self):                 # Q, R, S, U
        names = ["manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
                 "source_time_manifest_v3.json", "source_time_manifest_v4.json",
                 "source_time_manifest_v5.json"]
        paths = [GOLD / n for n in names] + [GOLD / f"instrument_metadata_v{i}.json" for i in (1, 2, 3, 4)]
        paths += [GOLD / "calibration_result_v1.json", GOLD / "calibration_result_v2.json",
                  GOLD / "perf_parity_v1.json"]
        for name in names:
            paths += [ROOT / c["fixture_ref"] for c in load_manifest(GOLD / name)["cases"]]

        def semantic(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        joined = "".join(semantic(p) for p in paths)
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(), EXISTING_SEMANTIC_SHA256)
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, DEFAULTS_AT_BASE)
        self.assertEqual(POLICY_V1.policy_version, "GEO-U1-POP-1")
        v2 = json.loads((GOLD / "calibration_result_v2.json").read_text(encoding="utf-8"))
        self.assertIs(v2["production_cutover_authorized"], False)

    def test_cap_unchanged_and_no_production_import(self):                   # T, V
        import geometry.consensus_calibration as calibration
        self.assertEqual(calibration.MAX_ACTIVE_PARAMETERS, 6)
        pattern = re.compile(r"source_time_manifest_v6|instrument_metadata_v5")
        offenders = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", ".git/", "runtime/", ".venv/", "venv/")):
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_no_screenshot_derived_oracle(self):                             # W
        for case in CASES.values():
            provenance = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))["provenance"]
            self.assertTrue(provenance["owner_screenshot_link"].startswith("UNCONFIRMED"))
            self.assertTrue(provenance["source"].startswith("Bybit v5 public market kline"))
            self.assertTrue(provenance["validation"]["recorded_anchor_prices_match_fixture"])


if __name__ == "__main__":
    unittest.main()
