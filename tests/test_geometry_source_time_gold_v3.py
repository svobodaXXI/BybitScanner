"""GEO-U1 Slice G1: one exact crypto EXPANSION case closes target readiness."""

import hashlib
import inspect
import json
import unittest

import pandas as pd

import geometry.consensus_evidence_readiness as readiness
from geometry.consensus_calibration_population import (
    CRYPTO_LINEAR_PERPETUAL,
    classify_cases,
    readiness_by_population,
)
from geometry.consensus_evidence_readiness import case_facts, exact_source_time_case_problems
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS, build_gold_case_report
from tests.geometry_gold import ROOT, _analyze, _load_frame, geometry_identity, load_manifest
from wedge.detector import detect_structure

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
V1 = load_manifest(GOLD / "source_time_manifest_v1.json")
V2 = load_manifest(GOLD / "source_time_manifest_v2.json")
V3 = load_manifest(GOLD / "source_time_manifest_v3.json")
META1 = json.loads((GOLD / "instrument_metadata_v1.json").read_text(encoding="utf-8"))
META2 = json.loads((GOLD / "instrument_metadata_v2.json").read_text(encoding="utf-8"))
NEW = "ENSUSDT-1m-src1789759320000"
CANONICAL_SHA256 = "c26fc68acb127f7fd243ef807ab065ffd700e591a781ba154b973acb13b23c0c"
# Semantic hashes of every pre-existing Gold manifest/fixture/metadata at base 141c071.
EXISTING_SEMANTIC_SHA256 = "bd5775a6b9e5a363ee3b6c740986cfb6ba41bde7990a72756ef9a5e8180fee1b"


def _semantic(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _existing_paths():
    manifests = [GOLD / "manifest_v1.json", GOLD / "source_time_manifest_v1.json",
                 GOLD / "source_time_manifest_v2.json"]
    paths = list(manifests) + [GOLD / "instrument_metadata_v1.json"]
    for manifest in manifests:
        paths += [ROOT / c["fixture_ref"] for c in load_manifest(manifest)["cases"]]
    return paths


def _classification():
    return classify_cases(META1["case_instruments"] + META2["case_instruments"],
                          {**META1["instruments"], **META2["instruments"]})


def _readiness(facts, reproduced):
    return readiness_by_population(
        facts, _classification(), newly_recovered_case_ids={NEW},
        provenance_complete_case_ids={f["case_id"] for f in facts},
        unrecoverable_targets=[t["target"] for t in V1["unrecoverable_targets"]],
        reproduced_case_ids=reproduced)


class ExistingEvidenceTests(unittest.TestCase):
    def test_existing_cases_metadata_and_g0_classification_unchanged(self):  # A, B
        joined = "".join(_semantic(p) for p in _existing_paths())
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(), EXISTING_SEMANTIC_SHA256)
        g0 = classify_cases(META1["case_instruments"], META1["instruments"])
        self.assertEqual([g0[k] for k in sorted(g0)], META1["observed_case_classification"])
        combined = _classification()
        for row in META1["observed_case_classification"]:
            self.assertEqual(combined[row["case_id"]], row)
        self.assertEqual(V3["observed_slice_d_case_facts"][:16],
                         V2["observed_slice_d_case_facts"])

    def test_thresholds_and_constants_unchanged(self):                       # K
        self.assertEqual(len(DEFAULT_SHADOW_REPORT_PARAMETERS), 17)
        self.assertEqual((DEFAULT_SHADOW_REPORT_PARAMETERS["compression_max_ratio"],
                          DEFAULT_SHADOW_REPORT_PARAMETERS["expansion_min_ratio"],
                          DEFAULT_SHADOW_REPORT_PARAMETERS["terminal_window_bars"]),
                         (0.9, 1.1, 30))
        self.assertEqual(
            (readiness.MIN_EXACT_CASES, readiness.MIN_PERSISTENT_COMPRESSION,
             readiness.MIN_EXPANSION, readiness.MIN_NO_TREND,
             readiness.MIN_NO_ADMISSIBLE, readiness.MIN_PRODUCTION_DETECTED),
            (12, 3, 2, 3, 2, 3))


class NewCaseTests(unittest.TestCase):
    case = V3["cases"][0]

    def test_new_case_is_crypto_from_pinned_metadata(self):                  # C
        self.assertEqual([c["case_id"] for c in V3["cases"]], [NEW])
        self.assertEqual(META2["instruments"]["ENSUSDT"]["symbolType"], "")
        row = _classification()[NEW]
        self.assertEqual(row["instrument_class"], CRYPTO_LINEAR_PERPETUAL)
        self.assertTrue(row["calibration_eligible"])
        self.assertEqual(META2["observed_case_classification"], [row])

    def test_fixture_provenance_cutoff_and_anchor_prices(self):              # D
        payload = json.loads((ROOT / self.case["fixture_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(exact_source_time_case_problems(self.case, payload), ())
        provenance = payload["provenance"]
        frame = _load_frame(self.case)
        self.assertEqual(len(frame), 199)
        self.assertEqual(int(frame.time.iloc[-1]), self.case["cutoff_candle_open_ms"])
        self.assertEqual(provenance["excluded_forming_candle_open_ms"],
                         self.case["cutoff_candle_open_ms"] + provenance["interval_ms"])
        self.assertEqual(provenance["scanner_record"]["scanner_source_candle_time_ms"],
                         provenance["excluded_forming_candle_open_ms"])
        checks = provenance["validation"]["anchor_price_checks"]
        self.assertEqual(len(checks), 4)
        for key, check in checks.items():
            column = "high" if key.startswith("upper_line") else "low"
            self.assertEqual(float(frame[column].iloc[int(key.split("=")[1])]), check["recorded"])
        _, _, geometry = _analyze(frame)
        self.assertEqual(geometry_identity(geometry),
                         self.case["expectation"]["production_geometry_identity"])
        detected = detect_structure(geometry, candles=frame) if geometry else None
        self.assertEqual(detected["pattern"] if detected else None,
                         self.case["expectation"]["production_pattern"])

    def test_exact_shadow_is_selected_expansion_three_runs_and_future_rows(self):  # E, F, G
        frame = _load_frame(self.case)
        first = build_gold_case_report(self.case, frame)
        second = build_gold_case_report(self.case, frame)
        future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
        third = build_gold_case_report(self.case, pd.concat([frame, future], ignore_index=True))
        hashes = {hashlib.sha256(_dumps(r).encode()).hexdigest() for r in (first, second, third)}
        self.assertEqual(hashes, {CANONICAL_SHA256})
        runs = V3["reproducibility"][NEW]["runs"]
        self.assertEqual(len(runs), 3)
        self.assertTrue(any(r["future_rows_appended"] for r in runs))
        self.assertEqual({r["canonical_report_sha256"] for r in runs}, {CANONICAL_SHA256})
        facts = json.loads(_dumps(case_facts(first)))
        self.assertEqual((facts["selection_status"], facts["terminal_width_trend"]),
                         ("SELECTED", "EXPANSION"))
        self.assertEqual(facts, V3["observed_slice_d_case_facts"][-1])


class ReadinessTests(unittest.TestCase):
    facts = V3["observed_slice_d_case_facts"]
    reproduced = set(V2["reproducibility"]) | set(V3["reproducibility"])

    def test_all_linear_historical_and_current(self):                       # H
        historical = _readiness(V2["observed_slice_d_case_facts"], set(V2["reproducibility"]))
        self.assertTrue(historical["ALL_LINEAR"].calibration_ready)
        self.assertEqual(historical["ALL_LINEAR"].exact_case_count, 16)
        current = _readiness(self.facts, self.reproduced)["ALL_LINEAR"]
        self.assertEqual(json.loads(_dumps(current.__dict__)), V3["observed_readiness_all_linear"])
        self.assertTrue(current.calibration_ready)

    def test_target_ready_only_with_new_case(self):                        # I, J
        with_new = _readiness(self.facts, self.reproduced)["TARGET_POPULATION"]
        self.assertEqual(json.loads(_dumps(with_new.__dict__)),
                         V3["observed_readiness_target_population"])
        self.assertTrue(with_new.calibration_ready)
        self.assertEqual((with_new.exact_case_count, with_new.persistent_compression_count,
                          with_new.expansion_count, with_new.no_persistent_trend_count,
                          with_new.rejected_selection_count),
                         (16, 3, 2, 9, 2))
        self.assertEqual(_dumps(_readiness(self.facts[::-1], self.reproduced)
                                ["TARGET_POPULATION"].__dict__), _dumps(with_new.__dict__))
        without = _readiness(self.facts[:-1], self.reproduced)["TARGET_POPULATION"]
        self.assertFalse(without.calibration_ready)
        self.assertEqual(without.calibration_blockers, ("EXPANSION: have 1, need >= 2",))
        unreproduced = _readiness(self.facts, self.reproduced - {NEW})["TARGET_POPULATION"]
        self.assertFalse(unreproduced.calibration_ready)

    def test_no_calibration_logic_in_g1_evidence(self):                     # L
        for source in (inspect.getsource(readiness),
                       inspect.getsource(classify_cases),
                       inspect.getsource(readiness_by_population)):
            for forbidden in ("calibrate(", "fit_threshold", "grid_search", "optimi"):
                self.assertNotIn(forbidden, source.lower())


if __name__ == "__main__":
    unittest.main()
