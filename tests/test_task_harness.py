from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.dev.task import finish, start
from tools.dev.workflow import Git


class TaskHarnessTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        root = base / "work"
        origin = base / "origin.git"
        root.mkdir()
        subprocess.run(("git", "init", "--bare", str(origin)), check=True, capture_output=True)
        subprocess.run(("git", "init", "-b", "main"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
        for relative in ("AGENTS.md", "DOCUMENTS/PROJECT_STATE.md", "DOCUMENTS/ASSISTANT_PROTOCOL.md"):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.authority(relative), encoding="utf-8")
        (root / "task.py").write_bytes(b"HEADER = 1\nVALUE = 1\nFOOTER = 1\n")
        (root / "user.txt").write_bytes(b"clean\n")
        subprocess.run(("git", "add", "."), cwd=root, check=True)
        subprocess.run(("git", "commit", "-qm", "initial"), cwd=root, check=True)
        subprocess.run(("git", "remote", "add", "origin", str(origin)), cwd=root, check=True)
        subprocess.run(("git", "push", "-u", "origin", "main"), cwd=root, check=True, capture_output=True)
        return temporary, root

    @staticmethod
    def authority(relative: str) -> str:
        if relative == "AGENTS.md":
            return "Generated ContextDumps are non-authoritative.\n"
        if relative.endswith("ASSISTANT_PROTOCOL.md"):
            return "Version:\n\n1.0\n"
        return "# CURRENT_DEVELOPMENT_PRIORITY\n\nPriority:\n\nACTIVE\n"

    def test_start_and_finish_route_scope_and_standard_report(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        passed, output = start("change value", ["task.py"], git=git, task_id="flow")
        self.assertTrue(passed, output)
        self.assertIn("VERIFICATION AUTO_FROM_SCOPE", output)
        (root / "task.py").write_bytes(b"HEADER = 1\nVALUE = 2\nFOOTER = 1\n")
        passed, output = finish("flow", git=git)
        self.assertTrue(passed, output)
        self.assertEqual(output.splitlines()[0], "STATUS PASS")
        self.assertIn("CHANGED task.py", output)
        self.assertIn("python-compile", output)
        self.assertIn("VERIFIER PASS", output)
        self.assertTrue((root / ".git/bybitscanner/latest-pass.json").is_file())

    def test_finish_rejects_new_out_of_scope_change(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        passed, output = start("change value", ["task.py"], git=git, task_id="scope")
        self.assertTrue(passed, output)
        (root / "task.py").write_bytes(b"HEADER = 1\nVALUE = 2\nFOOTER = 1\n")
        (root / "user.txt").write_bytes(b"not task work\n")
        passed, output = finish("scope", git=git)
        self.assertFalse(passed)
        self.assertIn("out-of-scope worktree changes: user.txt", output)
        self.assertFalse((root / ".git/bybitscanner/latest-pass.json").exists())

    def test_finish_rejects_mutation_of_preexisting_dirty_file(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        (root / "user.txt").write_bytes(b"user baseline\n")
        passed, output = start("change value", ["task.py"], git=git, task_id="owned")
        self.assertTrue(passed, output)
        (root / "task.py").write_bytes(b"HEADER = 1\nVALUE = 2\nFOOTER = 1\n")
        (root / "user.txt").write_bytes(b"overwritten\n")
        passed, output = finish("owned", git=git)
        self.assertFalse(passed)
        self.assertIn("pre-existing user-owned files changed", output)

    def test_start_fails_closed_when_local_head_is_not_origin_main(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        (root / "local.txt").write_text("ahead\n", encoding="utf-8")
        subprocess.run(("git", "add", "local.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-qm", "ahead"), cwd=root, check=True)
        passed, output = start("must stop", ["task.py"], git=git, task_id="ahead")
        self.assertFalse(passed)
        self.assertIn("HEAD does not match origin/main", output)
        self.assertFalse((root / ".git/bybitscanner/tasks/ahead").exists())

    def test_start_invalidates_previous_pass_receipt(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        receipt = root / ".git/bybitscanner/latest-pass.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text('{"status":"PASS"}\n', encoding="utf-8")
        passed, output = start("new task", ["task.py"], git=git, task_id="fresh")
        self.assertTrue(passed, output)
        self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
