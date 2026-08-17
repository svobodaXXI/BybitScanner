import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.project_sync.governance.context_dump import (
    ContextDumpError,
    GitState,
    VALIDATION_EXIT_CODES,
    build_context_dump,
    generate_context_dump,
    validate_context_dump,
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

    def _generate(self, git_state: GitState = FIXED_GIT) -> Path:
        return generate_context_dump(
            self.root,
            self.request_path,
            git_state=git_state,
            generated_at=FIXED_TIME,
        )

    def _registry(self) -> dict:
        return json.loads(
            (self.root / "DOCUMENTS/LEGACY_WARNINGS.json").read_text(encoding="utf-8")
        )

    def _write_registry(self, registry: dict) -> None:
        (self.root / "DOCUMENTS/LEGACY_WARNINGS.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )

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

    def test_fresh_advisory_context_is_valid_and_non_blocking(self):
        output = self._generate()
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertTrue(result.valid)
        self.assertEqual("ADVISORY", result.status)
        self.assertEqual(("LW-TEST",), result.warning_ids)
        self.assertEqual(0, VALIDATION_EXIT_CODES[result.status])

    def test_applicable_blocking_warning_is_machine_blocking(self):
        registry = self._registry()
        registry["warnings"][0]["severity"] = "BLOCKING"
        registry["warnings"][0]["new_usage_prohibited"] = True
        self._write_registry(registry)
        output = self._generate()
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertFalse(result.valid)
        self.assertEqual("BLOCKING", result.status)
        self.assertEqual(2, VALIDATION_EXIT_CODES[result.status])

    def test_task_revision_branch_and_head_changes_are_stale(self):
        output = self._generate()
        metadata = _request_metadata()
        metadata["revision"] = "1.1"
        self._write_request(metadata)
        result = validate_context_dump(
            self.root,
            output,
            self.request_path,
            git_state=GitState("feature", "b" * 40, FIXED_GIT.status_short),
        )
        self.assertEqual("STALE", result.status)
        self.assertIn("task revision changed", result.reasons)
        self.assertIn("branch changed", result.reasons)
        self.assertIn("HEAD changed", result.reasons)
        self.assertIn("ChangeRequest content changed", result.reasons)
        self.assertEqual(1, VALIDATION_EXIT_CODES[result.status])

    def test_authority_and_scoped_file_changes_are_stale(self):
        output = self._generate()
        (self.root / "DOCUMENTS/AUTHORITY.md").write_text(
            "# CONTRACT-TEST\n\nChanged.\n", encoding="utf-8"
        )
        (self.root / "scoped.py").write_text("VALUE = 2\n", encoding="utf-8")
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertEqual("STALE", result.status)
        self.assertIn("authoritative source content changed", result.reasons)
        self.assertIn("scoped file content changed", result.reasons)

    def test_relevant_warning_change_is_stale(self):
        output = self._generate()
        registry = self._registry()
        registry["warnings"][0]["reason"] = "Changed warning."
        self._write_registry(registry)
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertEqual("STALE", result.status)
        self.assertIn("relevant LegacyWarning state changed", result.reasons)

    def test_unrelated_warning_change_does_not_make_context_stale(self):
        output = self._generate()
        registry = self._registry()
        unrelated = copy.deepcopy(registry["warnings"][0])
        unrelated["warning_id"] = "LW-UNRELATED"
        unrelated["affected_paths"] = ["unrelated.py"]
        registry["warnings"].append(unrelated)
        self._write_registry(registry)
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertEqual("ADVISORY", result.status)

    def test_unrelated_dirty_state_does_not_make_context_stale(self):
        output = self._generate()
        changed_unrelated = GitState(
            "main", "a" * 40, (" M scoped.py", "?? another-unrelated.tmp")
        )
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=changed_unrelated
        )
        self.assertEqual("ADVISORY", result.status)

    def test_malformed_context_is_explicit_failure(self):
        output = self.root / "bad.md"
        output.write_text("not context", encoding="utf-8")
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertEqual("FAIL", result.status)
        self.assertEqual(1, VALIDATION_EXIT_CODES[result.status])

    def test_unknown_context_schema_is_explicit_failure(self):
        output = self._generate()
        content = output.read_text(encoding="utf-8").replace(
            '"schema_version": "1.1"', '"schema_version": "9.9"', 1
        )
        output.write_text(content, encoding="utf-8")
        result = validate_context_dump(
            self.root, output, self.request_path, git_state=FIXED_GIT
        )
        self.assertEqual("FAIL", result.status)

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
