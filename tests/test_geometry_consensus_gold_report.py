"""GEO-U1 Slice D: SHADOW-vs-production Gold delta report contracts."""

import json
import unittest

import pandas as pd

from geometry.consensus_boundary import build_boundary_consensus
from geometry.consensus_gold_report import (
    DEFAULT_SHADOW_REPORT_PARAMETERS,
    NOT_COMPARABLE,
    UNAVAILABLE,
    build_gold_case_report,
    build_gold_delta_report,
    compose_case_report,
    format_delta_table,
)
from tests.geometry_gold import _analyze, _load_frame, load_manifest
from wedge.detector import detect_structure

TOSHI = "1000TOSHIUSDT-locality-invariant"   # production geometry present
XEC = "1000XECUSDT-no-local-formation"       # production geometry absent


def _case(case_id):
    return next(c for c in load_manifest()["cases"] if c["case_id"] == case_id)


def _dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class FullGoldReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = build_gold_delta_report()

    def test_schema_and_coverage_of_every_exact_gold_case(self):
        report = self.report
        manifest_ids = [c["case_id"] for c in load_manifest()["cases"]]
        self.assertEqual([c["case_id"] for c in report["cases"]], manifest_ids)
        self.assertEqual(report["mode"], "SHADOW_DELTA_REPORT_ONLY")
        self.assertEqual(report["verdict"], "NONE_FACTS_ONLY")
        self.assertEqual(report["parameters"], DEFAULT_SHADOW_REPORT_PARAMETERS)
        _dumps(report)
        for case in report["cases"]:
            self.assertEqual(
                set(case),
                {"case_id", "symbol", "timeframe", "evidence_class",
                 "expectation_kind", "as_of_index", "frame_rows", "production",
                 "shadow", "delta", "non_finite_values_replaced"})
            self.assertEqual(case["non_finite_values_replaced"], 0)
            self.assertEqual(case["frame_rows"], case["as_of_index"] + 1)
            self.assertGreaterEqual(case["shadow"]["candidate_count"],
                                    case["shadow"]["admissible_count"])
            self.assertNotIn("classification", case["shadow"])
            self.assertNotIn("better", json.dumps(case["delta"]).lower())
            self.assertEqual(case["delta"]["support_coverage"], NOT_COMPARABLE)
            self.assertEqual(case["delta"]["touch_evidence"], NOT_COMPARABLE)
            self.assertEqual(case["delta"]["classification"]["status"],
                             NOT_COMPARABLE)

    def test_absent_production_geometry_is_unavailable_not_invented(self):
        for case_id in (XEC, "AEVO-formation-fit-negative"):
            case = next(c for c in self.report["cases"] if c["case_id"] == case_id)
            self.assertFalse(case["production"]["geometry_present"])
            self.assertEqual(case["production"]["classification"], UNAVAILABLE)
            self.assertEqual(case["production"]["upper"], UNAVAILABLE)
            self.assertEqual(case["delta"]["sides"], UNAVAILABLE)
            self.assertEqual(case["delta"]["identity"], UNAVAILABLE)
            self.assertEqual(case["delta"]["widths_at_production_interval"],
                             UNAVAILABLE)

    def test_present_production_geometry_gets_fact_deltas(self):
        pons = next(c for c in self.report["cases"]
                    if c["case_id"] == "PONS-formation-fit-positive-anchor")
        self.assertEqual(pons["production"]["identity"],
                         [143, 178, 145, 186, 143, 186])
        self.assertEqual(pons["production"]["classification"]["pattern"],
                         "Falling Wedge")
        if pons["shadow"]["selection_status"] == "SELECTED":
            sides = pons["delta"]["sides"]
            for side in ("upper", "lower"):
                self.assertIn("slope_delta_shadow_minus_production", sides[side])
                self.assertIn("seed_anchor_match", sides[side])
            for label in ("start", "end"):
                self.assertIn(label, pons["delta"]["widths_at_production_interval"])
        else:
            self.assertEqual(pons["delta"]["sides"], UNAVAILABLE)

    def test_aggregate_is_counts_only_and_consistent(self):
        agg = self.report["aggregate"]
        cases = self.report["cases"]
        self.assertEqual(agg["total_cases"], len(cases))
        self.assertEqual(
            agg["cases_with_admissible_shadow_selection"]
            + agg["cases_with_rejected_shadow_selection"]
            + sum(c["shadow"]["selection_status"] == "NO_CANDIDATES" for c in cases),
            len(cases))
        self.assertEqual(sum(agg["presence_agreement"].values()), len(cases))
        self.assertEqual(sum(agg["terminal_trend_counts_top_ranked"].values()),
                         len(cases))
        self.assertEqual(agg["classification_agreement"], NOT_COMPARABLE)
        for forbidden in ("score", "winner", "performance", "better"):
            self.assertFalse(any(forbidden in key.lower() for key in agg))

    def test_table_helper_is_compact_review_text(self):
        table = format_delta_table(self.report)
        for case in self.report["cases"]:
            self.assertIn(case["case_id"][:34], table)
        self.assertIn("facts only; no verdict", table)


class InvarianceTests(unittest.TestCase):
    def test_determinism_future_rows_reversal_and_production_inert(self):
        case = _case(TOSHI)
        frame = _load_frame(case)
        pristine = frame.copy(deep=True)
        _, _, before = _analyze(frame)
        before_model = json.dumps(vars(before), sort_keys=True)
        before_classification = detect_structure(before, candles=frame)

        expected = build_gold_case_report(case, frame)
        self.assertEqual(_dumps(build_gold_case_report(case, frame)),
                         _dumps(expected))

        future = pd.DataFrame({name: [float("nan")] * 10
                               for name in ("open", "high", "low", "close")})
        extended = pd.concat([frame, future], ignore_index=True)
        self.assertEqual(_dumps(build_gold_case_report(case, extended)),
                         _dumps(expected))

        boundary = dict(as_of_index=case["as_of_index"], episode_start_index=0,
                        inlier_band_atr=0.2, separation_atr=0.75)
        uppers = build_boundary_consensus(frame, side="upper", **boundary)
        lowers = build_boundary_consensus(frame, side="lower", **boundary)
        reversed_report = compose_case_report(
            case, frame, tuple(reversed(uppers)), tuple(reversed(lowers)))
        self.assertEqual(_dumps(reversed_report), _dumps(expected))

        pd.testing.assert_frame_equal(frame, pristine)
        _, _, after = _analyze(frame)
        self.assertEqual(json.dumps(vars(after), sort_keys=True), before_model)
        self.assertEqual(detect_structure(after, candles=frame),
                         before_classification)
        self.assertTrue(expected["production"]["geometry_present"])

    def test_case_ids_filter_and_invalid_cutoff_fail_closed(self):
        report = build_gold_delta_report(case_ids={XEC})
        self.assertEqual([c["case_id"] for c in report["cases"]], [XEC])
        self.assertEqual(report["aggregate"]["total_cases"], 1)
        case = dict(_case(XEC), as_of_index=10_000)
        with self.assertRaises(ValueError):
            compose_case_report(case, _load_frame(_case(XEC)), (), ())


if __name__ == "__main__":
    unittest.main()
