import copy
import unittest
from pathlib import Path

from tools.project_sync.governance.change_request import (
    load_change_request,
    validate_change_request,
)


ROOT = Path(__file__).resolve().parents[1]
CURRENT_REQUEST = ROOT / "DOCUMENTS" / "CHANGE_REQUESTS" / "CR-DOC-AI-CONTEXT-001.md"


class ChangeRequestGovernanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = load_change_request(CURRENT_REQUEST)

    def test_current_change_request_is_valid(self):
        result = validate_change_request(self.valid)
        self.assertTrue(result.valid, result.errors)

    def test_missing_required_identity_fails(self):
        data = copy.deepcopy(self.valid)
        del data["id"]
        result = validate_change_request(data)
        self.assertFalse(result.valid)
        self.assertIn("Missing or empty text field: id", result.errors)

    def test_invalid_status_and_revision_fail(self):
        data = copy.deepcopy(self.valid)
        data["status"] = "MAYBE"
        data["revision"] = "latest"
        result = validate_change_request(data)
        self.assertFalse(result.valid)
        self.assertIn("Invalid status: MAYBE", result.errors)
        self.assertIn("Invalid revision: latest", result.errors)

    def test_missing_scope_and_verification_fail(self):
        data = copy.deepcopy(self.valid)
        data["approved_scope"] = []
        data["verification_requirements"] = []
        result = validate_change_request(data)
        self.assertFalse(result.valid)
        self.assertIn("Required list must not be empty: approved_scope", result.errors)
        self.assertIn("Required list must not be empty: verification_requirements", result.errors)

    def test_inconsistent_phase_and_implementation_status_fail(self):
        data = copy.deepcopy(self.valid)
        data["current_checkpoint"] = "PHASE_2_COMPLETED"
        data["implementation_status"] = "PHASE_2_IN_PROGRESS"
        data["next_phase"] = "PHASE_1"
        result = validate_change_request(data)
        self.assertFalse(result.valid)
        self.assertIn("Completed checkpoint is inconsistent with implementation_status", result.errors)
        self.assertIn("next_phase must follow current_phase", result.errors)

    def test_malformed_related_commit_fails(self):
        data = copy.deepcopy(self.valid)
        data["related_commits"] = [{"phase": "PHASE_1", "commit": "not-a-commit"}]
        result = validate_change_request(data)
        self.assertFalse(result.valid)
        self.assertIn("Malformed related commit at index 0", result.errors)


if __name__ == "__main__":
    unittest.main()
