"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from tools.stop_robot_runtime import RuntimeShutdown, SCOPE_ALL, _environment

REPO = Path("/opt/BybitScanner")
SERVICE = "bybitscanner-paper-start.service"
PREFIX = ("sudo", "-n")


def run_maintenance(target: str, *, root: Path = REPO, runner=subprocess.run,
                    stop=None, env_file: Path | None = None,
                    wait_seconds: float = 0, poll_seconds: float = 30,
                    clock=time.monotonic, sleep=time.sleep) -> str:
    if len(target) != 40 or any(char not in "0123456789abcdef" for char in target):
        return "BLOCKED: target must be an exact 40-character commit SHA"
    if wait_seconds < 0 or poll_seconds <= 0:
        return "BLOCKED: invalid waiting period"

    def execute(*argv: str):
        try:
            return runner(list(argv), cwd=root, capture_output=True,
                          text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None

    def command(*argv: str) -> bool:
        reply = execute(*argv)
        return reply is not None and reply.returncode == 0

    # Preflight is read-only for runtime: do not stop a working protected
    # service to discover a dirty tree or invalid/unavailable target later.
    if not command("git", "fetch", "origin", "stable/adfb50b-forward"):
        return "BLOCKED: cannot fetch approved stable"
    if not command("git", "diff", "--quiet") or not command(
        "git", "diff", "--cached", "--quiet"
    ):
        return "BLOCKED: working tree contains changes"
    if not command("git", "merge-base", "--is-ancestor", target,
                   "origin/stable/adfb50b-forward"):
        return "BLOCKED: target is not on approved stable"
    if not command("git", "merge-base", "--is-ancestor", "HEAD", target):
        return "BLOCKED: target is not a fast-forward from installed HEAD"

    shutdown = stop if stop is not None else RuntimeShutdown(
        root=root, env=_environment(env_file)
    ).run
    deadline = clock() + wait_seconds
    while True:
        result = shutdown(SCOPE_ALL)
        if result.ok and result.runtime_stopped:
            break
        if clock() >= deadline:
            return "BLOCKED: canonical safe-stop refused; PAPER protection retained"
        sleep(min(poll_seconds, max(0, deadline - clock())))

    if not command("git", "merge", "--ff-only", target):
        return "BLOCKED: fast-forward failed after safe-stop"
    installed = execute("git", "rev-parse", "--verify", "HEAD")
    if installed is None or installed.returncode != 0 or installed.stdout.strip() != target:
        return "BLOCKED: installed HEAD differs from approved target"
    if not command(*PREFIX, "systemctl", "start", SERVICE):
        return "BLOCKED: PAPER core start failed; no admission bypass attempted"
    return "CORE_STARTED: exact HEAD and PAPER core start confirmed; PAPER_AUTO/reentry and protection require API proof"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed one-action PAPER maintenance")
    parser.add_argument("sha")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    parser.add_argument("--wait-seconds", type=float, default=0)\n    args = parser.parse_args(argv)
    status = run_maintenance(args.sha, env_file=args.env_file, wait_seconds=args.wait_seconds)
    print(status)
    return 0 if status.startswith("CORE_STARTED:") else 2


if __name__ == "__main__":
    sys.exit(main())
