"""GEO-U1 Slice F: source-time Gold continuation + reproducibility-gated readiness."""

import hashlib
import json
import unittest

import pandas as pd

import geometry.consensus_evidence_readiness as readiness
from geometry.consensus_evidence_readiness import (
    aggregate_case_facts,
    assess_geometry_evidence_readiness,
    case_facts,
    exact_source_time_case_problems,
)
from geometry.consensus_gold_report import (
    DEFAULT_SHADOW_REPORT_PARAMETERS,
    build_gold_case_report,
)
from tests.geometry_gold import ROOT, _analyze, _load_frame, geometry_identity, load_manifest
from wedge.detector import detect_structure

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
V1 = GOLD / "source_time_manifest_v1.json"
V2 = GOLD / "source_time_manifest_v2.json"
NEW_QUALIFYING = {
    "BILLUSDT-1m-src1789759080000": "PERSISTENT_COMPRESSION",
    "GOATUSDT-1m-src1789850640000": "PERSISTENT_COMPRESSION",
    "MCDUSDT-5m-src1790004300000": "EXPANSION",
}
# Semantic (line-ending independent) content hashes of the 13 pre-existing
# exact cases' manifests and the eight Slice E fixtures, taken at base
# 6e7ce6c. Slice F must not alter any of them.
V1_SEMANTIC_SHA256 = "509fd47e37b8221832ee70c4470225bc0fdf34f6d9e47d35fb9b4493daf38279"
V1_FIXTURES_SEMANTIC_SHA256 = "24f507a72b7c46d555088cd6092675c0145a375f6dbc84d3b4a0959ec61a1796"
MANIFEST_V1_SEMANTIC_SHA256 = "16725897626d78c69eebbc1018a97993bf764a261149a4923b8b997d081e5bdd"


def _semantic(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _payload(case):
    return json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class ExistingEvidenceUnchangedTests(unittest.TestCase):
    def test_existing_13_cases_unchanged(self):                               # A
        self.assertEqual(_semantic(GOLD / "manifest_v1.json"), MANIFEST_V1_SEMANTIC_SHA256)
        self.assertEqual(_semantic(V1), V1_SEMANTIC_SHA256)
        joined = "".join(_semantic(ROOT / c["fixture_ref"])
                         for c in load_manifest(V1)["cases"])
        self.assertEqual(hashlib.sha256(joined.encode()).hexdigest(),
                         V1_FIXTURES_SEMANTIC_SHA256)
        v2 = load_manifest(V2)
        self.assertEqual(v2["observed_slice_d_case_facts"][:13],
                         load_manifest(V1)["observed_slice_d_case_facts"])

    def test_thresholds_and_rule_constants_unchanged(self):                   # E
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS, {
            "inlier_band_atr": 0.2, "separation_atr": 0.75,
            "touch_band_atr": 0.2, "minimum_swing_width_fraction": 0.30,
            "minimum_swing_atr": 0.5, "minimum_side_touch_clusters": 2,
            "min_cross_boundary_traversals": 1, "min_alternating_touches": 3,
            "min_touch_balance": 0.25, "min_shared_support_coverage": 0.25,
            "max_support_gap_fraction": 0.5, "terminal_window_bars": 30,
            "terminal_segments": 3, "compression_max_ratio": 0.9,
            "expansion_min_ratio": 1.1, "segment_tolerance": 0.05,
            "single_bar_narrow_ratio": 0.5,
        })
        self.assertEqual(
            (readiness.MIN_EXACT_CASES, readiness.MIN_PERSISTENT_COMPRESSION,
             readiness.MIN_EXPANSION, readiness.MIN_NO_TREND,
             readiness.MIN_NO_ADMISSIBLE, readiness.MIN_PRODUCTION_DETECTED),
            (12, 3, 2, 3, 2, 3))
        self.assertTrue(load_manifest(V1)["observed_readiness"]["readiness_rule"]
                        == readiness.READINESS_RULE)


class NewFixtureTests(unittest.TestCase):
    manifest = load_manifest(V2)

    def test_new_fixtures_eligible_cutoff_and_anchor_prices(self):           # B, C, D
        self.assertEqual({c["case_id"] for c in self.manifest["cases"]},
                         set(NEW_QUALIFYING))
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                payload = _payload(case)
                self.assertEqual(exact_source_time_case_problems(case, payload), ())
                provenance = payload["provenance"]
                frame = _load_frame(case)
                self.assertEqual(len(frame), 199)
                self.assertEqual(int(frame.time.iloc[-1]), case["cutoff_candle_open_ms"])
                self.assertEqual(provenance["excluded_forming_candle_open_ms"],
                                 case["cutoff_candle_open_ms"] + provenance["interval_ms"])
                self.assertEqual(provenance["scanner_record"]["scanner_source_candle_time_ms"],
                                 provenance["excluded_forming_candle_open_ms"])
                checks = provenance["validation"]["anchor_price_checks"]
                self.assertEqual(len(checks), 4)
                for key, check in checks.items():
                    column = "high" if key.startswith("upper_line") else "low"
                    index = int(key.split("=")[1])
                    self.assertEqual(float(frame[column].iloc[index]), check["recorded"])
                _, _, geometry = _analyze(frame)
                self.assertEqual(geometry_identity(geometry),
                                 case["expectation"]["production_geometry_identity"])
                detected = detect_structure(geometry, candles=frame) if geometry else None
                self.assertEqual(detected["pattern"] if detected else None,
                                 case["expectation"]["production_pattern"])

    def test_new_qualifying_cases_reproduce_twice_and_ignore_future_rows(self):  # F, G
        pinned = {f["case_id"]: f for f in self.manifest["observed_slice_d_case_facts"]}
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                frame = _load_frame(case)
                first = build_gold_case_report(case, frame)
                second = build_gold_case_report(case, frame)
                future = pd.DataFrame({n: [float("nan")] * 10 for n in frame.columns})
                third = build_gold_case_report(
                    case, pd.concat([frame, future], ignore_index=True))
                self.assertEqual(_dumps(first), _dumps(second))
                self.assertEqual(_dumps(first), _dumps(third))
                facts = json.loads(_dumps(case_facts(first)))
                self.assertEqual(facts, pinned[case["case_id"]])
                self.assertEqual(facts["selection_status"], "SELECTED")
                self.assertEqual(facts["terminal_width_trend"],
                                 NEW_QUALIFYING[case["case_id"]])
                sha = hashlib.sha256(_dumps(first).encode()).hexdigest()
                for run in self.manifest["reproducibility"][case["case_id"]]["runs"]:
                    self.assertEqual(run["canonical_report_sha256"], sha)

    def test_screenshot_only_candidates_remain_excluded(self):              # K
        problems = exact_source_time_case_problems(
            {"case_id": "X", "evidence_class": "VISUAL_ONLY"}, None)
        self.assertIn("NO_FIXTURE_CANDLES", problems)
        ids = {c["case_id"] for c in self.manifest["cases"]}
        for target in load_manifest(V1)["unrecoverable_targets"]:
            self.assertNotIn(target["target"], ids)
        for case in self.manifest["cases"]:
            self.assertTrue(_payload(case)["provenance"]["owner_screenshot_link"]
                            .startswith("UNCONFIRMED"))


class ExpandedReadinessTests(unittest.TestCase):
    manifest = load_manifest(V2)

    def _assess(self, reproduced):
        v1 = load_manifest(V1)
        ids = ({c["case_id"] for c in load_manifest()["cases"]}
               | {c["case_id"] for c in v1["cases"]}
               | {c["case_id"] for c in self.manifest["cases"]})
        return assess_geometry_evidence_readiness(
            self.manifest["observed_slice_d_case_facts"],
            newly_recovered_case_ids={c["case_id"] for c in self.manifest["cases"]},
            provenance_complete_case_ids=ids,
            unrecoverable_targets=[t["target"] for t in v1["unrecoverable_targets"]],
            reproduced_case_ids=reproduced)

    def test_expanded_aggregate_and_readiness_deterministic(self):          # H, I
        facts = self.manifest["observed_slice_d_case_facts"]
        self.assertEqual(len(facts), 16)
        aggregate = aggregate_case_facts(facts)
        self.assertEqual(_dumps(aggregate), _dumps(aggregate_case_facts(facts[::-1])))
        self.assertEqual(json.loads(_dumps(aggregate)),
                         self.manifest["observed_expanded_aggregate"])
        result = self._assess(set(self.manifest["reproducibility"]))
        self.assertEqual(json.loads(_dumps(result.__dict__)),
                         self.manifest["observed_readiness"])
        self.assertEqual(json.loads(_dumps(self._assess(
            set(self.manifest["reproducibility"])).__dict__)),
            self.manifest["observed_readiness"])

    def test_gap_closing_cases_require_reproducibility(self):               # J
        reproduced = set(self.manifest["reproducibility"])
        result = self._assess(reproduced)
        self.assertTrue(result.calibration_ready)
        qualifying = {f["case_id"] for f in self.manifest["observed_slice_d_case_facts"]
                      if f["selection_status"] == "SELECTED"
                      and f["terminal_width_trend"] in ("PERSISTENT_COMPRESSION", "EXPANSION")}
        self.assertEqual(qualifying, reproduced)
        for case_id in sorted(qualifying):
            with self.subTest(withheld=case_id):
                blocked = self._assess(reproduced - {case_id})
                self.assertFalse(blocked.calibration_ready)
                self.assertTrue(any(case_id in b for b in blocked.calibration_blockers))
        for entry in self.manifest["reproducibility"].values():
            self.assertGreaterEqual(len(entry["runs"]), 2)
            self.assertTrue(any(r["future_rows_appended"] for r in entry["runs"]))
            self.assertEqual(len({r["canonical_report_sha256"] for r in entry["runs"]}), 1)
        # Without the opt-in the Slice E behaviour (and rule text) is unchanged.
        self.assertEqual(self._assess(None).readiness_rule, readiness.READINESS_RULE)


if __name__ == "__main__":
    unittest.main()
