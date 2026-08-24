"""Create a safe user-run checkpoint from the latest PASS receipt."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .workflow import Git, compact, fingerprints, read_receipt, repository_root, require_ok


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
            raise RuntimeError("verification receipt is stale: HEAD changed")
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
