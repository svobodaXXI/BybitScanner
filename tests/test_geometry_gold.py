"""RVL-G2 compact Geometry Gold seed.

The five initial cases are all READY in DOCUMENTS/GEOMETRY_GOLD_INVENTORY.md.
No RECOVERABLE or VISUAL_ONLY case is promoted here.
"""

import unittest

from tests.geometry_gold import load_manifest, run_geometry_gold


class GeometryGoldSeedTests(unittest.TestCase):
    def test_manifest_contains_only_the_first_five_ready_cases(self):
        manifest = load_manifest()
        cases = manifest["cases"]
        self.assertEqual(len(cases), 5)
        self.assertEqual(
            [case["case_id"] for case in cases],
            [
                "PONS-formation-fit-positive-anchor",
                "1000BONKUSDT-wrong-anchor-negative",
                "1000TOSHIUSDT-locality-invariant",
                "1000XECUSDT-no-local-formation",
                "AEVO-formation-fit-negative",
            ],
        )
        self.assertTrue(all(case["evidence_class"] == "READY" for case in cases))

    def test_all_seed_cases_match_current_production_geometry(self):
        results = run_geometry_gold()
        failures = [result for result in results if not result["passed"]]
        self.assertEqual(failures, [], failures)

    def test_runner_is_deterministic(self):
        self.assertEqual(run_geometry_gold(), run_geometry_gold())


if __name__ == "__main__":
    unittest.main()
