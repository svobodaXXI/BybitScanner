"""GitHub-first checkpoint wrapper.

For GitHub origins, checkpoint is validation-only: it verifies the latest PASS
receipt and never stages, commits, or pushes. Repository publication belongs to
GitHub/PR workflow; local machines synchronize after merge with pull.

For non-GitHub origins, the legacy local-publish implementation remains
available for isolated/local harness tests and explicitly non-GitHub workflows.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .checkpoint_legacy import checkpoint as _legacy_checkpoint
from .task_transaction import candidate_root, candidate_tree, inspect, load_transaction
from .workflow import Git, compact, fingerprints, index_tree, read_receipt, repository_root, require_ok


def _origin_url(git: Git) -> str:
    result = git.run("remote", "get-url", "origin")
    return result.stdout.strip() if result.returncode == 0 else ""


def _is_github_origin(url: str) -> bool:
    normalized = url.strip().lower()
    return (
        normalized.startswith("https://github.com/")
        or normalized.startswith("http://github.com/")
        or normalized.startswith("git@github.com:")
        or normalized.startswith("ssh://git@github.com/")
    )


def _validate_github_first(message: str, *, git: Git) -> tuple[bool, str]:
    checks: list[str] = []
    scope: list[str] = []
    try:
        root = repository_root(git)
        receipt = read_receipt(root, git)
        scope = list(receipt["task_paths"])
        files = list(receipt["files"])
        branch = require_ok(git.run("branch", "--show-current"), "branch discovery")
        head = require_ok(git.run("rev-parse", "HEAD"), "HEAD discovery")
        if branch != receipt["branch"]:
            raise RuntimeError("verification receipt is stale: branch changed")
        if head != receipt["head"]:
            raise RuntimeError("verification receipt is stale: HEAD changed")
        if fingerprints(root, files) != receipt["fingerprints"]:
            raise RuntimeError("verification receipt is stale: task-file content changed")
        checks.append("receipt-current")

        staged_raw = require_ok(
            git.run("diff", "--cached", "--name-only", "-z"),
            "staged-file inspection",
        )
        staged = sorted(item for item in staged_raw.split("\0") if item)
        if staged:
            raise RuntimeError("unexpected staged files: " + ", ".join(staged))
        checks.append("real-index-clean")
        head_tree = require_ok(git.run("rev-parse", f"{head}^{{tree}}"), "HEAD tree discovery")
        if index_tree(git) != head_tree:
            raise RuntimeError("real Git index tree does not match current HEAD")
        checks.append("real-index-head-aligned")

        transaction = receipt.get("transaction")
        if transaction:
            task_id = transaction["id"]
            _, metadata = load_transaction(task_id, git=git)
            if metadata["branch"] != receipt["branch"] or metadata["head"] != receipt["head"]:
                raise RuntimeError("verification receipt transaction baseline does not match")
            if metadata["scope"] != receipt["task_paths"]:
                raise RuntimeError("verification receipt transaction scope does not match")
            isolated = transaction.get("isolated_verification", {})
            if (
                isolated.get("status") != "PASS"
                or isolated.get("cleanup") != "PASS"
                or isolated.get("base_head") != receipt["head"]
                or isolated.get("candidate_tree") != transaction.get("candidate_tree")
            ):
                raise RuntimeError("verification receipt lacks current isolated candidate PASS evidence")
            state = inspect(task_id, git=git)
            if state["status"] != "OK":
                raise RuntimeError("transaction is stale: " + ", ".join(state["blockers"]))
            candidate_files = list(transaction["candidate_files"])
            candidates = candidate_root(task_id, git=git)
            if fingerprints(candidates, candidate_files) != transaction["candidate_fingerprints"]:
                raise RuntimeError("verification receipt is stale: verified candidate changed")
            if candidate_tree(task_id, git=git) != transaction["candidate_tree"]:
                raise RuntimeError("verification receipt is stale: verified candidate tree changed")
            proofs = transaction.get("proofs", {})
            if not set(candidate_files).issubset(proofs) or any(
                value.get("status") != "PASS" for value in proofs.values()
            ):
                raise RuntimeError("verification receipt candidate proof state is invalid")
            checks.extend(("transaction-current", "candidate-current", "isolated-candidate-pass"))

        checks.extend(("github-first", "no-local-commit", "no-local-push"))
        return True, compact("PASS", scope, checks, (), ())
    except (KeyError, OSError, RuntimeError, TypeError, ValueError) as exc:
        return False, compact("FAIL", scope, checks, (), (str(exc),))


def checkpoint(message: str = "", *, git: Git | None = None) -> tuple[bool, str]:
    probe = git or Git(Path.cwd())
    try:
        root = repository_root(probe)
        active_git = git or Git(root)
    except (OSError, RuntimeError, ValueError) as exc:
        return False, compact("FAIL", (), (), (), (str(exc),))
    if _is_github_origin(_origin_url(active_git)):
        return _validate_github_first(message, git=active_git)
    return _legacy_checkpoint(message, git=active_git)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--message",
        default="",
        help="Compatibility label only for GitHub-first validation; no commit is created.",
    )
    args = parser.parse_args(argv)
    passed, output = checkpoint(args.message)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
