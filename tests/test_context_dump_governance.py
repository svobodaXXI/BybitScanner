import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.project_sync.governance.context_dump import (
    ContextDumpError,
    GitState,
    build_context_dump,
    generate_context_dump,
)


FIXED_GIT = GitState("main", "a" * 40, (" M scoped.py", "?? unrelated.tmp"))
FIXED_TIME = "2026-08-17T12:00:00+00:00"


def _request_metadata() -> dict:
    return {
        "schema_version": "1.0",
        "id": "CR-TEST-001",
        "title": "Context test",
        "status": "IN_PROGRESS",
        "revision": "1.0",
        "lifecycle_stage": "IMPLEMENT",
        "objective": "Generate only task-scoped context.",
        "non_goals": ["Unrelated work"],
        "approved_scope": ["Scoped generator"],
        "prohibited_scope": ["Production code"],
        "authoritative_references": ["DOCUMENTS/AUTHORITY.md#CONTRACT-TEST"],
        "context_scope_paths": ["scoped.py"],
        "context_test_paths": ["tests/test_scoped.py"],
        "context_excerpt_references": ["DOCUMENTS/AUTHORITY.md#CONTRACT-TEST"],
        "approved_decisions": ["Derived only"],
        "unresolved_decisions": [],
        "acceptance_criteria": ["Scoped output"],
        "verification_requirements": ["Focused test"],
        "risks": ["Staleness"],
        "rollback_boundaries": ["Single commit"],
        "implementation_phases": [
            {"id": "PHASE_1", "status": "COMPLETED"},
            {"id": "PHASE_2", "status": "IN_PROGRESS"},
        ],
        "current_phase": "PHASE_1",
        "current_checkpoint": "PHASE_1_COMPLETED",
        "implementation_status": "PHASE_1_IMPLEMENTED_VERIFIED",
        "next_phase": "PHASE_2",
        "next_phase_authorization": "NOT_AUTHORIZED",
        "related_commits": [{"commit": "abcdef0"}],
        "amendment_history": [],
    }


class ContextDumpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "DOCUMENTS/CHANGE_REQUESTS").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "scoped.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "tests/test_scoped.py").write_text("# focused\n", encoding="utf-8")
        (self.root / "DOCUMENTS/AUTHORITY.md").write_text(
            "# CONTRACT-TEST\n\nOnly this excerpt.\n\n# UNRELATED\n\nMust not appear.\n",
            encoding="utf-8",
        )
        (self.root / "DOCUMENTS/LEGACY_WARNINGS.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "registry_id": "TEST",
                    "warnings": [
                        {
                            "warning_id": "LW-TEST",
                            "status": "LEGACY",
                            "severity": "ADVISORY",
                            "affected_paths": ["scoped.py"],
                            "affected_symbols": [],
                            "replacement_available": True,
                            "canonical_replacement": "new.py",
                            "new_usage_prohibited": False,
                            "reason": "Scoped legacy path.",
                            "compatibility_boundary": "Read only.",
                            "retention_policy": "Keep.",
                            "introduced_revision": "abcdef0",
                            "last_validated_revision": "abcdef0",
                            "owner": "Tests",
                            "retirement_conditions": "Explicit approval.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.request_path = self.root / "DOCUMENTS/CHANGE_REQUESTS/CR-TEST-001.md"
        self._write_request(_request_metadata())

    def tearDown(self):
        self.temp.cleanup()

    def _write_request(self, metadata: dict) -> None:
        self.request_path.write_text(
            "# Request\n\n<!-- CHANGE_REQUEST_METADATA_BEGIN -->\n```json\n"
            + json.dumps(metadata, indent=2)
            + "\n```\n<!-- CHANGE_REQUEST_METADATA_END -->\n",
            encoding="utf-8",
        )

    def _source_hashes(self) -> dict[str, str]:
        return {
            str(path.relative_to(self.root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                self.request_path,
                self.root / "DOCUMENTS/AUTHORITY.md",
                self.root / "DOCUMENTS/LEGACY_WARNINGS.json",
            )
        }

    def test_build_is_deterministic_scoped_and_contains_provenance(self):
        first = build_context_dump(
            self.root, self.request_path, git_state=FIXED_GIT, generated_at=FIXED_TIME
        )
        second = build_context_dump(
            self.root, self.request_path, git_state=FIXED_GIT, generated_at=FIXED_TIME
        )
        self.assertEqual(first, second)
        self.assertIn("NON-AUTHORITATIVE DERIVED ARTIFACT", first)
        self.assertIn('"source_revision": "' + "a" * 40 + '"', first)
        self.assertIn('"task_revision": "1.0"', first)
        self.assertIn('"change_request_source"', first)
        self.assertIn('"scoped_files"', first)
        self.assertIn("scoped.py", first)
        self.assertIn("tests/test_scoped.py", first)
        self.assertIn("LW-TEST", first)
        self.assertIn("Only this excerpt.", first)
        self.assertNotIn("Must not appear.", first)
        self.assertNotIn("unrelated.tmp", first)
        self.assertLess(len(first.encode("utf-8")), 30 * 1024)

    def test_generation_uses_canonical_location_without_mutating_sources(self):
        before = self._source_hashes()
        output = generate_context_dump(
            self.root,
            self.request_path,
            git_state=FIXED_GIT,
            generated_at=FIXED_TIME,
        )
        self.assertEqual(output, self.root / "runtime/context/CR-TEST-001.md")
        self.assertTrue(output.is_file())
        self.assertEqual(before, self._source_hashes())

    def test_missing_scope_fails_clearly_and_writes_nothing(self):
        metadata = copy.deepcopy(_request_metadata())
        del metadata["context_scope_paths"]
        self._write_request(metadata)
        with self.assertRaisesRegex(ContextDumpError, "context_scope_paths"):
            generate_context_dump(
                self.root,
                self.request_path,
                git_state=FIXED_GIT,
                generated_at=FIXED_TIME,
            )
        self.assertFalse((self.root / "runtime/context").exists())

    def test_unresolved_authority_section_fails_clearly(self):
        metadata = copy.deepcopy(_request_metadata())
        metadata["context_excerpt_references"] = [
            "DOCUMENTS/AUTHORITY.md#MISSING-CONTRACT"
        ]
        metadata["authoritative_references"].append(
            "DOCUMENTS/AUTHORITY.md#MISSING-CONTRACT"
        )
        self._write_request(metadata)
        with self.assertRaisesRegex(ContextDumpError, "cannot be resolved"):
            build_context_dump(
                self.root,
                self.request_path,
                git_state=FIXED_GIT,
                generated_at=FIXED_TIME,
            )


if __name__ == "__main__":
    unittest.main()
