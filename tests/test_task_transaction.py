from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.dev.task_transaction import (
    TransactionError, begin, candidate_root, candidate_tree, create_isolated_worktree,
    derive_candidate, inspect, load_transaction, remove_isolated_worktree,
)
from tools.dev.workflow import Git


class TaskTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.git_run("init", "-q", "-b", "main")
        self.git_run("config", "user.name", "Test")
        self.git_run("config", "user.email", "test@example.invalid")
        self.path = self.root / "sample.txt"
        self.path.write_bytes(b"alpha\nbeta\ngamma\n")
        self.git_run("add", "sample.txt")
        self.git_run("commit", "-qm", "initial")
        self.git = Git(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def git_run(self, *args: str):
        return subprocess.run(("git", *args), cwd=self.root, check=True, capture_output=True)

    def transaction_dir(self, task_id: str) -> Path:
        return self.root / ".git" / "bybitscanner" / "tasks" / task_id

    def candidate(self, task_id: str) -> bytes:
        return (self.transaction_dir(task_id) / "candidate" / "sample.txt").read_bytes()

    def test_clean_tracked_task_edit_produces_candidate(self):
        begin(["sample.txt"], git=self.git, task_id="clean")
        self.path.write_bytes(b"alpha\nbeta task\ngamma\n")
        proofs = derive_candidate("clean", git=self.git)
        self.assertEqual(self.candidate("clean"), self.path.read_bytes())
        self.assertEqual(proofs["sample.txt"].status, "PASS")
        self.assertEqual(inspect("clean", git=self.git)["files"][0]["classification"], "TASK_NEW")

    def test_public_transaction_lookup_returns_validated_metadata_paths(self):
        begin(["sample.txt"], git=self.git, task_id="lookup")
        directory, metadata = load_transaction("lookup", git=self.git)
        self.assertEqual(metadata["task_id"], "lookup")
        self.assertEqual(candidate_root("lookup", git=self.git), directory / "candidate")

    def test_isolated_worktree_matches_candidate_and_cleans_without_real_mutation(self):
        begin(["sample.txt"], git=self.git, task_id="isolated")
        task_bytes = b"alpha\nbeta task\ngamma\n"
        self.path.write_bytes(task_bytes)
        derive_candidate("isolated", git=self.git)
        index_before = (self.root / ".git" / "index").read_bytes()
        worktree_before = self.path.read_bytes()
        isolated, tree = create_isolated_worktree("isolated", git=self.git)
        self.assertEqual((isolated / "sample.txt").read_bytes(), task_bytes)
        self.assertEqual(tree, candidate_tree("isolated", git=self.git))
        remove_isolated_worktree(isolated, git=self.git)
        self.assertFalse(isolated.exists())
        self.assertEqual(self.path.read_bytes(), worktree_before)
        self.assertEqual((self.root / ".git" / "index").read_bytes(), index_before)

    def test_dirty_independent_task_hunk_yields_task_only_and_inverse_proof(self):
        self.path.write_bytes(b"alpha user\nbeta\ngamma\n")
        begin(["sample.txt"], git=self.git, task_id="mixed")
        self.path.write_bytes(b"alpha user\nbeta\ngamma task\n")
        proofs = derive_candidate("mixed", git=self.git)
        self.assertEqual(self.candidate("mixed"), b"alpha\nbeta\ngamma task\n")
        self.assertEqual(proofs["sample.txt"].detail, "inverse reconstruction is byte-exact")
        self.assertEqual(inspect("mixed", git=self.git)["files"][0]["classification"], "MIXED")

    def test_overlapping_user_and_task_edit_fails_closed(self):
        self.path.write_bytes(b"alpha user\nbeta\ngamma\n")
        begin(["sample.txt"], git=self.git, task_id="overlap")
        self.path.write_bytes(b"alpha task\nbeta\ngamma\n")
        with self.assertRaises(TransactionError):
            derive_candidate("overlap", git=self.git)

    def test_preexisting_untracked_is_classified_and_fails_closed(self):
        extra = self.root / "extra.txt"
        extra.write_bytes(b"user\n")
        begin(["extra.txt"], git=self.git, task_id="untracked")
        self.assertEqual(inspect("untracked", git=self.git)["files"][0]["classification"], "PREEXISTING_UNTRACKED")
        with self.assertRaises(TransactionError):
            derive_candidate("untracked", git=self.git)

    def test_head_change_after_begin_is_stale(self):
        begin(["sample.txt"], git=self.git, task_id="stale")
        (self.root / "other.txt").write_text("next\n", encoding="utf-8")
        self.git_run("add", "other.txt")
        self.git_run("commit", "-qm", "next")
        self.assertEqual(inspect("stale", git=self.git)["status"], "STALE")
        with self.assertRaises(TransactionError):
            derive_candidate("stale", git=self.git)

    def test_corrupt_metadata_is_inspectable(self):
        begin(["sample.txt"], git=self.git, task_id="broken")
        (self.transaction_dir("broken") / "transaction.json").write_text("{", encoding="utf-8")
        value = inspect("broken", git=self.git)
        self.assertEqual(value["status"], "CORRUPT")
        self.assertTrue(value["blockers"])

    def test_unsafe_metadata_path_is_rejected_without_worktree_mutation(self):
        begin(["sample.txt"], git=self.git, task_id="unsafe")
        metadata_path = self.transaction_dir("unsafe") / "transaction.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["files"][0]["path"] = "../outside.txt"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        before = self.path.read_bytes()
        self.assertEqual(inspect("unsafe", git=self.git)["status"], "CORRUPT")
        with self.assertRaises(TransactionError):
            derive_candidate("unsafe", git=self.git)
        self.assertEqual(self.path.read_bytes(), before)

    def test_operations_do_not_change_worktree_or_real_index(self):
        self.path.write_bytes(b"alpha user\nbeta\ngamma\n")
        before_worktree = self.path.read_bytes()
        before_index = (self.root / ".git" / "index").read_bytes()
        begin(["sample.txt"], git=self.git, task_id="immutable")
        self.path.write_bytes(b"alpha user\nbeta\ngamma task\n")
        expected_worktree = self.path.read_bytes()
        derive_candidate("immutable", git=self.git)
        inspect("immutable", git=self.git)
        self.assertNotEqual(before_worktree, expected_worktree)
        self.assertEqual(self.path.read_bytes(), expected_worktree)
        self.assertEqual((self.root / ".git" / "index").read_bytes(), before_index)

    def test_clean_baseline_avoids_snapshot_and_preserves_raw_dirty_bytes(self):
        clean = begin(["sample.txt"], git=self.git, task_id="no-copy")
        self.assertIsNone(clean["files"][0]["snapshot"])
        raw = b"alpha\x00user\r\n"
        self.path.write_bytes(raw)
        dirty = begin(["sample.txt"], git=self.git, task_id="raw")
        snapshot = self.transaction_dir("raw") / dirty["files"][0]["snapshot"]
        self.assertEqual(snapshot.read_bytes(), raw)
        self.assertEqual(dirty["files"][0]["baseline_sha256"], hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
