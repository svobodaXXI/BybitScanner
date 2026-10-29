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
                    clock=time.monotonic, sleep=time.sleep, readiness=None) -> str:
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
    # Ignore explicitly ignored runtime DB/log files but refuse any tracked
    # or untracked source change before touching an actively protected service.
    working = execute("git", "status", "--porcelain", "--untracked-files=normal")
    if working is None or working.returncode != 0 or working.stdout.strip():
        return "BLOCKED: working tree contains changes"
    branch = execute("git", "branch", "--show-current")
    if (branch is None or branch.returncode != 0
            or branch.stdout.strip() != "stable/adfb50b-forward"):
        return "BLOCKED: installed branch is not canonical stable"
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
    # The oneshot says only that startup was requested; do not report READY
    # unless the PAPER backend has independently proven its safety.
    from tools.runtime_intent import http_get
    try:
        health = http_get("http://127.0.0.1:8765/api/health", 5)
        protection = http_get("http://127.0.0.1:8765/api/robot/protection-health", 5)
        scanner = http_get("http://127.0.0.1:8765/api/scanner/status", 5)
        autopilot = http_get("http://127.0.0.1:8765/api/robot/autopilot", 5)
        h, p, s, a = (reply.json() for reply in
                       (health, protection, scanner, autopilot))
        if not all(reply.status == 200 for reply in
                   (health, protection, scanner, autopilot)):
            raise ValueError("backend verification endpoint failed")
        if (h.get("mode") != "paper" or h.get("paper_live_safe") is not True
                or p.get("healthy") is not True
                or s.get("mode") != "SCANNER_RUNNING"
                or a.get("mode") != "PAPER_AUTO"):
            raise ValueError("PAPER state not ready")
    except (ValueError, KeyError, OSError, TypeError):
        return "BLOCKED: PAPER core started but PAPER_AUTO/protection readiness not proven; do not enable new admission"
    # An enabled Autopilot is not proof that Robot can admit trades.
    # Read the canonical durable state without mutating the PAPER DB.
    try:
        if readiness is not None:
            if not readiness():
                raise ValueError("Robot readiness rejected")
        else:
            import sqlite3
            from tools.stop_robot_runtime import _database_path
            db = _database_path(root, _environment(env_file))
            with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
                row = conn.execute(
                    "SELECT mode, recovery_status FROM robot_runtime_state "
                    "WHERE trading_account_id='paper'"
                ).fetchone()
            if row != ("ROBOT_RUNNING", "READY"):
                raise ValueError("Robot is not READY")
            if _environment(env_file).get("BYBITSCANNER_STOP_REENTRY_AUTO") != "1":
                raise ValueError("STOP reentry is not enabled")
    except Exception:
        return "BLOCKED: PAPER core started but Robot READY/reentry not proven"
    return "READY: exact HEAD, PAPER-only, Robot, Scanner, PAPER_AUTO, reentry and protection confirmed"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed one-action PAPER maintenance")
    parser.add_argument("sha")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    parser.add_argument("--wait-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    status = run_maintenance(args.sha, env_file=args.env_file, wait_seconds=args.wait_seconds)
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
