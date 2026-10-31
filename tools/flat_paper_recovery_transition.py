"""Exceptional PAPER FLAT-only backend lifecycle handoff.

No trading or SQL mutation. Unlike canonical STOP this may interrupt the old
backend while its reconciliation is stuck; it is NOT an ordinary operator stop.
Requires explicit operator --execute and exact expected PID, build SHA, immutable
process start token, and fresh FLAT proof under a SQLite writer barrier.

Does not deploy or restart anything. Never escalates to SIGKILL or retries an
ambiguous interruption. Production use additionally requires owner approval.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import time

from tools.flat_paper_recovery_gate import FlatRecoveryBlocked, prove_flat_recovery
from tools.runtime_intent import expected_database_identity, http_get
from tools.stop_robot_runtime import _database_path, _environment

UNIT = "bybitscanner-paper-backend.service"
ROOT = Path("/opt/BybitScanner")
PAPER_HTTP = "http://127.0.0.1:8765"
ROUTES = {
    "backend": "/api/health",
    "scanner": "/api/scanner/status",
    "autopilot": "/api/robot/autopilot",
    "protection": "/api/robot/protection-health",
}


def _assert(value: bool, reason: str) -> None:
    if not value:
        raise FlatRecoveryBlocked(reason)


def get_snapshots():
    result = {}
    for name, route in ROUTES.items():
        response = http_get(PAPER_HTTP + route, 5)
        _assert(response.status == 200, name + "_api_unavailable")
        body = response.json()
        _assert(isinstance(body, dict), name + "_api_invalid")
        result[name] = body
    return result


def _service_pid() -> int:
    def show(property_name: str) -> str:
        r = subprocess.run(
            ["systemctl", "show", "--property", property_name, "--value", UNIT],
            capture_output=True, text=True, check=False, timeout=5,
        )
        _assert(r.returncode == 0, "systemd_identity_unavailable")
        return r.stdout.strip()

    _assert(show("ActiveState") == "active", "backend_unit_not_active")
    _assert(show("Restart") == "no", "automatic_backend_restart_not_disabled")
    pid = show("MainPID")
    _assert(pid.isdecimal() and int(pid) > 1, "backend_main_pid_unproven")
    return int(pid)


def _process_start_token(pid: int) -> str:
    try:
        # proc stat field 22 is starttime; comm may contain whitespace or ')'.
        stat = Path(f"/proc/{pid}/stat").read_text()
        start = stat.rsplit(")", 1)[1].strip().split()[19]
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        cgroup = Path(f"/proc/{pid}/cgroup").read_text()
    except (OSError, IndexError, ValueError) as exc:
        raise FlatRecoveryBlocked("backend_process_provenance_missing") from exc
    _assert(
        b"-m" in cmdline and b"terminal.runtime.paper_http_server" in cmdline
        and "bybitscanner-paper-backend.service" in cgroup,
        "backend_process_command_or_unit_unproven",
    )
    _assert(start.isdecimal() and int(start) > 0, "backend_process_start_unproven")
    return start


@contextmanager
def _frozen_snapshot(path: Path):
    _assert(path.is_file(), "paper_database_missing")
    conn = None
    try:
        # BEGIN IMMEDIATE reserves the writer slot; no SQL is edited. The
        # reservation spans final durable proof and the one lifecycle signal.
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=5)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("PRAGMA query_only=ON")
        yield conn
    except sqlite3.Error as exc:
        raise FlatRecoveryBlocked("paper_writer_barrier_unavailable") from exc
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()


def execute_flat_handoff(
    *, db_path: Path, expected_identity: str, expected_pid: int,
    expected_build_sha: str, execute: bool, snapshots=None,
    service_pid=_service_pid, start_token=_process_start_token,
    send_interrupt=os.kill, is_alive=None, writer_guard=_frozen_snapshot,
    monotonic=time.monotonic, sleep=time.sleep,
) -> str:
    """One-shot SIGINT, not a systemd override and never a SIGKILL fallback."""
    _assert(expected_pid > 1, "expected_pid_invalid")
    _assert(len(expected_build_sha) == 40 and
            all(c in "0123456789abcdef" for c in expected_build_sha),
            "expected_build_sha_invalid")
    snapshots = snapshots if snapshots is not None else get_snapshots()
    _assert(snapshots["backend"].get("build_sha") == expected_build_sha,
            "installed_build_sha_changed")
    _assert(snapshots["backend"].get("process_instance_id"),
            "backend_process_instance_unproven")
    _assert(service_pid() == expected_pid, "systemd_main_pid_changed")
    token = start_token(expected_pid)
    _assert(bool(token), "backend_start_token_missing")
    with writer_guard(db_path) as conn:
        # Do not trust an earlier stand-alone FLAT snapshot.
        proof = prove_flat_recovery(
            conn, expected_identity=expected_identity, **snapshots,
        )
        _assert(proof == "FLAT_RECOVERY_EVIDENCE_PROVEN_ONLY",
                "flat_recovery_evidence_missing")
        _assert(service_pid() == expected_pid and start_token(expected_pid) == token,
                "backend_process_changed_during_proof")
        if not execute:
            return "PRECHECK_ONLY: FLAT proven under writer barrier; no process action"
        # SIGINT allows Python main() to unwind its finally: server, market
        # data, protection manager and owner runtime. Never send twice.
        send_interrupt(expected_pid, signal.SIGINT)
        probe = is_alive if is_alive is not None else (
            lambda pid: Path(f"/proc/{pid}/stat").exists()
        )
        deadline = monotonic() + 15
        while monotonic() < deadline:
            if service_pid() != expected_pid or not probe(expected_pid):
                return "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed"
            sleep(0.25)
        return "OUTCOME_UNKNOWN: single SIGINT sent, do not retry or deploy"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Exceptional FLAT-only PAPER backend handoff")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/bybitscanner/paper.env"))
    parser.add_argument("--expected-pid", type=int, required=True)
    parser.add_argument("--expected-build-sha", required=True)
    parser.add_argument("--execute", action="store_true",
                        help="One exceptional SIGINT; needs separate owner authorization")
    args = parser.parse_args(argv)
    env = _environment(args.env_file)
    try:
        result = execute_flat_handoff(
            db_path=_database_path(ROOT, env),
            expected_identity=expected_database_identity(ROOT, env),
            expected_pid=args.expected_pid,
            expected_build_sha=args.expected_build_sha,
            execute=args.execute,
        )
    except (FlatRecoveryBlocked, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"BLOCKED: {exc}; no new signal is authorized")
        return 2
    print(result)
    return 0 if result.startswith(("PRECHECK_ONLY:", "INTERRUPT_EXIT_OBSERVED:")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
