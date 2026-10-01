"""GEO-U1 Slice H3: exact crypto evidence constraining min_alternating_touches."""

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
META4 = json.loads((GOLD / "instrument_metadata_v4.json").read_text(encoding="utf-8"))
METAS = [json.loads((GOLD / f"instrument_metadata_v{i}.json").read_text(encoding="utf-8"))
         for i in (1, 2, 3, 4)]
V2R = json.loads((GOLD / "calibration_result_v2.json").read_text(encoding="utf-8"))
CASES = {c["case_id"]: c for c in V5["cases"]}
IDS = [c["case_id"] for c in V5["cases"]]
FACTS = {f["case_id"]: f for f in V5["observed_slice_d_case_facts"]}
PAIR = V5["observed_h3_pair_facts"]
DIAG = V5["observed_min_alternating_touches_diagnostic"]
# Semantic hashes of every pre-existing Gold manifest/fixture/metadata and the
# v1/v2 calibration results and perf parity at base cce347d.
EXISTING_SEMANTIC_SHA256 = "7cc9bf8d4198906ca0acf9aac9197b8841f9fc8ed8a2e14cbeda984490760e7b"
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


def _bucket(alternating):
    return "3" if alternating == 3 else "4" if alternating == 4 else "5+"


def _classification():
    return classify_cases(sum((m["case_instruments"] for m in METAS), []),
                          {k: v for m in METAS for k, v in m["instruments"].items()})


class NewCaseEvidenceTests(unittest.TestCase):
    def test_six_cases_cover_all_buckets_and_both_timeframes(self):         # A
        self.assertEqual(len(IDS), 6)
        self.assertEqual(sorted(_bucket(PAIR[c]["alternating_touches"]) for c in IDS),
                         ["3", "3", "4", "4", "5+", "5+"])
        self.assertEqual(sorted(CASES[c]["timeframe"] for c in IDS), ["1", "1", "1", "5", "5", "5"])
        self.assertEqual(len({CASES[c]["symbol"] for c in IDS}), 6)
        self.assertFalse({CASES[c]["symbol"] for c in IDS} & {"CASHCATUSDT", "ENAUSDT"})
        self.assertEqual(sum(META4["instruments"][CASES[c]["symbol"]]["symbolType"] == "innovation"
                             for c in IDS), 1)

    def test_all_eligible_from_pinned_metadata(self):                       # B
        classification = _classification()
        self.assertEqual(META4["observed_case_classification"], [classification[c] for c in IDS])
        for case_id in IDS:
            self.assertEqual(classification[case_id]["instrument_class"], CRYPTO_LINEAR_PERPETUAL)
            self.assertTrue(classification[case_id]["calibration_eligible"])

    def test_fixtures_exact_and_forming_candle_excluded(self):              # C, D
        for case_id, case in CASES.items():
            payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(exact_source_time_case_problems(case, payload), (), case_id)
            provenance, interval = payload["provenance"], INTERVAL[case["timeframe"]]
            self.assertEqual(provenance["interval_ms"], interval)
            times = [row[0] for row in payload["candles"]]
            self.assertEqual(len(set(times)), 199)
            self.assertEqual(times, [times[0] + i * interval for i in range(199)])
            source = provenance["scanner_record"]["scanner_source_candle_time_ms"]
            self.assertEqual(provenance["excluded_forming_candle_open_ms"], source)
            self.assertEqual(source, times[-1] + interval)
            self.assertEqual(case_id, f"{case['symbol']}-{case['timeframe']}m-src{source}")
            self.assertNotIn(source, times)
            frame = _load_frame(case)
            for key, check in provenance["validation"]["anchor_price_checks"].items():
                column = "high" if key.startswith("upper_line") else "low"
                self.assertEqual(float(frame[column].iloc[int(key.split("=")[1])]), check["recorded"])

    def test_shadow_facts_pinned_and_reproducible(self):                    # E-K
        for case_id, case in CASES.items():
            frame = _load_frame(case)
            future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
            reports = [build_gold_case_report(case, frame), build_gold_case_report(case, frame),
                       build_gold_case_report(case, pd.concat([frame, future], ignore_index=True))]
            self.assertEqual({_sha(r) for r in reports}, {PAIR[case_id]["canonical_report_sha256"]}, case_id)
            runs = V5["reproducibility"][case_id]["runs"]
            self.assertEqual(len(runs), 3)
            self.assertTrue(any(r["future_rows_appended"] for r in runs))
            self.assertEqual({r["canonical_report_sha256"] for r in runs},
                             {PAIR[case_id]["canonical_report_sha256"]})
            facts = json.loads(_dumps(case_facts(reports[0])))
            self.assertEqual(facts, FACTS[case_id])
            self.assertEqual(facts["selection_status"], "SELECTED")
            shadow, pair = reports[0]["shadow"], reports[0]["shadow"]["pair"]
            self.assertEqual(pair["alternating_touch_count"], PAIR[case_id]["alternating_touches"])
            self.assertEqual(pair["cross_boundary_traversal_count"],
                             PAIR[case_id]["cross_boundary_traversals"])
            self.assertEqual((pair["upper_touch_count"], pair["lower_touch_count"]),
                             (PAIR[case_id]["upper_touch_clusters"],
                              PAIR[case_id]["lower_touch_count_clusters"]))
            self.assertEqual(shadow["deciding_component"], PAIR[case_id]["deciding_component"])
            _, _, geometry = _analyze(frame)
            self.assertEqual(geometry_identity(geometry),
                             case["expectation"]["production_geometry_identity"])
            detected = detect_structure(geometry, candles=frame) if geometry else None
            self.assertEqual(bool(detected and detected.get("detected")),
                             case["expectation"]["production_detected"])


class DiagnosticTests(unittest.TestCase):
    def test_alternation_diagnostic_deterministic_and_order_invariant(self):  # Q, R
        values = {"LOW": 2, "CURRENT": 3, "HIGH": 4}
        for order in (IDS, list(reversed(IDS))):
            observed = {}
            for case_id in order:
                case, frame = CASES[case_id], _load_frame(CASES[case_id])
                observed[case_id] = {
                    tag: evidence_class(case_outcome(
                        case, frame, {**DEFAULT_SHADOW_REPORT_PARAMETERS,
                                      "min_alternating_touches": v}))
                    for tag, v in values.items()}
            for case_id in IDS:
                entry = DIAG["new_h3"]["per_case"][case_id]
                self.assertEqual(observed[case_id], {"LOW": entry["low_class"],
                                                     "CURRENT": entry["current_class"],
                                                     "HIGH": entry["high_class"]}, case_id)

    def test_diagnostic_facts(self):
        self.assertEqual(DIAG["old_17"]["class_changes"],
                         [["NXPCUSDT-5m-src1789996800000", "HIGH",
                           "PERSISTENT_COMPRESSION", "NO_ADMISSIBLE_PAIR"]])
        self.assertEqual(DIAG["old_17"]["pair_only_changes"], [])
        high_new = sorted(c[0] for c in DIAG["high_4_class_changes_new"])
        threes = sorted(c for c in IDS if PAIR[c]["alternating_touches"] == 3)
        self.assertEqual(high_new, threes)
        for case_id in IDS:
            if PAIR[case_id]["alternating_touches"] >= 4:
                entry = DIAG["new_h3"]["per_case"][case_id]
                self.assertEqual(entry["high_class"], entry["current_class"], case_id)
        self.assertEqual(DIAG["new_h3"]["pair_only_changes"], [])
        low_changes = [c for c in DIAG["combined_23"]["class_changes"] if c[1] == "LOW"]
        self.assertEqual(low_changes, [])
        self.assertEqual(len(DIAG["combined_23"]["class_changes"]), 3)

    def test_universe_search_is_exhausted_and_bounded(self):
        search = V5["search"]
        self.assertTrue(search["exhausted"])
        self.assertEqual(search["exact_default_shadow_runs"], search["universe_size"])
        self.assertEqual(search["prefix_failures"], 0)
        rows = search["screened_all_rows"]["rows"]
        self.assertEqual(len(rows), search["universe_size"])
        self.assertEqual(sum(r[2] == "SELECTED" for r in rows), search["universe_outcome"]["SELECTED"])


class InvarianceTests(unittest.TestCase):
    def test_old_gold_v1_v2_defaults_policy_unchanged(self):                # L, M, N, O
        names = ["manifest_v1.json", "source_time_manifest_v1.json", "source_time_manifest_v2.json",
                 "source_time_manifest_v3.json", "source_time_manifest_v4.json"]
        paths = [GOLD / n for n in names] + [GOLD / f"instrument_metadata_v{i}.json" for i in (1, 2, 3)]
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
        self.assertIs(V2R["production_cutover_authorized"], False)

    def test_no_production_import_and_cap_unchanged(self):                  # P
        import geometry.consensus_calibration as calibration
        self.assertEqual(calibration.MAX_ACTIVE_PARAMETERS, 6)
        pattern = re.compile(r"source_time_manifest_v5|instrument_metadata_v4")
        offenders = []
        for path in ROOT.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(("tests/", ".git/", "runtime/", ".venv/", "venv/")):
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_no_screenshot_derived_oracle(self):                            # S
        for case in CASES.values():
            payload = json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))
            provenance = payload["provenance"]
            self.assertTrue(provenance["owner_screenshot_link"].startswith("UNCONFIRMED"))
            self.assertTrue(provenance["source"].startswith("Bybit v5 public market kline"))
            self.assertTrue(provenance["validation"]["recorded_anchor_prices_match_fixture"])


if __name__ == "__main__":
    unittest.main()
