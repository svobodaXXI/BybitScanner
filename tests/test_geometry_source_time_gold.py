"""GEO-U1 Slice E: exact source-time Geometry Gold + readiness contracts."""

import json
import unittest
from pathlib import Path

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
from tests.geometry_gold import (
    ROOT,
    _analyze,
    _load_frame,
    geometry_identity,
    load_manifest,
    run_geometry_gold,
)
from wedge.detector import detect_structure

SOURCE_TIME = ROOT / "tests" / "fixtures" / "geometry_gold" / "source_time_manifest_v1.json"
CHEAP_CASE = "ENAUSDT-1m-src1789759320000"   # 585 SHADOW pairs


def _payload(case):
    return json.loads((ROOT / case["fixture_ref"]).read_text(encoding="utf-8"))


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class SourceTimeFixtureTests(unittest.TestCase):
    manifest = load_manifest(SOURCE_TIME)

    def test_every_fixture_loads_offline_with_pinned_cutoff(self):          # A, B
        self.assertEqual(len(self.manifest["cases"]), 8)
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                payload = _payload(case)
                frame = _load_frame(case)
                self.assertEqual(len(frame), 199)
                self.assertEqual(case["as_of_index"], 198)
                self.assertEqual(int(frame.time.iloc[-1]),
                                 case["cutoff_candle_open_ms"])
                provenance = payload["provenance"]
                self.assertEqual(
                    provenance["excluded_forming_candle_open_ms"],
                    case["cutoff_candle_open_ms"] + provenance["interval_ms"])
                self.assertEqual(
                    provenance["scanner_record"]["scanner_source_candle_time_ms"],
                    provenance["excluded_forming_candle_open_ms"])
                self.assertTrue(frame.time.is_monotonic_increasing)
                self.assertEqual(frame.time.nunique(), len(frame))

    def test_provenance_complete_and_recorded_anchor_prices_verified(self):  # H
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                payload = _payload(case)
                self.assertEqual(exact_source_time_case_problems(case, payload), ())
                frame = _load_frame(case)
                checks = payload["provenance"]["validation"]["anchor_price_checks"]
                self.assertEqual(len(checks), 4)
                for key, check in checks.items():
                    side, index = key.split(".")[0], int(key.split("=")[1])
                    column = "high" if side == "upper_line" else "low"
                    self.assertEqual(float(frame[column].iloc[index]),
                                     check["recorded"])

    def test_screenshot_only_target_cannot_enter_exact_gold(self):          # I
        screenshot_only = {"case_id": "ENAUSDT-1m-owner-screenshot",
                           "symbol": "ENAUSDT", "timeframe": "1",
                           "evidence_class": "VISUAL_ONLY"}
        problems = exact_source_time_case_problems(screenshot_only, None)
        self.assertIn("EVIDENCE_CLASS_NOT_EXACT_SOURCE_TIME", problems)
        self.assertIn("NO_FIXTURE_CANDLES", problems)
        self.assertIn("MISSING_CUTOFF_CANDLE_OPEN_MS", problems)
        ids = {case["case_id"] for case in self.manifest["cases"]}
        for target in self.manifest["unrecoverable_targets"]:
            self.assertEqual(target["status"], "UNRECOVERABLE_EXACT_CUTOFF")
            self.assertNotIn(target["target"], ids)
        self.assertTrue(all("owner" not in i.lower() for i in ids))

    def test_production_result_is_the_pinned_observed_fact(self):           # F (new)
        for case in self.manifest["cases"]:
            with self.subTest(case=case["case_id"]):
                frame = _load_frame(case)
                _, _, geometry = _analyze(frame)
                expectation = case["expectation"]
                self.assertEqual(geometry_identity(geometry),
                                 expectation["production_geometry_identity"])
                detected = (detect_structure(geometry, candles=frame)
                            if geometry is not None else None)
                self.assertEqual(detected["pattern"] if detected else None,
                                 expectation["production_pattern"])


class ExistingGoldUnchangedTests(unittest.TestCase):
    def test_five_case_manifest_and_production_results_unchanged(self):     # E, F
        manifest = load_manifest()
        self.assertEqual(len(manifest["cases"]), 5)
        self.assertTrue(all(c["evidence_class"] == "READY" for c in manifest["cases"]))
        results = run_geometry_gold()
        self.assertTrue(all(r["passed"] for r in results), results)

    def test_no_calibration_threshold_is_mutated(self):                     # J
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


class SourceTimeReportTests(unittest.TestCase):
    """Full expanded recompute is ~40 min (~60k SHADOW pairs), so it is a
    one-off evidence run pinned in the manifest; one cheap case is recomputed
    live here to prove the pinned facts are reproducible."""

    def test_cheap_case_live_report_is_deterministic_and_matches_pin(self):  # C, D
        manifest = load_manifest(SOURCE_TIME)
        case = next(c for c in manifest["cases"] if c["case_id"] == CHEAP_CASE)
        frame = _load_frame(case)
        pristine = frame.copy(deep=True)
        report = build_gold_case_report(case, frame)
        expected = _dumps(report)
        self.assertEqual(_dumps(build_gold_case_report(case, frame)), expected)
        future = pd.DataFrame({name: [float("nan")] * 10 for name in frame.columns})
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(_dumps(build_gold_case_report(case, extended)), expected)
        pd.testing.assert_frame_equal(frame, pristine)
        pinned = next(f for f in manifest["observed_slice_d_case_facts"]
                      if f["case_id"] == CHEAP_CASE)
        self.assertEqual(json.loads(_dumps(case_facts(report))), pinned)

    def test_expanded_aggregate_and_readiness_are_deterministic_facts(self):  # G
        manifest = load_manifest(SOURCE_TIME)
        facts = manifest["observed_slice_d_case_facts"]
        self.assertEqual(
            [f["case_id"] for f in facts],
            [c["case_id"] for c in load_manifest()["cases"]]
            + [c["case_id"] for c in manifest["cases"]])
        aggregate = aggregate_case_facts(facts)
        self.assertEqual(_dumps(aggregate),
                         _dumps(aggregate_case_facts(list(reversed(facts)))))
        self.assertEqual(json.loads(_dumps(aggregate)),
                         manifest["observed_expanded_aggregate"])
        new_ids = {c["case_id"] for c in manifest["cases"]}
        provenance_ok = {c["case_id"] for c in manifest["cases"]
                         if not exact_source_time_case_problems(c, _payload(c))}
        # The five READY cases carry their RVL-G1 inventory provenance.
        provenance_ok |= {c["case_id"] for c in load_manifest()["cases"]}
        result = assess_geometry_evidence_readiness(
            facts, newly_recovered_case_ids=new_ids,
            provenance_complete_case_ids=provenance_ok,
            unrecoverable_targets=[t["target"]
                                   for t in manifest["unrecoverable_targets"]])
        self.assertEqual(result.exact_case_count, 13)
        self.assertEqual(result.newly_recovered_case_count, 8)
        self.assertEqual(result.source_provenance_complete_count, 13)
        self.assertEqual(result.calibration_ready, not result.calibration_blockers)
        self.assertEqual(json.loads(_dumps(result.__dict__)),
                         manifest["observed_readiness"])

    def test_readiness_rule_is_fixed_and_fails_closed(self):
        base = {"symbol": "X", "timeframe": "5", "production_geometry_present": True,
                "production_identity": None, "production_detected": True,
                "production_pattern": "Rising Wedge", "candidate_count": 1,
                "admissible_count": 1, "selected_pair_identity": None,
                "terminal_compression_ratio": None,
                "realized_contraction_ratio": None,
                "rejection_reasons_of_top_ranked": [],
                "presence_agreement": "BOTH_PRESENT"}
        trends = (["PERSISTENT_COMPRESSION"] * 3 + ["EXPANSION"] * 2
                  + ["NO_PERSISTENT_WIDTH_TREND"] * 5)
        facts = [dict(base, case_id=f"c{i}", selection_status="SELECTED",
                      terminal_width_trend=t) for i, t in enumerate(trends)]
        facts += [dict(base, case_id=f"n{i}", selection_status="NO_ADMISSIBLE_PAIR",
                       terminal_width_trend="NO_PERSISTENT_WIDTH_TREND")
                  for i in range(2)]
        ids = {f["case_id"] for f in facts}
        ready = assess_geometry_evidence_readiness(
            facts, newly_recovered_case_ids=set(),
            provenance_complete_case_ids=ids, unrecoverable_targets=())
        self.assertTrue(ready.calibration_ready)
        short = assess_geometry_evidence_readiness(
            facts[1:], newly_recovered_case_ids=set(),
            provenance_complete_case_ids=ids, unrecoverable_targets=())
        self.assertFalse(short.calibration_ready)
        self.assertIn("PERSISTENT_COMPRESSION: have 2, need >= 3",
                      short.calibration_blockers)
        missing = assess_geometry_evidence_readiness(
            facts, newly_recovered_case_ids=set(),
            provenance_complete_case_ids=ids - {"c0"}, unrecoverable_targets=())
        self.assertFalse(missing.calibration_ready)
        with self.assertRaises(ValueError):
            assess_geometry_evidence_readiness(
                facts + facts[:1], newly_recovered_case_ids=set(),
                provenance_complete_case_ids=ids, unrecoverable_targets=())


if __name__ == "__main__":
    unittest.main()
