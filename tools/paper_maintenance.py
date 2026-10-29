"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from tools.stop_robot_runtime import RuntimeShutdown, SCOPE_ALL, _environment

REPO = Path("/opt/BybitScanner")
SERVICE = "bybitscanner-paper-start.service"
PREFIX = ("sudo", "-n")


def run_maintenance(target: str, *, root: Path = REPO, runner=subprocess.run,
                    stop=None, env_file: Path | None = None) -> str:
    if len(target) != 40 or any(char not in "0123456789abcdef" for char in target):
        return "BLOCKED: target must be an exact 40-character commit SHA"
    # Stop via canonical backend identity, admission and protection guards.
    shutdown = stop if stop is not None else RuntimeShutdown(
        root=root, env=_environment(env_file)
    ).run
    result = shutdown(SCOPE_ALL)
    if not result.ok or not result.runtime_stopped:
        return "BLOCKED: canonical safe-stop refused; existing PAPER protection retained"

    def command(*argv: str) -> bool:
        try:
            completed = runner(list(argv), cwd=root, capture_output=True,
                               text=True, timeout=180, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    # Explicit fast-forward only. Never rewrite a working tree or checkout a
    # detached commit; if the target cannot be installed the robot stays stopped.
    if not command("git", "fetch", "origin", "stable/adfb50b-forward"):
        return "BLOCKED: git fetch failed after safe-stop"
    if not command("git", "merge-base", "--is-ancestor", target,
                   "origin/stable/adfb50b-forward"):
        return "BLOCKED: target is not on approved stable"
    if not command("git", "merge", "--ff-only", target):
        return "BLOCKED: fast-forward failed after safe-stop"
    if not command("git", "rev-parse", "--verify", "HEAD"):
        return "BLOCKED: unable to verify installed HEAD"
    if not command(*PREFIX, "systemctl", "start", SERVICE):
        return "BLOCKED: PAPER core start failed; no admission bypass attempted"
    return "READY: canonical safe-stop, fast-forward and PAPER core start completed; PAPER_AUTO must be confirmed separately"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed one-action PAPER maintenance")
    parser.add_argument("sha")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    args = parser.parse_args(argv)
    status = run_maintenance(args.sha, env_file=args.env_file)
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
