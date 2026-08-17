import copy
import unittest
from pathlib import Path

from tools.project_sync.governance.legacy_warning import (
    enforce_scoped_warnings,
    load_registry,
    query_warnings,
    validate_registry,
    warning_level,
)


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "DOCUMENTS" / "LEGACY_WARNINGS.json"


class LegacyWarningGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = load_registry(REGISTRY_PATH)

    def test_current_registry_is_valid_and_blocking_is_machine_visible(self):
        result = validate_registry(self.registry)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual("BLOCKING", result.status)
        self.assertEqual(1, result.blocking_count)
        self.assertEqual(1, result.advisory_count)

    def test_valid_advisory_entry_is_recognized(self):
        data = copy.deepcopy(self.registry)
        data["warnings"] = [data["warnings"][1]]
        result = validate_registry(data)
        self.assertTrue(result.valid, result.errors)
        self.assertEqual("ADVISORY", result.status)

    def test_malformed_warning_fails(self):
        data = copy.deepcopy(self.registry)
        warning = data["warnings"][0]
        warning["status"] = "OLD"
        warning["severity"] = "DANGER"
        warning["affected_paths"] = []
        warning["new_usage_prohibited"] = "yes"
        result = validate_registry(data)
        self.assertFalse(result.valid)
        self.assertEqual("FAIL", result.status)
        self.assertTrue(any("invalid status" in error for error in result.errors))
        self.assertTrue(any("invalid severity" in error for error in result.errors))
        self.assertTrue(any("no usable path or symbol scope" in error for error in result.errors))

    def test_missing_warning_id_fails(self):
        data = copy.deepcopy(self.registry)
        del data["warnings"][0]["warning_id"]
        result = validate_registry(data)
        self.assertFalse(result.valid)
        self.assertTrue(any("missing or empty field: warning_id" in error for error in result.errors))

    def test_blocking_warning_must_prohibit_new_usage(self):
        data = copy.deepcopy(self.registry)
        data["warnings"][0]["new_usage_prohibited"] = False
        result = validate_registry(data)
        self.assertFalse(result.valid)
        self.assertTrue(any("BLOCKING warning must prohibit" in error for error in result.errors))

    def test_claimed_replacement_must_be_present(self):
        data = copy.deepcopy(self.registry)
        data["warnings"][0]["canonical_replacement"] = ""
        result = validate_registry(data)
        self.assertFalse(result.valid)
        self.assertTrue(any("canonical_replacement is missing" in error for error in result.errors))

    def test_duplicate_warning_id_fails(self):
        data = copy.deepcopy(self.registry)
        data["warnings"].append(copy.deepcopy(data["warnings"][0]))
        result = validate_registry(data)
        self.assertFalse(result.valid)
        self.assertIn("Duplicate warning_id: LW-WEDGE-LEGACY-001", result.errors)

    def test_path_query_returns_blocking_warning(self):
        warnings = query_warnings(self.registry, path="wedge_legacy.py")
        self.assertEqual(["LW-WEDGE-LEGACY-001"], [item["warning_id"] for item in warnings])
        self.assertEqual("BLOCKING", warning_level(warnings))

    def test_path_query_normalizes_windows_separator(self):
        warnings = query_warnings(self.registry, path=r".\wedge_legacy_root.py")
        self.assertEqual("BLOCKING", warning_level(warnings))

    def test_symbol_query_returns_applicable_warning(self):
        data = copy.deepcopy(self.registry)
        data["warnings"][0]["affected_symbols"] = ["LegacyWedgeDetector"]
        warnings = query_warnings(data, symbol="LegacyWedgeDetector")
        self.assertEqual("BLOCKING", warning_level(warnings))

    def test_unmatched_query_passes(self):
        self.assertEqual("PASS", warning_level(query_warnings(self.registry, path="main.py")))

    def test_scoped_enforcement_is_deterministic_and_blocking(self):
        result = enforce_scoped_warnings(
            self.registry,
            paths=["main.py", "wedge_legacy.py", "wedge_legacy.py"],
        )
        self.assertTrue(result.blocking)
        self.assertEqual("BLOCKING", result.status)
        self.assertEqual(
            ["LW-WEDGE-LEGACY-001"],
            [warning["warning_id"] for warning in result.warnings],
        )

    def test_scoped_advisory_enforcement_is_non_blocking(self):
        result = enforce_scoped_warnings(self.registry, paths=["SNAPSHOT.md"])
        self.assertFalse(result.blocking)
        self.assertEqual("ADVISORY", result.status)


if __name__ == "__main__":
    unittest.main()
