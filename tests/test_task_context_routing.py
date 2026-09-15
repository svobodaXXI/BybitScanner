from __future__ import annotations

import unittest
from pathlib import Path

from tools.dev.task_context import _authority_refs
from tools.project_sync.governance.context_budget import measure_reference


class TaskContextRoutingTests(unittest.TestCase):
    def test_common_authority_anchors_resolve(self):
        root = Path(__file__).resolve().parents[1]
        common = _authority_refs("developer_workflow")[:4]

        for reference in common:
            with self.subTest(reference=reference):
                measure_reference(root, reference)

    def test_task_context_does_not_route_to_legacy_protocol_heading(self):
        references = _authority_refs("developer_workflow")

        self.assertFalse(any("#28." in reference for reference in references))
        self.assertIn("DOCUMENTS/GITHUB_FIRST_WORKFLOW.md", references)


if __name__ == "__main__":
    unittest.main()
