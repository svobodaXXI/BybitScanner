"""Focused tests for RVL-G3 Geometry Gold baseline reporting."""

import unittest

from tests.geometry_gold_report import build_baseline_report, render_text


MANIFEST = {
    "schema_version": 1,
    "cases": [
        {
            "case_id": "positive",
            "symbol": "P",
            "expectation": {
                "kind": "POSITIVE_ANCHOR",
                "geometry_identity": [10, 20, 12, 22, 10, 22],
                "detected": True,
            },
        },
        {
            "case_id": "negative",
            "symbol": "N",
            "expectation": {"kind": "NO_GEOMETRY"},
        },
        {
            "case_id": "locality",
            "symbol": "L",
            "expectation": {
                "kind": "LOCALITY_INVARIANT",
                "max_span": 120,
                "forbidden_interval": [30, 173],
                "fresh": False,
            },
        },
    ],
}


class GeometryGoldBaselineReportTests(unittest.TestCase):
    def test_green_report_has_zero_anchor_delta_and_no_changed_cases(self):
        results = [
            {
                "case_id": "positive",
                "symbol": "P",
                "expectation_kind": "POSITIVE_ANCHOR",
                "passed": True,
                "errors": [],
                "observed": {
                    "geometry_identity": [10, 20, 12, 22, 10, 22],
                    "detected": True,
                },
            },
            {
                "case_id": "negative",
                "symbol": "N",
                "expectation_kind": "NO_GEOMETRY",
                "passed": True,
                "errors": [],
                "observed": {"geometry_identity": None},
            },
            {
                "case_id": "locality",
                "symbol": "L",
                "expectation_kind": "LOCALITY_INVARIANT",
                "passed": True,
                "errors": [],
                "observed": {
                    "geometry_identity": [1, 2, 3, 4, 100, 180],
                    "interval": [100, 180],
                    "span": 80,
                    "fresh": False,
                },
            },
        ]

        report = build_baseline_report(manifest=MANIFEST, results=results)

        self.assertEqual(report["case_count"], 3)
        self.assertEqual(report["failed_cases"], [])
        self.assertEqual(report["changed_cases"], [])
        self.assertEqual(report["false_positive_cases"], [])
        self.assertEqual(report["false_negative_cases"], [])
        self.assertEqual(
            report["cases"][0]["anchor_delta"],
            {
                "upper_anchor": 0,
                "upper_second": 0,
                "lower_anchor": 0,
                "lower_second": 0,
                "start": 0,
                "end": 0,
            },
        )

    def test_report_exposes_false_positive_false_negative_and_anchor_regression(self):
        results = [
            {
                "case_id": "positive",
                "symbol": "P",
                "expectation_kind": "POSITIVE_ANCHOR",
                "passed": False,
                "errors": ["geometry identity changed"],
                "observed": {
                    "geometry_identity": [11, 20, 12, 22, 11, 22],
                    "detected": True,
                },
            },
            {
                "case_id": "negative",
                "symbol": "N",
                "expectation_kind": "NO_GEOMETRY",
                "passed": False,
                "errors": ["unexpected geometry"],
                "observed": {"geometry_identity": [1, 2, 3, 4, 1, 4]},
            },
            {
                "case_id": "locality",
                "symbol": "L",
                "expectation_kind": "LOCALITY_INVARIANT",
                "passed": False,
                "errors": ["expected an admitted local geometry"],
                "observed": {"geometry_identity": None},
            },
        ]

        report = build_baseline_report(manifest=MANIFEST, results=results)

        self.assertEqual(report["changed_cases"], ["positive", "negative", "locality"])
        self.assertEqual(report["false_positive_cases"], ["negative"])
        self.assertEqual(report["false_negative_cases"], ["locality"])
        self.assertEqual(report["cases"][0]["anchor_delta"]["upper_anchor"], 1)
        self.assertEqual(report["cases"][0]["anchor_delta"]["start"], 1)

        text = render_text(report)
        self.assertIn("[FAIL] positive", text)
        self.assertIn("upper_anchor=+1", text)
        self.assertIn("classification: FALSE_POSITIVE", text)
        self.assertIn("classification: FALSE_NEGATIVE", text)

    def test_missing_or_duplicate_results_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "count mismatch"):
            build_baseline_report(manifest=MANIFEST, results=[])

        duplicate = [
            {
                "case_id": "positive",
                "symbol": "P",
                "expectation_kind": "POSITIVE_ANCHOR",
                "passed": True,
                "errors": [],
                "observed": {"geometry_identity": None, "detected": False},
            },
        ] * 3
        with self.assertRaisesRegex(ValueError, "duplicate"):
            build_baseline_report(manifest=MANIFEST, results=duplicate)


if __name__ == "__main__":
    unittest.main()
