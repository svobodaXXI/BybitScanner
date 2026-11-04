"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from tools.stop_robot_runtime import RuntimeShutdown, SCOPE_ALL, _environment

REPO = Path("/opt/BybitScanner")
SERVICE = "bybitscanner-paper-start.service"
PREFIX = ("sudo", "-n")
# Stable outside an immutable release tree: a process restart or failed
# deploy must not erase evidence that a mutating STOP might have been sent.
STOP_ATTEMPT_PATH = Path("/var/lib/bybitscanner/paper-maintenance/stop-attempt.json")


def _claim_stop_once(path: Path, target: str) -> bool:
    """Durably claim this host's one STOP attempt *before* any mutation.

    O_EXCL prevents a concurrent second caller. A truncated/unknown receipt
    also remains consumed after a crash: never infer that STOP did not happen.
    There is deliberately no delete/reset/retry path in this command.
    """
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink():
            return False
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
    except OSError:
        return False
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"schema_version": 1, "target_sha": target,
                       "stop_attempt": "claimed_before_invocation"}, stream)
            stream.write("\\n")
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    except (OSError, ValueError):
        # Leave even a partially written marker intact: STOP could already
        # have been sent in a different process with the same durable path.
        return False


def run_maintenance(target: str, *, root: Path = REPO, runner=subprocess.run,
                    stop=None, env_file: Path | None = None,
                    wait_seconds: float = 0, poll_seconds: float = 30,
                    clock=time.monotonic, sleep=time.sleep, readiness=None,
                    attempt_path: Path | None = None) -> str:
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
    # The canonical ALL stop is a potentially mutating operation. Repeating it
    # after a 409, timeout, lost response or uncertain SIGINT outcome may replay
    # a non-idempotent action. In particular, an old backend may still protect
    # a PAPER position even if the operator's HTTP response was lost.
    #
    # Never retry an entire STOP as a polling mechanism. A future maintenance
    # resume path must use read-only, identity-bound observed state to determine
    # whether a *different* stage is now legal.
    # Claim is intentionally after read-only preflight and before the first
    # irreversible stop step. The claim is never cleared on 409, timeout,
    # crash, successful STOP, restart or a different target SHA.
    if not _claim_stop_once(attempt_path if attempt_path is not None else STOP_ATTEMPT_PATH,
                            target):
        return (
            "BLOCKED: prior or unprovable PAPER maintenance STOP attempt; "
            "no repeated STOP, release switch or start; use read-only "
            "identity-bound recovery"
        )
    try:
        result = shutdown(SCOPE_ALL)
    except Exception:
        # A broken transport or helper may fail *after* an irreversible side
        # effect. The caller has no authority to guess the outcome or retry.
        return (
            "BLOCKED: canonical safe-stop outcome unknown; no repeated STOP, "
            "release switch or start; observe runtime state before recovery"
        )
    if not (
        getattr(result, "ok", None) is True
        and getattr(result, "runtime_stopped", None) is True
    ):
        return (
            "BLOCKED: canonical safe-stop not proven; no repeated STOP, "
            "release switch or start; PAPER backend retained when present"
        )

    if not command("git", "merge", "--ff-only", target):
        return "BLOCKED: fast-forward failed after safe-stop"
    installed = execute("git", "rev-parse", "--verify", "HEAD")
    if installed is None or installed.returncode != 0 or installed.stdout.strip() != target:
        return "BLOCKED: installed HEAD differs from approved target"
    # The target release owns this narrow helper. Reload and prove all three
    # installed units are loaded/stopped before any conditional reset-failed.
    # Do not start the PAPER core after an ambiguous systemd preparation.
    if not command(*PREFIX, str(root / "venv/bin/python"), "-m",
                   "tools.vps_systemd_unit_prepare"):
        return "BLOCKED: PAPER systemd units not proven ready; no start attempted"
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
    parser.add_argument("--wait-seconds", type=float, default=0,
                        help="Legacy compatibility only; mutating STOP is never retried")
    args = parser.parse_args(argv)
    status = run_maintenance(args.sha, env_file=args.env_file, wait_seconds=args.wait_seconds)
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
