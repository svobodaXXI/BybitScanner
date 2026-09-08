from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.dev.task import _sync_preflight
from tools.dev.task_transaction import begin
from tools.dev.verify import verify
from tools.dev.workflow import Git


class HarnessLeanWorkflowTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        root = base / "work"
        origin = base / "origin.git"
        root.mkdir()
        subprocess.run(("git", "init", "--bare", str(origin)), check=True, capture_output=True)
        subprocess.run(("git", "init", "-b", "main"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
        (root / ".gitattributes").write_text("*.txt text eol=lf\n", encoding="utf-8")
        (root / "task.txt").write_text("base\n", encoding="utf-8")
        (root / "docs.txt").write_text("docs\n", encoding="utf-8")
        subprocess.run(("git", "add", ".gitattributes", "task.txt", "docs.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-qm", "initial"), cwd=root, check=True)
        subprocess.run(("git", "remote", "add", "origin", str(origin)), cwd=root, check=True)
        subprocess.run(("git", "push", "-u", "origin", "main"), cwd=root, check=True, capture_output=True)
        return temporary, root, origin

    def test_sync_preflight_accepts_synced_feature_branch(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        subprocess.run(("git", "switch", "-c", "feature/harness"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "push", "-u", "origin", "feature/harness"), cwd=root, check=True, capture_output=True)

        _sync_preflight(Git(root))

    def test_sync_preflight_rejects_feature_branch_that_is_not_mirrored(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        subprocess.run(("git", "switch", "-c", "feature/local-only"), cwd=root, check=True, capture_output=True)

        with self.assertRaisesRegex(RuntimeError, "no origin mirror"):
            _sync_preflight(Git(root))

    def test_crlf_only_declared_scope_is_not_a_candidate_change(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        begin(["task.txt", "docs.txt"], git=git, task_id="crlf-scope")
        (root / "task.txt").write_bytes(b"task\n")
        (root / "docs.txt").write_bytes(b"docs\r\n")

        passed, output = verify(["task.txt", "docs.txt"], git=git, transaction_id="crlf-scope")

        self.assertTrue(passed, output)
        receipt = json.loads((root / ".git/bybitscanner/latest-pass.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["transaction"]["candidate_files"], ["task.txt"])

    def test_failed_check_reports_its_detail_immediately(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        (root / "task.txt").write_text("changed\n", encoding="utf-8")

        passed, output = verify(
            ["task.txt"],
            git=Git(root),
            additional_commands=[{
                "label": "forced-fail",
                "cwd": ".",
                "argv": [sys.executable, "-c", "print('boom'); raise SystemExit(1)"],
            }],
        )

        self.assertFalse(passed)
        self.assertIn("FAILED forced-fail", output)
        self.assertIn("BLOCKERS forced-fail: boom", output)


if __name__ == "__main__":
    unittest.main()
