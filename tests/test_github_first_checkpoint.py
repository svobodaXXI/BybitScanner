from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.dev.checkpoint import checkpoint
from tools.dev.workflow import CommandResult, Git, fingerprints


class GitHubFirstCheckpointGit(Git):
    def __init__(self, root: Path):
        super().__init__(root)
        self.head = "a" * 40
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str) -> CommandResult:
        self.calls.append(args)
        if args[:2] == ("rev-parse", "--show-toplevel"):
            return CommandResult(0, str(self.root))
        if args[:2] == ("rev-parse", "--git-dir"):
            return CommandResult(0, str(self.root / ".git"))
        if args[:3] == ("remote", "get-url", "origin"):
            return CommandResult(0, "https://github.com/example/project.git\n")
        if args[:2] == ("branch", "--show-current"):
            return CommandResult(0, "main\n")
        if args[:2] == ("rev-parse", "HEAD"):
            return CommandResult(0, self.head + "\n")
        if args[:4] == ("diff", "--cached", "--name-only", "-z"):
            return CommandResult(0, "")
        if args[:2] == ("rev-parse", f"{self.head}^{{tree}}"):
            return CommandResult(0, "tree\n")
        if args[0] == "write-tree":
            return CommandResult(0, "tree\n")
        return CommandResult(0, "")


class GitHubFirstCheckpointTests(unittest.TestCase):
    def test_github_origin_checkpoint_never_stages_commits_or_pushes(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        (root / ".git/bybitscanner").mkdir(parents=True)
        (root / "task.py").write_text("VALUE = 1\n", encoding="utf-8")
        git = GitHubFirstCheckpointGit(root)
        (root / ".git/bybitscanner/latest-pass.json").write_text(
            json.dumps({
                "status": "PASS",
                "branch": "main",
                "head": git.head,
                "task_paths": ["task.py"],
                "files": ["task.py"],
                "fingerprints": fingerprints(root, ["task.py"]),
                "checks": [],
            }),
            encoding="utf-8",
        )

        passed, output = checkpoint("ignored message", git=git)

        self.assertTrue(passed, output)
        self.assertIn("github-first", output)
        self.assertIn("no-local-commit", output)
        self.assertIn("no-local-push", output)
        forbidden = {"add", "commit", "push", "read-tree", "update-index"}
        self.assertFalse(any(call and call[0] in forbidden for call in git.calls), git.calls)


if __name__ == "__main__":
    unittest.main()
