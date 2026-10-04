"""H26: forward calibration policy keeps exactly six active dimensions."""

import json
import unittest

from geometry import consensus_calibration as calibration
from tests.geometry_gold import ROOT

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
H5 = json.loads((GOLD / "calibration_result_v3.json").read_text(encoding="utf-8-sig"))
FORWARD_ACTIVE = [
    "minimum_side_touch_clusters", "min_shared_support_coverage",
    "terminal_window_bars", "terminal_segments",
    "compression_max_ratio", "expansion_min_ratio",
]


def _record(outcomes, rows, active):
    # Serialization only: no grid, leave-one-out or population calibration run.
    return calibration.build_calibration_result(
        [{"case_id": c, "timeframe": c.split("-")[1][:-1]} for c in H5["case_ids"]],
        {c: {"calibration_eligible": True, "instrument_symbol": c.split("-")[0],
             "symbol_type": "ordinary"} for c in H5["case_ids"]},
        outcomes, sensitivity_rows=rows, active=active, sweep_labels=[],
        invalid_labels=[], parameter_sets=dict(calibration.sensitivity_parameter_sets()),
        determinism={}, performance={})


class ForwardActiveSetTests(unittest.TestCase):
    def setUp(self):
        self.outcomes = calibration.expand_outcome_matrix(H5["outcome_matrix"])
        self.rows, self.material = calibration.summarize_sensitivity(
            self.outcomes, H5["case_ids"])

    def test_policy_constants(self):
        self.assertEqual(sorted(calibration.DIAGNOSTIC_ONLY_PARAMETERS),
                         ["max_support_gap_fraction", "minimum_swing_width_fraction"])
        self.assertFalse(set(calibration.DIAGNOSTIC_ONLY_PARAMETERS)
                         & set(calibration.FROZEN_STRUCTURAL_PARAMETERS))
        self.assertEqual(tuple(calibration.FROZEN_STRUCTURAL_PARAMETERS),
                         ("min_alternating_touches",))
        self.assertEqual(calibration.MAX_ACTIVE_PARAMETERS, 6)

    def test_historical_h5_material_set_is_unchanged(self):
        self.assertEqual(self.material, H5["active_parameters"])
        self.assertEqual(len(self.material), 8)
        # Diagnostic-only names are still measured and reported.
        reported = {r["parameter"]: r["sensitivity"] for r in self.rows}
        for name in calibration.DIAGNOSTIC_ONLY_PARAMETERS:
            self.assertEqual(reported[name], "MATERIAL")

    def test_forward_active_set_is_exactly_six(self):
        active = calibration.forward_active_parameters(self.material)
        self.assertEqual(active, FORWARD_ACTIVE)
        self.assertLessEqual(len(active), calibration.MAX_ACTIVE_PARAMETERS)
        _, grid, invalid = calibration.derived_parameter_sets(active)
        self.assertEqual(len(grid) + len(invalid), 3 ** 6)

    def test_underdetermined_no_longer_triggered_by_active_count(self):
        def underdetermined(record):
            return [r for r in record["reasons"]
                    if r.startswith(calibration.CALIBRATION_UNDERDETERMINED)]
        self.assertTrue(underdetermined(_record(self.outcomes, self.rows, self.material)))
        forward = _record(self.outcomes, self.rows,
                          calibration.forward_active_parameters(self.material))
        self.assertEqual(underdetermined(forward), [])
        self.assertEqual(forward["active_parameters"], FORWARD_ACTIVE)
        self.assertIs(forward["production_cutover_authorized"], False)

    def test_diagnostic_only_parameters_cannot_be_swept(self):
        for name in calibration.DIAGNOSTIC_ONLY_PARAMETERS:
            with self.assertRaisesRegex(ValueError, "DIAGNOSTIC_ONLY_ACTIVE_PARAMETERS"):
                calibration.sweep_parameter_sets([name])


if __name__ == "__main__":
    unittest.main()
