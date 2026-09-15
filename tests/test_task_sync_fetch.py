from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.dev.task import _sync_preflight
from tools.dev.workflow import Git


class RecordingGit:
    def __init__(self, inner: Git):
        self.inner = inner
        self.root = inner.root
        self.calls: list[tuple[str, ...]] = []

    def run(self, *args: str):
        self.calls.append(tuple(args))
        return self.inner.run(*args)


class TaskSyncFetchTests(unittest.TestCase):
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
        (root / "README.md").write_text("# Base\n", encoding="utf-8")
        subprocess.run(("git", "add", "README.md"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-qm", "initial"), cwd=root, check=True)
        subprocess.run(("git", "remote", "add", "origin", str(origin)), cwd=root, check=True)
        subprocess.run(("git", "push", "-u", "origin", "main"), cwd=root, check=True, capture_output=True)
        return temporary, root

    def test_sync_preflight_fetches_only_active_main_branch(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        recording = RecordingGit(Git(root))

        _sync_preflight(recording)  # type: ignore[arg-type]

        fetches = [call for call in recording.calls if call and call[0] == "fetch"]
        self.assertEqual(
            fetches,
            [("fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main")],
        )
        self.assertNotIn("--prune", fetches[0])

    def test_sync_preflight_scopes_feature_branch_fetch_to_that_branch(self):
        temporary, root = self.make_repo()
        self.addCleanup(temporary.cleanup)
        subprocess.run(("git", "switch", "-c", "feature/scoped"), cwd=root, check=True, capture_output=True)
        subprocess.run(("git", "push", "-u", "origin", "feature/scoped"), cwd=root, check=True, capture_output=True)
        recording = RecordingGit(Git(root))

        _sync_preflight(recording)  # type: ignore[arg-type]

        fetches = [call for call in recording.calls if call and call[0] == "fetch"]
        self.assertEqual(
            fetches,
            [("fetch", "--no-tags", "origin", "refs/heads/feature/scoped:refs/remotes/origin/feature/scoped")],
        )


if __name__ == "__main__":
    unittest.main()
