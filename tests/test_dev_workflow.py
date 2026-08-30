from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tools.dev.checkpoint import checkpoint
from tools.dev.task_transaction import begin, candidate_root
from tools.dev.verify import verify
from tools.dev.workflow import CommandResult, Git, fingerprints


class FakeGit(Git):
    def __init__(self, root: Path, *, head: str = "a" * 40, staged: str = ""):
        super().__init__(root)
        self.head = head
        self.staged = staged
        self.calls: list[tuple[str, ...]] = []
        self.fail_at: str | None = None

    def run(self, *args: str) -> CommandResult:
        self.calls.append(args)
        operation = args[0]
        if self.fail_at == operation:
            return CommandResult(1, stderr=f"forced {operation} failure")
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return CommandResult(0, str(self.root))
        if args[:2] == ("rev-parse", "--git-dir"):
            return CommandResult(0, str(self.root / ".git"))
        if args[:2] == ("branch", "--show-current"):
            return CommandResult(0, "main\n")
        if args[:2] == ("rev-parse", "HEAD"):
            return CommandResult(0, self.head + "\n")
        if args[:4] == ("diff", "--cached", "--name-only", "-z"):
            return CommandResult(0, self.staged)
        if operation == "add":
            self.staged = "task.py\0"
            return CommandResult(0)
        if args[:3] == ("diff", "--cached", "--check"):
            return CommandResult(0)
        if operation == "commit":
            self.head = "b" * 40
            return CommandResult(0)
        if operation == "push":
            return CommandResult(0)
        if operation == "ls-remote":
            return CommandResult(0, f"{self.head}\trefs/heads/main\n")
        return CommandResult(0)


class DevWorkflowTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        subprocess.run(("git", "init", "-b", "main"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
        (root / "task.py").write_text("VALUE = 1\n", encoding="utf-8")
        subprocess.run(("git", "add", "task.py"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-m", "initial"), cwd=root, check=True, capture_output=True)
        return temporary, root

    def write_receipt(self, root: Path, git: FakeGit) -> None:
        target = root / ".git" / "bybitscanner" / "latest-pass.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "status": "PASS", "branch": "main", "head": "a" * 40,
            "task_paths": ["task.py"], "files": ["task.py"],
            "fingerprints": fingerprints(root, ["task.py"]), "checks": [],
        }), encoding="utf-8")

    def test_pass_writes_verification_receipt(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        passed, output = verify(["task.py"], git=Git(root))
        self.assertTrue(passed, output)
        receipt = json.loads((root / ".git/bybitscanner/latest-pass.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["task_paths"], ["task.py"])
        self.assertEqual(receipt["branch"], "main")
        self.assertTrue(receipt["checks"])

    def test_stale_head_is_rejected_before_staging(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = FakeGit(root, head="c" * 40)
        self.write_receipt(root, git)
        passed, output = checkpoint("checkpoint", git=git)
        self.assertFalse(passed)
        self.assertIn("HEAD changed", output)
        self.assertFalse(any(call[0] == "add" for call in git.calls))

    def test_stale_content_is_rejected_before_staging(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = FakeGit(root)
        self.write_receipt(root, git)
        (root / "task.py").write_text("VALUE = 2\n", encoding="utf-8")
        passed, output = checkpoint("checkpoint", git=git)
        self.assertFalse(passed)
        self.assertIn("content changed", output)
        self.assertFalse(any(call[0] == "add" for call in git.calls))

    def test_unexpected_staged_file_is_rejected(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = FakeGit(root, staged="unrelated.txt\0")
        self.write_receipt(root, git)
        passed, output = checkpoint("checkpoint", git=git)
        self.assertFalse(passed)
        self.assertIn("unexpected staged files", output)
        self.assertFalse(any(call[0] == "add" for call in git.calls))

    def test_exact_path_staging_preserves_unrelated_dirty_and_untracked(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        unrelated = root / "unrelated.txt"
        unrelated.write_text("user work\n", encoding="utf-8")
        git = FakeGit(root)
        self.write_receipt(root, git)
        passed, output = checkpoint("checkpoint", git=git)
        self.assertTrue(passed, output)
        add_calls = [call for call in git.calls if call[0] == "add"]
        self.assertEqual(add_calls, [("add", "--", "task.py")])
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "user work\n")
        forbidden = {"clean", "reset", "restore", "checkout"}
        self.assertFalse(any(call[0] in forbidden for call in git.calls))

    def test_failure_stops_before_next_unsafe_action(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = FakeGit(root)
        git.fail_at = "commit"
        self.write_receipt(root, git)
        passed, output = checkpoint("checkpoint", git=git)
        self.assertFalse(passed)
        self.assertIn("commit failed", output)
        self.assertFalse(any(call[0] in {"push", "ls-remote"} for call in git.calls))

    def test_verify_checkpoint_cli_end_to_end_with_local_origin(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        root = base / "work"
        origin = base / "origin.git"
        root.mkdir()
        subprocess.run(("git", "init", "--bare", str(origin)), check=True, capture_output=True)
        subprocess.run(("git", "init", "-b", "main"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
        (root / "task.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "tracked-unrelated.txt").write_text("original\n", encoding="utf-8")
        subprocess.run(("git", "add", "task.py", "tracked-unrelated.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-m", "initial"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "remote", "add", "origin", str(origin)), cwd=root, check=True)
        subprocess.run(("git", "push", "-u", "origin", "main"), cwd=root, check=True, capture_output=True)

        (root / "task.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "tracked-unrelated.txt").write_text("user work\n", encoding="utf-8")
        (root / "untracked-unrelated.txt").write_text("untracked work\n", encoding="utf-8")
        environment = os.environ.copy()
        project_root = str(Path(__file__).resolve().parents[1])
        environment["PYTHONPATH"] = os.pathsep.join(
            item for item in (project_root, environment.get("PYTHONPATH", "")) if item
        )
        verified = subprocess.run(
            (sys.executable, "-m", "tools.dev.verify", "--path", "task.py"),
            cwd=root, env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        message = "checkpoint end-to-end"
        completed = subprocess.run(
            (sys.executable, "-m", "tools.dev.checkpoint", "--message", message),
            cwd=root, env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("STATUS PASS", completed.stdout)
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, text=True, capture_output=True, check=True
        ).stdout.strip()
        self.assertEqual(
            subprocess.run(
                ("git", "show", "-s", "--format=%B", "HEAD"), cwd=root,
                text=True, capture_output=True, check=True,
            ).stdout.strip(),
            message,
        )
        self.assertEqual(
            subprocess.run(
                ("git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
                cwd=root, text=True, capture_output=True, check=True,
            ).stdout.splitlines(),
            ["task.py"],
        )
        remote_head = subprocess.run(
            ("git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"),
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        self.assertEqual(remote_head, head)
        self.assertEqual((root / "tracked-unrelated.txt").read_text(encoding="utf-8"), "user work\n")
        self.assertEqual((root / "untracked-unrelated.txt").read_text(encoding="utf-8"), "untracked work\n")
        status = subprocess.run(
            ("git", "status", "--short"), cwd=root, text=True, capture_output=True, check=True
        ).stdout
        self.assertIn(" M tracked-unrelated.txt", status)
        self.assertIn("?? untracked-unrelated.txt", status)

        repeated = subprocess.run(
            (sys.executable, "-m", "tools.dev.checkpoint", "--message", message),
            cwd=root, env=environment, text=True, capture_output=True, check=False,
        )
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertIn("completed-commit", repeated.stdout)
        self.assertEqual(
            subprocess.run(
                ("git", "rev-parse", "HEAD"), cwd=root, text=True,
                capture_output=True, check=True,
            ).stdout.strip(),
            head,
        )


class TransactionWorkflowTests(unittest.TestCase):
    def make_repo(self) -> tuple[tempfile.TemporaryDirectory, Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        base = Path(temporary.name)
        root = base / "work"
        origin = base / "origin.git"
        root.mkdir()
        subprocess.run(("git", "init", "--bare", str(origin)), check=True, capture_output=True)
        subprocess.run(("git", "init", "-q", "-b", "main"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.email", "test@example.invalid"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
        (root / "task.txt").write_bytes(b"alpha\nbeta\ngamma\n")
        (root / "unrelated.txt").write_bytes(b"original\n")
        subprocess.run(("git", "add", "task.txt", "unrelated.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-qm", "initial"), cwd=root, check=True)
        subprocess.run(("git", "remote", "add", "origin", str(origin)), cwd=root, check=True)
        subprocess.run(("git", "push", "-u", "origin", "main"), cwd=root, check=True, capture_output=True)
        return temporary, root, origin

    @staticmethod
    def head(root: Path) -> str:
        return subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, text=True, capture_output=True, check=True
        ).stdout.strip()

    def test_clean_transaction_commits_verified_candidate(self):
        temporary, root, origin = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        begin(["task.txt", "unrelated.txt"], git=git, task_id="clean-flow")
        (root / "task.txt").write_bytes(b"alpha\nbeta task\ngamma\n")
        passed, output = verify(
            ["task.txt", "unrelated.txt"], git=git, transaction_id="clean-flow"
        )
        self.assertTrue(passed, output)
        expected = (candidate_root("clean-flow", git=git) / "task.txt").read_bytes()
        passed, output = checkpoint("clean transaction", git=git)
        self.assertTrue(passed, output)
        committed = subprocess.run(
            ("git", "show", "HEAD:task.txt"), cwd=root, capture_output=True, check=True
        ).stdout
        self.assertEqual(committed, expected)
        committed_files = subprocess.run(
            ("git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"),
            cwd=root, text=True, capture_output=True, check=True,
        ).stdout.splitlines()
        self.assertEqual(committed_files, ["task.txt"])
        remote = subprocess.run(
            ("git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"),
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        self.assertEqual(remote, self.head(root))

    def test_mixed_transaction_preserves_combined_worktree_and_real_index(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        (root / "task.txt").write_bytes(b"alpha user\nbeta\ngamma\n")
        begin(["task.txt"], git=git, task_id="mixed-flow")
        combined = b"alpha user\nbeta\ngamma task\n"
        (root / "task.txt").write_bytes(combined)
        (root / "unrelated.txt").write_bytes(b"unrelated user\n")
        (root / "untracked.txt").write_bytes(b"untracked user\n")
        index_before = (root / ".git" / "index").read_bytes()
        passed, output = verify(["task.txt"], git=git, transaction_id="mixed-flow")
        self.assertTrue(passed, output)
        candidate = (candidate_root("mixed-flow", git=git) / "task.txt").read_bytes()
        self.assertEqual(candidate, b"alpha\nbeta\ngamma task\n")
        self.assertEqual((root / ".git" / "index").read_bytes(), index_before)
        passed, output = checkpoint("mixed transaction", git=git)
        self.assertTrue(passed, output)
        self.assertEqual((root / "task.txt").read_bytes(), combined)
        self.assertEqual((root / ".git" / "index").read_bytes(), index_before)
        self.assertEqual(
            subprocess.run(("git", "show", "HEAD:task.txt"), cwd=root, capture_output=True, check=True).stdout,
            candidate,
        )
        remaining = subprocess.run(
            ("git", "diff", "HEAD", "--", "task.txt"), cwd=root,
            text=True, capture_output=True, check=True,
        ).stdout
        self.assertIn("alpha user", remaining)
        self.assertEqual((root / "unrelated.txt").read_bytes(), b"unrelated user\n")
        self.assertEqual((root / "untracked.txt").read_bytes(), b"untracked user\n")

    def test_overlap_fails_before_commit(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        (root / "task.txt").write_bytes(b"alpha user\nbeta\ngamma\n")
        begin(["task.txt"], git=git, task_id="overlap-flow")
        old_head = self.head(root)
        index_before = (root / ".git" / "index").read_bytes()
        (root / "task.txt").write_bytes(b"alpha task\nbeta\ngamma\n")
        passed, output = verify(["task.txt"], git=git, transaction_id="overlap-flow")
        self.assertFalse(passed)
        self.assertIn("three-way merge", output)
        self.assertEqual(self.head(root), old_head)
        self.assertEqual((root / ".git" / "index").read_bytes(), index_before)

    def test_stale_head_and_branch_fail_verification(self):
        for change in ("head", "branch"):
            with self.subTest(change=change):
                temporary, root, _ = self.make_repo()
                self.addCleanup(temporary.cleanup)
                git = Git(root)
                begin(["task.txt"], git=git, task_id=f"stale-{change}")
                if change == "head":
                    (root / "next.txt").write_bytes(b"next\n")
                    subprocess.run(("git", "add", "next.txt"), cwd=root, check=True)
                    subprocess.run(("git", "commit", "-qm", "next"), cwd=root, check=True)
                else:
                    subprocess.run(("git", "switch", "-qc", "other"), cwd=root, check=True)
                passed, output = verify(["task.txt"], git=git, transaction_id=f"stale-{change}")
                self.assertFalse(passed)
                self.assertIn("transaction is stale", output)

    def test_candidate_change_after_verify_fails_before_commit(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        begin(["task.txt"], git=git, task_id="tamper")
        (root / "task.txt").write_bytes(b"alpha\nbeta task\ngamma\n")
        passed, output = verify(["task.txt"], git=git, transaction_id="tamper")
        self.assertTrue(passed, output)
        (candidate_root("tamper", git=git) / "task.txt").write_bytes(b"tampered\n")
        old_head = self.head(root)
        passed, output = checkpoint("must fail", git=git)
        self.assertFalse(passed)
        self.assertIn("verified candidate changed", output)
        self.assertEqual(self.head(root), old_head)

    def test_unexpected_staged_file_fails_before_transaction_commit(self):
        temporary, root, _ = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        begin(["task.txt"], git=git, task_id="staged")
        (root / "task.txt").write_bytes(b"alpha\nbeta task\ngamma\n")
        passed, output = verify(["task.txt"], git=git, transaction_id="staged")
        self.assertTrue(passed, output)
        (root / "staged.txt").write_bytes(b"staged\n")
        subprocess.run(("git", "add", "staged.txt"), cwd=root, check=True)
        old_head = self.head(root)
        passed, output = checkpoint("must fail", git=git)
        self.assertFalse(passed)
        self.assertIn("unexpected staged files", output)
        self.assertEqual(self.head(root), old_head)

    def test_push_failure_reports_exact_local_commit(self):
        temporary, root, origin = self.make_repo()
        self.addCleanup(temporary.cleanup)
        git = Git(root)
        begin(["task.txt"], git=git, task_id="push-fail")
        (root / "task.txt").write_bytes(b"alpha\nbeta task\ngamma\n")
        passed, output = verify(["task.txt"], git=git, transaction_id="push-fail")
        self.assertTrue(passed, output)
        subprocess.run(("git", "remote", "set-url", "origin", str(root / "missing-origin")), cwd=root, check=True)
        old_head = self.head(root)
        passed, output = checkpoint("local only", git=git)
        self.assertFalse(passed)
        local_commit = self.head(root)
        self.assertNotEqual(local_commit, old_head)
        self.assertIn(f"local commit {local_commit} created; push failed", output)
        subprocess.run(("git", "remote", "set-url", "origin", str(origin)), cwd=root, check=True)
        passed, output = checkpoint("local only", git=git)
        self.assertTrue(passed, output)
        self.assertIn("completed-commit", output)
        remote_head = subprocess.run(
            ("git", "--git-dir", str(origin), "rev-parse", "refs/heads/main"),
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        self.assertEqual(remote_head, local_commit)


if __name__ == "__main__":
    unittest.main()
