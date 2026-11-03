"""Single owner command for safe PAPER maintenance on an already running VPS.

No direct database writes, no process kills, no LIVE operations. A blocked stop
does not advance to git or systemd: protection stays with the current backend.
"""
from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from tools.stop_robot_runtime import RuntimeShutdown, SCOPE_ALL, _environment


def _durable_editor_freeze(root: Path, env_file: Path | None) -> str:
    """Prove admission freeze from the existing PAPER SQLite, without writing it."""
    import sqlite3
    from tools.runtime_intent import expected_database_identity
    from tools.stop_robot_runtime import _database_path

    env = _environment(env_file)
    path = _database_path(root, env)
    if not path.is_file() or path.is_symlink():
        raise ValueError("PAPER_database_missing_or_symlink")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2.0) as conn:
        conn.execute("PRAGMA query_only=ON")
        if conn.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("PAPER_database_integrity_unproven")
        if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("PAPER_database_foreign_key_conflict")
        scanner = conn.execute(
            "SELECT mode FROM scanner_runtime_state WHERE trading_account_id='paper'"
        ).fetchone()
        autopilot = conn.execute(
            "SELECT mode FROM robot_autopilot_state WHERE trading_account_id='paper'"
        ).fetchone()
    if scanner != ("SCANNER_STOPPED",) or autopilot != ("OFF",):
        raise ValueError("EDITOR_ONLY_requires_durable_Scanner_STOPPED_and_Autopilot_OFF")
    return expected_database_identity(root, env)


def _editor_runtime_ready(target: str, database_identity: str) -> bool:
    """Read-only owner proof. Never substitute an HTTP timeout for process absence."""
    from tools.runtime_intent import http_get

    try:
        health = http_get("http://127.0.0.1:8765/api/health", 3)
        scanner = http_get("http://127.0.0.1:8765/api/scanner/status", 3)
        autopilot = http_get("http://127.0.0.1:8765/api/robot/autopilot", 3)
        telegram = http_get("http://127.0.0.1:8766/health", 3)
        if not all(x.status == 200 for x in (health, scanner, autopilot, telegram)):
            return False
        h, s, a, t = (x.json() for x in (health, scanner, autopilot, telegram))
        return (
            isinstance(h, dict) and h.get("ok") is True
            and h.get("component") == "paper_backend"
            and h.get("mode") == "paper"
            and h.get("paper_live_safe") is True
            and h.get("build_sha") == target
            and h.get("database_identity") == database_identity
            and isinstance(s, dict) and s.get("mode") == "SCANNER_STOPPED"
            and isinstance(a, dict) and a.get("mode") == "OFF"
            and isinstance(t, dict) and t.get("component") == "telegram_monitoring"
            and t.get("status") == "ready"
            and t.get("database_identity") == database_identity
        )
    except (OSError, ValueError, TypeError, KeyError, Exception):
        return False


def resume_installed_release(
    target: str, *, root: Path, env_file: Path | None,
    runner=subprocess.run, resume_proof=None, freeze_proof=None,
    runtime_ready=None,
) -> str:
    """Resume a VERIFIED, already-installed Gitless release without STOP/deploy.

    An active-but-unreachable Backend cannot pass the stopped/listener proof.
    Each service start is attempted once; on unknown outcome, the next run
    must independently re-observe readiness, not re-send STOP or SIGINT.
    This is not an installer, and never starts Scanner or PAPER_AUTO.
    """
    from tools.vps_release_resume import ResumeBlocked, check_resume

    if len(target) != 40 or any(c not in "0123456789abcdef" for c in target):
        return "BLOCKED: invalid_approved_target"
    try:
        identity = (freeze_proof or _durable_editor_freeze)(root, env_file)
        if not isinstance(identity, str) or len(identity) != 64:
            return "BLOCKED: PAPER_database_identity_unproven"
    except (OSError, ValueError, sqlite3.Error) as exc:
        return "BLOCKED: editor_only_freeze_unproven:" + type(exc).__name__
    probe = runtime_ready or _editor_runtime_ready
    if probe(target, identity):
        return "READY: exact installed PAPER release, Telegram and EDITOR_ONLY already proven; no mutation"
    try:
        receipt = (resume_proof or check_resume)(target, root=root)
        if not isinstance(receipt, str) or not receipt.startswith("RESUME_READY:"):
            raise ResumeBlocked("installed_release_resume_unproven")
    except (ResumeBlocked, OSError, ValueError) as exc:
        return "BLOCKED: installed_release_not_stopped_and_verified:" + type(exc).__name__

    def command(*argv: str) -> bool:
        try:
            answer = runner(list(argv), cwd=root, capture_output=True, text=True,
                            timeout=180, check=False)
            return answer.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    if not command(*PREFIX, str(root / "venv/bin/python"), "-m",
                   "tools.vps_systemd_unit_prepare"):
        return "BLOCKED: unit_prepare_failed_or_unknown; no service started"
    if not command(*PREFIX, "systemctl", "start", "bybitscanner-paper-backend.service"):
        return "BLOCKED: backend_start_failed_or_unknown; do not retry before observing owner"
    if not command(*PREFIX, "systemctl", "start", "bybitscanner-telegram.service"):
        return "BLOCKED: telegram_start_failed_or_unknown; Backend preserved, no trade ingress requested"
    if not probe(target, identity):
        return "BLOCKED: EDITOR_ONLY_postconditions_unproven; no Scanner or PAPER_AUTO requested"
    return "READY: exact installed PAPER release, Telegram and EDITOR_ONLY proven; no Scanner/PAPER_AUTO start"


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
    # An installed Gitless PAPER tree cannot be upgraded with git merge.
    # Reject this known VPS layout BEFORE attempting a live runtime stop.
    # The approved immutable-release activation must be provided by the
    # unified service path, never by hot-patching an active checkout.
    if not (root / ".git").is_dir():
        return "BLOCKED: gitless_install_requires_verified_immutable_release_switch; runtime unchanged"

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
    # This is a trading/runtime mutation, not a health probe. An ambiguous
    # response cannot authorize a second STOP, even after a waiting period.
    # All retries/resumption must first observe exact owner/process state.
    result = shutdown(SCOPE_ALL)
    if not (result.ok and result.runtime_stopped):
        return "BLOCKED: canonical safe-stop unproven; no mutation retry; PAPER protection retained"

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
    parser.add_argument("--wait-seconds", type=float, default=0)
    parser.add_argument("--resume-installed-editor-only", action="store_true",
                        help="only after an exact Gitless release was safely installed")
    args = parser.parse_args(argv)
    if args.resume_installed_editor_only:
        status = resume_installed_release(args.sha, root=REPO, env_file=args.env_file)
    else:
        status = run_maintenance(args.sha, env_file=args.env_file,
                                 wait_seconds=args.wait_seconds)
    print(status)
    return 0 if status.startswith("READY:") else 2


if __name__ == "__main__":
    sys.exit(main())
