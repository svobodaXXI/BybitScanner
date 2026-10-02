"""H4-B: freeze the minimum two-boundary recurrence in calibration policy."""

import json
import unittest

from geometry import consensus_calibration as calibration
from geometry.consensus_gold_report import DEFAULT_SHADOW_REPORT_PARAMETERS
from tests.geometry_gold import ROOT, _load_frame, load_manifest

GOLD = ROOT / "tests" / "fixtures" / "geometry_gold"
H2 = json.loads((GOLD / "calibration_result_v2.json").read_text(encoding="utf-8"))
H4A = load_manifest(GOLD / "source_time_manifest_v6.json")


class StructuralFreezeTests(unittest.TestCase):
    def test_policy_default_cap_and_domain(self):
        frozen = calibration.FROZEN_STRUCTURAL_PARAMETERS
        self.assertEqual(tuple(frozen), ("min_alternating_touches",))
        self.assertEqual(frozen["min_alternating_touches"]["value"], 3)
        self.assertEqual(frozen["min_alternating_touches"]["category"],
                         "STRUCTURAL_INVARIANT")
        self.assertEqual(DEFAULT_SHADOW_REPORT_PARAMETERS["min_alternating_touches"], 3)
        self.assertEqual(calibration.MAX_ACTIVE_PARAMETERS, 6)
        self.assertEqual(len(calibration.CALIBRATABLE_PARAMETER_DOMAIN), 16)

    def test_sensitivity_and_active_set_exclude_structural_parameter(self):
        sets = calibration.sensitivity_parameter_sets()
        self.assertEqual(len(sets), 33)
        self.assertFalse(any("min_alternating_touches=" in label for label, _ in sets))
        self.assertTrue(all(params["min_alternating_touches"] == 3 for _, params in sets))
        outcomes = calibration.expand_outcome_matrix(H2["outcome_matrix"])
        rows, active = calibration.summarize_sensitivity(outcomes, H2["case_ids"])
        self.assertEqual(len(rows), 16)
        self.assertNotIn("min_alternating_touches", [r["parameter"] for r in rows])
        self.assertNotIn("min_alternating_touches", active)
        self.assertEqual(len(active), 6)
        self.assertEqual([r["parameter"] for r in rows],
                         [r["parameter"] for r in H2["sensitivity_summary"]
                          if r["parameter"] != "min_alternating_touches"])

    def test_derived_sets_are_ordered_and_keep_three(self):
        outcomes = calibration.expand_outcome_matrix(H2["outcome_matrix"])
        _, active = calibration.summarize_sensitivity(outcomes, H2["case_ids"])
        first = calibration.derived_parameter_sets(active)
        second = calibration.derived_parameter_sets(active)
        self.assertEqual(first, second)
        sets, grid, invalid = first
        self.assertEqual(list(sets)[:33], [label for label, _ in
                                         calibration.sensitivity_parameter_sets()])
        self.assertEqual(len(grid) + len(invalid), 3 ** 6)
        self.assertTrue(all(params["min_alternating_touches"] == 3
                            for params in sets.values()))
        with self.assertRaisesRegex(ValueError, "NON_CALIBRATABLE_ACTIVE_PARAMETERS"):
            calibration.derived_parameter_sets(["min_alternating_touches"])
        with self.assertRaisesRegex(ValueError, "NON_CALIBRATABLE_ACTIVE_PARAMETERS"):
            calibration.sweep_parameter_sets(["min_alternating_touches"])
        varied = dict(DEFAULT_SHADOW_REPORT_PARAMETERS, min_alternating_touches=4)
        self.assertIn("FROZEN_STRUCTURAL_PARAMETER_VARIED: min_alternating_touches",
                      calibration.validate_parameter_set(varied))

    def test_result_exposes_freeze_without_authorizing_cutover(self):
        outcomes = calibration.expand_outcome_matrix(H2["outcome_matrix"])
        rows, active = calibration.summarize_sensitivity(outcomes, H2["case_ids"])
        cases = [{"case_id": case_id, "timeframe": case_id.split("-")[1][:-1]}
                 for case_id in H2["case_ids"]]
        # Only serialization is exercised here: no grid or calibration run.
        record = calibration.build_calibration_result(
            cases, {case_id: {"calibration_eligible": True,
                              "instrument_symbol": case_id.split("-")[0],
                              "symbol_type": "ordinary"}
                    for case_id in H2["case_ids"]},
            outcomes, sensitivity_rows=rows, active=active, sweep_labels=[],
            invalid_labels=[], parameter_sets=dict(calibration.sensitivity_parameter_sets()),
            determinism={}, performance={})
        self.assertEqual(record["frozen_structural_parameters"],
                         calibration.FROZEN_STRUCTURAL_PARAMETERS)
        self.assertIn("min_alternating_touches", record["frozen_parameters"])
        self.assertNotIn("min_alternating_touches", record["active_parameters"])
        self.assertIs(record["production_cutover_authorized"], False)
        self.assertIsNone(record["proposed_shadow_preset"])

    def test_direct_shadow_diagnostic_overrides_remain_available(self):
        case = next(c for c in H4A["cases"] if c["case_id"].startswith("GRTUSDT-1m-"))
        pinned = H4A["observed_min_alternating_touches_diagnostic"]["new_h4a"]["per_case"][
            case["case_id"]]
        frame = _load_frame(case)
        for tag, value in (("low", 2), ("current", 3), ("high", 4)):
            outcome = calibration.case_outcome(
                case, frame, dict(DEFAULT_SHADOW_REPORT_PARAMETERS,
                                  min_alternating_touches=value))
            self.assertEqual(outcome["selection_status"], pinned[tag]["selection_status"])
            self.assertEqual(outcome["selected_pair_identity"],
                             pinned[tag]["selected_pair_identity"])
        self.assertEqual(pinned["low"], pinned["current"])
        self.assertEqual(pinned["high"]["selection_status"], "NO_ADMISSIBLE_PAIR")


if __name__ == "__main__":
    unittest.main()
