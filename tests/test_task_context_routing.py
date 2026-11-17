from __future__ import annotations

import unittest
from pathlib import Path

from tools.dev.task_context import (
    _authority_refs, _current_backlog_priority, _derived_context_boundary, build_task_context,
)
from tools.dev.workflow import CommandResult
from tools.project_sync.governance.context_budget import measure_reference


class TaskContextRoutingTests(unittest.TestCase):
    def test_common_authority_anchors_resolve(self):
        root = Path(__file__).resolve().parents[1]
        common = _authority_refs("developer_workflow")[:4]

        for reference in common:
            with self.subTest(reference=reference):
                measure_reference(root, reference)

    def test_slim_agent_index_preserves_derived_context_boundary(self):
        root = Path(__file__).resolve().parents[1]
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(_derived_context_boundary(agents))
        self.assertFalse(_derived_context_boundary("# Inert instructions\n"))
        self.assertTrue(_derived_context_boundary(
            "Generated ContextDumps are derived context"
        ))

    def test_backlog_priority_is_first_p0_not_stale_following_section(self):
        priority = _current_backlog_priority(
            "## P0 CURRENT — Robot\ntext\n## P0 HISTORICAL — old\n"
        )
        self.assertEqual("DOCUMENTS/BACKLOG.md", priority["source"])
        self.assertEqual("P0 CURRENT — Robot", priority["heading"])
        self.assertEqual("UNRESOLVED", _current_backlog_priority("## P1 Later\n")["heading"])

    def test_actual_checkout_builds_compact_context_with_current_priority(self):
        root = Path(__file__).resolve().parents[1]

        class StubGit:
            def run(self, *args):
                if args == ("branch", "--show-current"):
                    return CommandResult(0, "test-branch\n")
                if args == ("rev-parse", "HEAD"):
                    return CommandResult(0, "test-head\n")
                raise AssertionError(f"unexpected git command: {args}")

        context = build_task_context(root, ["tools/dev/task_context.py"], git=StubGit())
        self.assertEqual("NON_AUTHORITATIVE_DERIVED", context["authority"])
        self.assertEqual("DOCUMENTS/BACKLOG.md", context["project_priority"]["source"])
        self.assertEqual(
            _current_backlog_priority((root / "DOCUMENTS/BACKLOG.md").read_text(encoding="utf-8")),
            context["project_priority"],
        )
        self.assertIn("DOCUMENTS/BACKLOG.md", context["authority_refs"])

    def test_task_context_does_not_route_to_legacy_protocol_heading(self):
        references = _authority_refs("developer_workflow")

        self.assertFalse(any("#28." in reference for reference in references))
        self.assertIn("DOCUMENTS/GITHUB_FIRST_WORKFLOW.md", references)


if __name__ == "__main__":
    unittest.main()
