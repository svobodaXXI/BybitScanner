import ast
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.project_sync.governance.codex_workflow import (
    NON_AUTHORITATIVE_CONTEXT,
    context_generation_is_appropriate,
    prepare_durable,
    prepare_lightweight,
)
from tools.project_sync.governance.context_dump import GitState, generate_context_dump


FIXED_GIT = GitState("main", "a" * 40, (" M scoped.py", "?? unrelated.tmp"))
WARNING_TEMPLATE = {
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


def request_metadata() -> dict:
    return {
        "schema_version": "1.0",
        "id": "CR-TEST-001",
        "title": "Workflow test",
        "status": "IN_PROGRESS",
        "revision": "1.0",
        "lifecycle_stage": "IMPLEMENT",
        "objective": "Exercise scoped workflow.",
        "non_goals": ["Production behavior"],
        "approved_scope": ["scoped.py"],
        "prohibited_scope": ["main.py"],
        "authoritative_references": ["DOCUMENTS/AUTHORITY.md#CONTRACT-TEST"],
        "context_scope_paths": ["scoped.py"],
        "context_test_paths": ["tests/test_scoped.py"],
        "context_excerpt_references": ["DOCUMENTS/AUTHORITY.md#CONTRACT-TEST"],
        "approved_decisions": ["Scoped only"],
        "unresolved_decisions": [],
        "acceptance_criteria": ["Deterministic gate"],
        "verification_requirements": ["Focused tests"],
        "risks": ["Stale context"],
        "rollback_boundaries": ["One commit"],
        "implementation_phases": [
            {"id": "PHASE_1", "status": "COMPLETED"},
            {"id": "PHASE_2", "status": "NOT_STARTED"},
        ],
        "current_phase": "PHASE_1",
        "current_checkpoint": "PHASE_1_COMPLETED",
        "implementation_status": "PHASE_1_IMPLEMENTED_VERIFIED",
        "next_phase": "PHASE_2",
        "next_phase_authorization": "NOT_AUTHORIZED",
        "related_commits": [{"commit": "abcdef0"}],
        "amendment_history": [],
    }


class CodexWorkflowGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "DOCUMENTS/CHANGE_REQUESTS").mkdir(parents=True)
        (self.root / "tests").mkdir()
        (self.root / "scoped.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.root / "tests/test_scoped.py").write_text("# test\n", encoding="utf-8")
        (self.root / "DOCUMENTS/AUTHORITY.md").write_text(
            "# CONTRACT-TEST\n\nScoped authority.\n", encoding="utf-8"
        )
        self.request = self.root / "DOCUMENTS/CHANGE_REQUESTS/CR-TEST-001.md"
        self._write_request(request_metadata())
        self._write_warnings([])

    def tearDown(self):
        self.temp.cleanup()

    def _write_request(self, metadata: dict) -> None:
        self.request.write_text(
            "# Request\n\n<!-- CHANGE_REQUEST_METADATA_BEGIN -->\n```json\n"
            + json.dumps(metadata, indent=2)
            + "\n```\n<!-- CHANGE_REQUEST_METADATA_END -->\n",
            encoding="utf-8",
        )

    def _write_warnings(self, warnings: list[dict]) -> None:
        (self.root / "DOCUMENTS/LEGACY_WARNINGS.json").write_text(
            json.dumps(
                {"schema_version": "1.0", "registry_id": "TEST", "warnings": warnings}
            ),
            encoding="utf-8",
        )

    def _warning(self, *, blocking: bool = False) -> dict:
        warning = copy.deepcopy(WARNING_TEMPLATE)
        if blocking:
            warning["severity"] = "BLOCKING"
            warning["new_usage_prohibited"] = True
        return warning

    def _generate(self) -> Path:
        return generate_context_dump(
            self.root,
            self.request,
            git_state=FIXED_GIT,
            generated_at="2026-08-18T00:00:00+00:00",
        )

    def test_lightweight_without_context_uses_direct_recovery(self):
        decision = prepare_lightweight(self.root, paths=["scoped.py"])
        self.assertTrue(decision.continuation_allowed)
        self.assertEqual("PASS", decision.status)
        self.assertEqual("DIRECT_SCOPED_RECOVERY", decision.recovery)
        self.assertIsNone(decision.context_path)

    def test_lightweight_advisory_is_visible_and_allowed(self):
        self._write_warnings([self._warning()])
        decision = prepare_lightweight(self.root, paths=["scoped.py"])
        self.assertEqual("ADVISORY", decision.status)
        self.assertTrue(decision.continuation_allowed)
        self.assertEqual(("LW-TEST",), decision.warning_ids)

    def test_lightweight_blocking_warning_fails(self):
        self._write_warnings([self._warning(blocking=True)])
        decision = prepare_lightweight(self.root, paths=["scoped.py"])
        self.assertEqual("BLOCKING", decision.status)
        self.assertFalse(decision.continuation_allowed)
        self.assertEqual(2, decision.exit_code)

    def test_durable_change_request_can_use_direct_recovery(self):
        decision = prepare_durable(self.root, self.request)
        self.assertEqual("PASS", decision.status)
        self.assertEqual("DURABLE", decision.task_kind)
        self.assertEqual("DIRECT_SCOPED_RECOVERY", decision.recovery)

    def test_durable_fresh_context_permits_implementation(self):
        context = self._generate()
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=FIXED_GIT
        )
        self.assertEqual("PASS", decision.status)
        self.assertTrue(decision.continuation_allowed)

    def test_stale_context_blocks_implementation(self):
        context = self._generate()
        (self.root / "scoped.py").write_text("VALUE = 2\n", encoding="utf-8")
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=FIXED_GIT
        )
        self.assertEqual("STALE", decision.status)
        self.assertFalse(decision.continuation_allowed)
        self.assertEqual(1, decision.exit_code)

    def test_invalid_context_blocks_implementation(self):
        invalid = self.root / "invalid-context.md"
        invalid.write_text("not a ContextDump", encoding="utf-8")
        decision = prepare_durable(
            self.root, self.request, context_path=invalid, git_state=FIXED_GIT
        )
        self.assertEqual("FAIL", decision.status)
        self.assertFalse(decision.continuation_allowed)

    def test_advisory_context_permits_continuation(self):
        self._write_warnings([self._warning()])
        context = self._generate()
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=FIXED_GIT
        )
        self.assertEqual("ADVISORY", decision.status)
        self.assertTrue(decision.continuation_allowed)

    def test_blocking_context_warning_blocks_continuation(self):
        self._write_warnings([self._warning(blocking=True)])
        context = self._generate()
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=FIXED_GIT
        )
        self.assertEqual("BLOCKING", decision.status)
        self.assertFalse(decision.continuation_allowed)

    def test_missing_context_falls_back_to_direct_recovery(self):
        decision = prepare_durable(self.root, self.request)
        self.assertEqual("DIRECT_SCOPED_RECOVERY", decision.recovery)
        self.assertTrue(decision.continuation_allowed)

    def test_missing_context_does_not_bypass_warning_enforcement(self):
        self._write_warnings([self._warning(blocking=True)])
        decision = prepare_durable(self.root, self.request)
        self.assertEqual("BLOCKING", decision.status)
        self.assertFalse(decision.continuation_allowed)

    def test_unrelated_dirty_paths_do_not_block_scoped_context(self):
        context = self._generate()
        changed_unrelated = GitState(
            "main", "a" * 40, (" M scoped.py", "?? another-unrelated.tmp")
        )
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=changed_unrelated
        )
        self.assertEqual("PASS", decision.status)

    def test_context_is_explicitly_non_authoritative(self):
        context = self._generate()
        decision = prepare_durable(
            self.root, self.request, context_path=context, git_state=FIXED_GIT
        )
        self.assertEqual(NON_AUTHORITATIVE_CONTEXT, decision.context_authority)

    def test_interruption_context_decision_is_deterministic(self):
        first = context_generation_is_appropriate(recovery_package=True)
        second = context_generation_is_appropriate(recovery_package=True)
        self.assertTrue(first)
        self.assertEqual(first, second)
        self.assertFalse(context_generation_is_appropriate())

    def test_generation_reuses_existing_context_components(self):
        generated = self.root / "runtime/context/CR-TEST-001.md"
        generated.parent.mkdir(parents=True)
        generated.write_text("derived", encoding="utf-8")
        validation = type(
            "Result",
            (),
            {"status": "PASS", "reasons": (), "warning_ids": ()},
        )()
        with patch(
            "tools.project_sync.governance.codex_workflow.generate_context_dump",
            return_value=generated,
        ) as generate, patch(
            "tools.project_sync.governance.codex_workflow.validate_context_dump",
            return_value=validation,
        ) as validate:
            decision = prepare_durable(
                self.root, self.request, explicitly_requested=True, git_state=FIXED_GIT
            )
        generate.assert_called_once()
        validate.assert_called_once()
        self.assertEqual("GENERATED_CONTEXT", decision.recovery)

    def test_production_subsystems_are_not_imported(self):
        module_path = (
            Path(__file__).resolve().parents[1]
            / "tools/project_sync/governance/codex_workflow.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        )
        forbidden = ("geometry", "wedge", "signal", "telegram", "market", "chart")
        self.assertFalse(any(name.startswith(forbidden) for name in imports), imports)


if __name__ == "__main__":
    unittest.main()
