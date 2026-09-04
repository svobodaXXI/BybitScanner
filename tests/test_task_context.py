from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.dev.task_context import build_task_context
from tools.dev.workflow import CommandResult, Git


class FakeGit(Git):
    def __init__(self, root: Path, head: str = "a" * 40):
        super().__init__(root)
        self.head = head

    def run(self, *args: str) -> CommandResult:
        if args == ("branch", "--show-current"):
            return CommandResult(0, "main\n")
        if args == ("rev-parse", "HEAD"):
            return CommandResult(0, self.head + "\n")
        return CommandResult(1, stderr="unexpected git call")


class TaskContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "DOCUMENTS").mkdir()
        (self.root / "AGENTS.md").write_text(
            "# Staged recovery\nGenerated ContextDumps are non-authoritative.\n", encoding="utf-8"
        )
        (self.root / "DOCUMENTS/ASSISTANT_PROTOCOL.md").write_text(
            "# Protocol\n\nВерсия:\n\n4.18\n", encoding="utf-8"
        )
        (self.root / "DOCUMENTS/PROJECT_STATE.md").write_text(
            """# CURRENT_DEVELOPMENT_PRIORITY

Priority:

TRADING_TERMINAL_TRADING_WORKSPACE

Priority level:

HIGHEST

# TRADING_WORKSPACE_MANUAL_LIVE_TRADING_STATE

Active mission:

CR-TRADING-WORKSPACE-001 — Workspace

Lifecycle state:

IN_PROGRESS

Checkpoint:

STAGE_8

Owning record:

`DOCUMENTS/CHANGE_REQUESTS/CR-TRADING-WORKSPACE-001.md`

Implementation status:

NEXT_SLICE_NOT_AUTHORIZED
""", encoding="utf-8"
        )

    def context(self, path: str, head: str = "a" * 40):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
        return build_task_context(self.root, [path], git=FakeGit(self.root, head))

    def test_narrow_frontend_task(self):
        value = self.context("terminal/frontend/src/App.tsx")
        self.assertEqual(value["task"]["scope_kind"], "frontend")
        self.assertIn("CR-TRADING-WORKSPACE-001", value["current"]["mission"])
        self.assertTrue(any("ARCHITECTURE" in ref for ref in value["authority_refs"]))

    def test_backend_trading_task(self):
        value = self.context("terminal/execution/engine.py")
        self.assertEqual(value["task"]["scope_kind"], "backend_trading")
        self.assertTrue(any("PROJECT_CONTRACTS" in ref for ref in value["authority_refs"]))
        self.assertIn("NOT_AUTHORIZED", value["unresolved_constraints"][0])

    def test_documentation_only_task(self):
        value = self.context("DOCUMENTS/PROJECT_RULES.md")
        self.assertEqual(value["task"]["scope_kind"], "documentation")
        self.assertNotIn("mission", value["current"])

    def test_no_unrelated_authority_leakage(self):
        value = self.context("terminal/frontend/src/App.tsx")
        rendered = str(value)
        self.assertNotIn("SCANNER-GEOMETRY", rendered)
        self.assertNotIn("TRADING-INTELLIGENCE", rendered)
        self.assertLess(len(rendered), 5000)

    def test_changed_head_and_active_cr_are_current(self):
        head = "b" * 40
        value = self.context("terminal/frontend/src/App.tsx", head=head)
        self.assertEqual(value["git"]["head"], head)
        self.assertEqual(value["git"]["last_safe_commit"], head)
        self.assertEqual(value["current"]["checkpoint"], "STAGE_8")

    def test_communication_language_routing_is_machine_readable(self):
        value = self.context("tools/dev/task.py")
        self.assertEqual(value["communication"], {
            "technical_repo": "English",
            "user_confirmations_approvals_safety_actions": "Russian",
            "preserve_literals": True,
            "duplicate_bilingual_statement": False,
        })


if __name__ == "__main__":
    unittest.main()
