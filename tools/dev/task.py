"""Single entry point for a protected BybitScanner implementation task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .task_context import build_task_context
from .task_transaction import begin, load_transaction
from .verify import verify
from .workflow import (
    Git, fingerprints, index_tree, read_receipt, receipt_path, repository_root, require_ok,
    worktree_change_paths,
)


HARNESS_SCHEMA = "bybitscanner.task-harness.v1"


def _manifest_path(directory: Path) -> Path:
    return directory / "harness.json"


def _sync_preflight(git: Git) -> None:
    """Require a named branch that exactly matches its origin mirror.

    Tasks are intentionally allowed on feature branches. The safety property is not
    "must be main"; it is "start from a reviewable, remotely mirrored baseline".
    """
    require_ok(git.run("fetch", "origin", "--prune"), "origin fetch")
    branch = require_ok(git.run("symbolic-ref", "--quiet", "--short", "HEAD"), "branch discovery")
    head = require_ok(git.run("rev-parse", "HEAD"), "HEAD discovery")
    remote_ref = f"refs/remotes/origin/{branch}"
    remote_result = git.run("rev-parse", "--verify", "--quiet", remote_ref)
    if remote_result.returncode:
        raise RuntimeError(
            f"current branch has no origin mirror; publish/sync {branch} before starting a task"
        )
    remote = remote_result.stdout.strip()
    if head != remote:
        counts = require_ok(
            git.run("rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"),
            "synchronization comparison",
        )
        raise RuntimeError(f"HEAD does not match origin/{branch} ({counts})")


def start(
    intent: str, paths: Sequence[str], *, git: Git | None = None, task_id: str | None = None
) -> tuple[bool, str]:
    try:
        probe = git or Git(Path.cwd())
        root = repository_root(probe)
        active = git or Git(root)
        _sync_preflight(active)
        receipt_path(root, active).unlink(missing_ok=True)
        context = build_task_context(root, paths, hint=intent, git=active)
        dirty_paths = worktree_change_paths(active)
        dirty_fingerprints = fingerprints(root, dirty_paths)
        baseline_index_tree = index_tree(active)
        metadata = begin(paths, git=active, task_id=task_id)
        directory, _ = load_transaction(metadata["task_id"], git=active)
        manifest = {
            "schema": HARNESS_SCHEMA,
            "intent": intent.strip(),
            "task_id": metadata["task_id"],
            "scope": metadata["scope"],
            "baseline_change_paths": dirty_paths,
            "baseline_change_fingerprints": dirty_fingerprints,
            "baseline_index_tree": baseline_index_tree,
            "context": context,
        }
        _manifest_path(directory).write_text(
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        refs = ", ".join(context["authority_refs"])
        return True, "\n".join((
            "STATUS PASS", f"TASK {metadata['task_id']}",
            f"BRANCH {metadata['branch']}",
            f"SCOPE {', '.join(metadata['scope'])}", f"AUTHORITY {refs}",
            "VERIFICATION AUTO_FROM_SCOPE", "BLOCKERS NONE",
        ))
    except (OSError, RuntimeError, ValueError) as exc:
        return False, f"STATUS FAIL\nBLOCKERS {exc}"


def _load_manifest(directory: Path) -> dict:
    try:
        value = json.loads(_manifest_path(directory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"task harness manifest is missing or corrupt: {exc}") from exc
    if value.get("schema") != HARNESS_SCHEMA:
        raise RuntimeError("task harness manifest is stale or corrupt")
    return value


def finish(task_id: str, *, git: Git | None = None) -> tuple[bool, str]:
    try:
        probe = git or Git(Path.cwd())
        root = repository_root(probe)
        active = git or Git(root)
        directory, metadata = load_transaction(task_id, git=active)
        manifest = _load_manifest(directory)
        if manifest.get("task_id") != task_id or manifest.get("scope") != metadata["scope"]:
            raise RuntimeError("task harness manifest does not match transaction")
        current_paths = worktree_change_paths(active)
        scope_files = {record["path"] for record in metadata["files"]}
        baseline_paths = set(manifest["baseline_change_paths"])
        unexpected = sorted(set(current_paths) - baseline_paths - scope_files)
        if unexpected:
            raise RuntimeError("out-of-scope worktree changes: " + ", ".join(unexpected))
        protected = sorted(baseline_paths - scope_files)
        if fingerprints(root, protected) != {
            path: manifest["baseline_change_fingerprints"][path] for path in protected
        }:
            raise RuntimeError("pre-existing user-owned files changed outside task scope")
        if index_tree(active) != manifest.get("baseline_index_tree"):
            raise RuntimeError("Git index content changed during task")
        passed, output = verify(metadata["scope"], git=active, transaction_id=task_id)
        if not passed:
            return False, output
        receipt = read_receipt(root, active)
        changed = receipt["transaction"]["candidate_files"]
        checks = [item["name"] for item in receipt["checks"]]
        return True, "\n".join((
            "STATUS PASS", f"CHANGED {', '.join(changed)}", f"TESTS {', '.join(checks)}",
            "VERIFIER PASS receipt=.git/bybitscanner/latest-pass.json",
            "BLOCKERS NONE",
        ))
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        return False, f"STATUS FAIL\nBLOCKERS {exc}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--intent", required=True)
    start_parser.add_argument("--path", action="append", required=True, dest="paths")
    start_parser.add_argument("--task-id")
    finish_parser = commands.add_parser("finish")
    finish_parser.add_argument("--task", required=True)
    args = parser.parse_args(argv)
    if args.command == "start":
        passed, output = start(args.intent, args.paths, task_id=args.task_id)
    else:
        passed, output = finish(args.task)
    print(output)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())