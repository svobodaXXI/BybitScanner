"""Create a safe user-run checkpoint from the latest PASS receipt."""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from .task_transaction import candidate_root, candidate_tree, inspect, load_transaction
from .workflow import (
    Git, CommandResult, compact, fingerprints, index_snapshot, index_tree, read_receipt,
    repository_root, require_ok, worktree_change_paths,
)


def _run_alternate(root: Path, index: Path, *args: str, input_bytes: bytes | None = None) -> CommandResult:
    environment = os.environ.copy()
    environment["GIT_INDEX_FILE"] = str(index)
    completed = subprocess.run(
        ("git", *args), cwd=root, env=environment, input=input_bytes,
        capture_output=True, check=False,
    )
    return CommandResult(
        completed.returncode,
        completed.stdout.decode(errors="replace"),
        completed.stderr.decode(errors="replace"),
    )


def _candidate_mode(git: Git, path: str) -> str:
    value = require_ok(git.run("ls-tree", "HEAD", "--", path), f"mode discovery for {path}")
    return value.split(None, 1)[0] if value else "100644"


def _transaction_commit(
    root: Path, git: Git, receipt: dict, message: str, checks: list[str]
) -> str:
    transaction = receipt["transaction"]
    task_id = transaction["id"]
    directory, metadata = load_transaction(task_id, git=git)
    if metadata["branch"] != receipt["branch"] or metadata["head"] != receipt["head"]:
        raise RuntimeError("verification receipt transaction baseline does not match")
    if metadata["scope"] != receipt["task_paths"]:
        raise RuntimeError("verification receipt transaction scope does not match")
    isolated = transaction.get("isolated_verification", {})
    if (
        isolated.get("status") != "PASS" or isolated.get("cleanup") != "PASS"
        or isolated.get("base_head") != receipt["head"]
        or isolated.get("candidate_tree") != transaction.get("candidate_tree")
    ):
        raise RuntimeError("verification receipt lacks current isolated candidate PASS evidence")
    state = inspect(task_id, git=git)
    if state["status"] != "OK":
        raise RuntimeError("transaction is stale: " + ", ".join(state["blockers"]))
    files = list(transaction["candidate_files"])
    candidates = candidate_root(task_id, git=git)
    if fingerprints(candidates, files) != transaction["candidate_fingerprints"]:
        raise RuntimeError("verification receipt is stale: verified candidate changed")
    if candidate_tree(task_id, git=git) != transaction["candidate_tree"]:
        raise RuntimeError("verification receipt is stale: verified candidate tree changed")
    proofs = transaction.get("proofs", {})
    if not set(files).issubset(proofs) or any(value.get("status") != "PASS" for value in proofs.values()):
        raise RuntimeError("verification receipt candidate proof state is invalid")
    if fingerprints(root, receipt["files"]) != receipt["fingerprints"]:
        raise RuntimeError("verification receipt is stale: task-file content changed")

    staged_raw = require_ok(git.run("diff", "--cached", "--name-only", "-z"), "staged-file inspection")
    staged = sorted(item for item in staged_raw.split("\0") if item)
    if staged:
        raise RuntimeError("unexpected staged files: " + ", ".join(staged))
    head_tree = require_ok(git.run("rev-parse", f"{receipt['head']}^{{tree}}"), "HEAD tree discovery")
    if index_tree(git) != head_tree:
        raise RuntimeError("real Git index tree does not match current HEAD")
    checks.extend((
        "receipt-current", "transaction-current", "candidate-current",
        "real-index-clean", "real-index-head-aligned",
    ))
    real_index = index_snapshot(root, git)
    protected_paths = sorted(set(receipt["files"]) | set(worktree_change_paths(git)))
    worktree = fingerprints(root, protected_paths)

    descriptor, temporary_name = tempfile.mkstemp(prefix="checkpoint-", suffix=".index", dir=directory)
    os.close(descriptor)
    alternate_index = Path(temporary_name)
    alternate_index.unlink()
    try:
        require_ok(_run_alternate(root, alternate_index, "read-tree", receipt["head"]), "alternate index initialization")
        for path in files:
            data = (candidates / path).read_bytes()
            blob = require_ok(
                _run_alternate(root, alternate_index, "hash-object", "-w", "--stdin", input_bytes=data),
                f"candidate blob creation for {path}",
            )
            require_ok(
                _run_alternate(
                    root, alternate_index, "update-index", "--add", "--cacheinfo",
                    _candidate_mode(git, path), blob, path,
                ),
                f"alternate index update for {path}",
            )
        require_ok(_run_alternate(root, alternate_index, "diff", "--cached", "--check"), "candidate diff-check")
        staged_candidate = {
            item for item in require_ok(
                _run_alternate(root, alternate_index, "diff", "--cached", "--name-only", "-z"),
                "candidate staged-file verification",
            ).split("\0") if item
        }
        if staged_candidate != set(files):
            raise RuntimeError("candidate staged files do not exactly match verification receipt")
        if index_snapshot(root, git) != real_index:
            raise RuntimeError("real Git index changed before commit")
        if fingerprints(root, protected_paths) != worktree:
            raise RuntimeError("working tree changed before commit")
        checks.extend(("alternate-index", "candidate-diff-check", "precommit-atomicity"))
        before = require_ok(git.run("rev-parse", "HEAD"), "pre-commit HEAD discovery")
        result = _run_alternate(root, alternate_index, "commit", "-m", message)
        after = require_ok(git.run("rev-parse", "HEAD"), "post-commit HEAD discovery")
        if result.returncode:
            if after != before:
                raise RuntimeError(f"commit reported failure after creating local commit {after}")
            require_ok(result, "commit")
        if after == before:
            raise RuntimeError("commit did not advance HEAD")
        checks.append("commit")
    finally:
        alternate_index.unlink(missing_ok=True)

    if index_snapshot(root, git) != real_index:
        raise RuntimeError(f"local commit {after} created but real Git index changed before reconciliation")
    if fingerprints(root, protected_paths) != worktree:
        raise RuntimeError(f"local commit {after} created but working tree changed")
    parent = require_ok(git.run("rev-parse", f"{after}^"), "commit parent discovery")
    if parent != receipt["head"]:
        raise RuntimeError(f"local commit {after} has unexpected parent")
    committed_raw = require_ok(
        git.run("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", after),
        "committed-file discovery",
    )
    if {item for item in committed_raw.split("\0") if item} != set(files):
        raise RuntimeError(f"local commit {after} file set does not match verified candidate")
    for path in files:
        completed = subprocess.run(
            ("git", "show", f"{after}:{path}"), cwd=root, capture_output=True, check=False
        )
        if completed.returncode or completed.stdout != (candidates / path).read_bytes():
            raise RuntimeError(f"local commit {after} content does not match verified candidate: {path}")
    committed_tree = require_ok(git.run("rev-parse", f"{after}^{{tree}}"), "committed tree discovery")
    if committed_tree != transaction["candidate_tree"]:
        raise RuntimeError(f"local commit {after} tree does not match isolated verified candidate")
    reconciliation = git.run("read-tree", after)
    if reconciliation.returncode:
        detail = (reconciliation.stderr or reconciliation.stdout).strip()
        raise RuntimeError(
            f"local commit {after} created; real-index reconciliation failed"
            + (f": {detail}" if detail else "")
        )
    if index_tree(git) != committed_tree:
        raise RuntimeError(f"local commit {after} created; real index does not match new HEAD")
    staged_after = {
        item for item in require_ok(
            git.run("diff", "--cached", "--name-only", "-z"),
            "post-commit staged-file inspection",
        ).split("\0") if item
    }
    if staged_after:
        raise RuntimeError(
            f"local commit {after} created; real index reconciliation left staged files: "
            + ", ".join(sorted(staged_after))
        )
    if fingerprints(root, protected_paths) != worktree:
        raise RuntimeError(f"local commit {after} created; working tree changed during index reconciliation")
    checks.extend((
        "committed-candidate", "real-index-reconciled", "real-index-head-aligned",
        "worktree-unchanged",
    ))
    return after


def _completed_checkpoint(
    git: Git, receipt: dict, message: str, files: list[str], current_head: str
) -> bool:
    """Recognize only the exact, already-pushed commit described by a receipt."""
    parent = require_ok(git.run("rev-parse", f"{current_head}^"), "commit parent discovery")
    if parent != receipt["head"]:
        return False
    committed_message = require_ok(
        git.run("show", "-s", "--format=%B", current_head), "commit message discovery"
    )
    if committed_message != message.strip():
        return False
    committed_raw = require_ok(
        git.run("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", current_head),
        "committed-file discovery",
    )
    committed_files = {item for item in committed_raw.split("\0") if item}
    if committed_files != set(files):
        return False
    remote = require_ok(
        git.run("ls-remote", "origin", f"refs/heads/{receipt['branch']}"),
        "remote SHA verification",
    )
    remote_sha = remote.split()[0] if remote else ""
    return remote_sha == current_head


def _matches_transaction_commit(
    root: Path, git: Git, receipt: dict, message: str, current_head: str
) -> bool:
    transaction = receipt["transaction"]
    if require_ok(git.run("rev-parse", f"{current_head}^"), "commit parent discovery") != receipt["head"]:
        return False
    if require_ok(git.run("show", "-s", "--format=%B", current_head), "commit message discovery") != message.strip():
        return False
    committed_raw = require_ok(
        git.run("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", current_head),
        "committed-file discovery",
    )
    files = list(transaction["candidate_files"])
    if {item for item in committed_raw.split("\0") if item} != set(files):
        return False
    candidates = candidate_root(transaction["id"], git=git)
    if fingerprints(candidates, files) != transaction["candidate_fingerprints"]:
        return False
    for path in files:
        completed = subprocess.run(
            ("git", "show", f"{current_head}:{path}"), cwd=root, capture_output=True, check=False
        )
        if completed.returncode or completed.stdout != (candidates / path).read_bytes():
            return False
    if require_ok(git.run("rev-parse", f"{current_head}^{{tree}}"), "committed tree discovery") != transaction.get("candidate_tree"):
        return False
    return True


def checkpoint(message: str, *, git: Git | None = None) -> tuple[bool, str]:
    probe = git or Git(Path.cwd())
    checks: list[str] = []
    scope: list[str] = []
    try:
        if not message.strip():
            raise RuntimeError("--message cannot be empty")
        root = repository_root(probe)
        active_git = git or Git(root)
        receipt = read_receipt(root, active_git)
        scope = list(receipt["task_paths"])
        files = list(receipt["files"])
        branch = require_ok(active_git.run("branch", "--show-current"), "branch discovery")
        head = require_ok(active_git.run("rev-parse", "HEAD"), "HEAD discovery")
        if branch != receipt["branch"]:
            raise RuntimeError("verification receipt is stale: branch changed")
        if head != receipt["head"]:
            if (
                receipt.get("transaction")
                and fingerprints(root, files) == receipt["fingerprints"]
                and _matches_transaction_commit(root, active_git, receipt, message, head)
            ):
                checks.append("completed-commit")
                staged_retry = {
                    item for item in require_ok(
                        active_git.run("diff", "--cached", "--name-only", "-z"),
                        "retry staged-file inspection",
                    ).split("\0") if item
                }
                if staged_retry:
                    raise RuntimeError(
                        f"local commit {head} exists; real index is not clean for push retry"
                    )
                retry_tree = require_ok(
                    active_git.run("rev-parse", f"{head}^{{tree}}"), "retry HEAD tree discovery"
                )
                if index_tree(active_git) != retry_tree:
                    raise RuntimeError(
                        f"local commit {head} exists; real index is not aligned for push retry"
                    )
                checks.append("real-index-head-aligned")
                push = active_git.run("push", "origin", branch)
                if push.returncode:
                    detail = (push.stderr or push.stdout).strip()
                    raise RuntimeError(
                        f"local commit {head} exists; push failed"
                        + (f": {detail}" if detail else "")
                    )
                checks.append("push")
                remote = require_ok(
                    active_git.run("ls-remote", "origin", f"refs/heads/{branch}"),
                    "remote SHA verification",
                )
                if (remote.split()[0] if remote else "") != head:
                    raise RuntimeError(f"local commit {head} exists; remote SHA does not match")
                checks.append("remote-sha")
                return True, compact("PASS", scope, checks, (), ())
            if (
                fingerprints(root, files) == receipt["fingerprints"]
                and _completed_checkpoint(active_git, receipt, message, files, head)
            ):
                checks.extend(("completed-commit", "remote-sha"))
                return True, compact("PASS", scope, checks, (), ())
            raise RuntimeError("verification receipt is stale: HEAD changed")
        if receipt.get("transaction"):
            committed = _transaction_commit(root, active_git, receipt, message, checks)
            branch = receipt["branch"]
            push = active_git.run("push", "origin", branch)
            if push.returncode:
                detail = (push.stderr or push.stdout).strip()
                raise RuntimeError(
                    f"local commit {committed} created; push failed"
                    + (f": {detail}" if detail else "")
                )
            checks.append("push")
            remote = require_ok(active_git.run("ls-remote", "origin", f"refs/heads/{branch}"), "remote SHA verification")
            remote_sha = remote.split()[0] if remote else ""
            if remote_sha != committed:
                raise RuntimeError(f"local commit {committed} created; remote SHA does not match")
            checks.append("remote-sha")
            return True, compact("PASS", scope, checks, (), ())
        if fingerprints(root, files) != receipt["fingerprints"]:
            raise RuntimeError("verification receipt is stale: task-file content changed")
        checks.append("receipt-current")
        staged_raw = require_ok(active_git.run("diff", "--cached", "--name-only", "-z"), "staged-file inspection")
        staged = {item for item in staged_raw.split("\0") if item}
        unexpected = sorted(staged - set(files))
        if unexpected:
            raise RuntimeError("unexpected staged files: " + ", ".join(unexpected))
        checks.append("staged-scope")
        require_ok(active_git.run("add", "--", *scope), "exact-path staging")
        checks.append("exact-path-staging")
        staged_after = {item for item in require_ok(active_git.run("diff", "--cached", "--name-only", "-z"), "staged-file verification").split("\0") if item}
        if not staged_after:
            raise RuntimeError("no staged changes to commit")
        unexpected_after = sorted(staged_after - set(files))
        if unexpected_after:
            raise RuntimeError("staging escaped receipt scope: " + ", ".join(unexpected_after))
        require_ok(active_git.run("diff", "--cached", "--check"), "cached diff-check")
        checks.append("cached-diff-check")
        require_ok(active_git.run("commit", "-m", message), "commit")
        checks.append("commit")
        committed = require_ok(active_git.run("rev-parse", "HEAD"), "committed HEAD discovery")
        require_ok(active_git.run("push", "origin", branch), "push")
        checks.append("push")
        remote = require_ok(active_git.run("ls-remote", "origin", f"refs/heads/{branch}"), "remote SHA verification")
        remote_sha = remote.split()[0] if remote else ""
        if remote_sha != committed:
            raise RuntimeError("remote SHA does not match committed HEAD")
        checks.append("remote-sha")
        return True, compact("PASS", scope, checks, (), ())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, compact("FAIL", scope, checks, (), (str(exc),))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", required=True)
    args = parser.parse_args(argv)
    passed, output = checkpoint(args.message)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
