"""Fixed GitHub-owner-comment -> PAPER VPS operation. No general remote shell.

The GitHub Actions workflow runs only from the default (main) branch. It
authenticates a specific OWNER-authored comment on the fixed operations issue;
the remote side independently checks every immutable state before the one
protected maintenance coordinator call. This is not a LIVE executor.
"""
from __future__ import annotations

import json
import sqlite3
from urllib import request as urlrequest
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import stat

REPO = "svobodaXXI/BybitScanner"
OWNER = "svobodaXXI"
ISSUE = 823
BRANCH = "stable/adfb50b-forward"
ORIGIN = "https://github.com/svobodaXXI/BybitScanner.git"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUEST = re.compile(r"/paper-vps (preflight|execute|diagnose) ([0-9a-f]{40})\Z")
TARGET = re.compile(r"root@[A-Za-z0-9.-]{1,253}\Z")
VENV = Path("/opt/BybitScanner/venv/bin/python")
TRANSACTIONS = Path("/var/lib/bybitscanner-release-transactions")
PINNED_REMOTE = Path("/usr/local/libexec/bybitscanner-paper-vps.py")
REMOTE_REQUEST = re.compile(r"(preflight|execute|diagnose) ([0-9a-f]{40})\Z")


def authorized_remote_request(original: str | None) -> tuple[str, str]:
    """Accept only sshd's original literal operation and exact Git SHA.

    The root-owned helper MUST be installed outside the Git checkout and
    bound to a dedicated SSH key via authorized_keys command= and restrict.
    An unforced root key will not be given a runnable Python SSH command.
    """
    installed = Path(__file__)
    try:
        meta = installed.lstat()
    except OSError as exc:
        raise ValueError("pinned_remote_missing") from exc
    if (installed != PINNED_REMOTE
            or not stat.S_ISREG(meta.st_mode)
            or meta.st_uid != 0 or meta.st_mode & 0o077
            or not isinstance(original, str)):
        raise ValueError("untrusted_remote_install_or_command")
    match = REMOTE_REQUEST.fullmatch(original)
    if match is None:
        raise ValueError("unsupported_ssh_original_command")
    return match.group(1), match.group(2)


# The source is executed by the already-installed PAPER venv using the pinned
# release staging as the import root; every HTTP probe precedes any DB snapshot.
PREFLIGHT = """
from pathlib import Path
import sys
from tools.vps_release_identity import create_manifest
from tools.vps_gitless_release_activate import inspect_staged_release
from tools.flat_paper_recovery_transition import get_snapshots
from tools.paper_two_orphan_proof import inspect_read_only, PROOF_LABEL
from tools.runtime_intent import expected_database_identity
from tools.stop_robot_runtime import _database_path, _environment
stage, sha = Path(sys.argv[1]), sys.argv[2]
try:
    manifest = create_manifest(stage, sha)
    assert manifest["build_sha"] == sha
    release = inspect_staged_release(
        sha, stage=stage, root=Path("/opt/BybitScanner"))
    assert release["new"]["build_sha"] == sha
    root = Path("/opt/BybitScanner")
    env = _environment(Path("/etc/bybitscanner/paper.env"))
    identity = expected_database_identity(root, env)
    snapshots = get_snapshots()
    result = inspect_read_only(_database_path(root, env),
                               expected_identity=identity, snapshots=snapshots)
    if result != PROOF_LABEL:
        raise ValueError("unexpected_two_orphan_proof_result")
    print("PREFLIGHT_PASS: exact staged release and immutable JASMY/FLOW proof",
          flush=True)
except Exception as exc:
    print("BLOCKED: " + type(exc).__name__ + ":" + str(exc)[:240], flush=True)
    sys.exit(2)
"""


def parse_request(event: dict) -> tuple[str, str]:
    if not isinstance(event, dict) or event.get("action") != "created":
        raise ValueError("not_new_comment")
    if not isinstance(event.get("repository"), dict) or (
        event["repository"].get("full_name") != REPO
    ):
        raise ValueError("foreign_repository")
    issue = event.get("issue")
    comment = event.get("comment")
    if not isinstance(issue, dict) or issue.get("number") != ISSUE or (
        issue.get("pull_request")
    ):
        raise ValueError("not_dedicated_issue")
    if not isinstance(comment, dict) or not isinstance(comment.get("user"), dict):
        raise ValueError("missing_comment_identity")
    if (comment["user"].get("login") != OWNER
            or comment.get("author_association") != "OWNER"):
        raise ValueError("comment_not_owner")
    body = comment.get("body")
    match = REQUEST.fullmatch(body) if isinstance(body, str) else None
    if match is None:
        raise ValueError("unsupported_request")
    return match.group(1), match.group(2)


def validate_target(value: str) -> str:
    if TARGET.fullmatch(value) is None or ".." in value:
        raise ValueError("invalid_root_ssh_target")
    return value


def _run(argv: list[str], *, cwd: Path | None = None,
         env: dict[str, str] | None = None, timeout: int | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True,
                            text=True, timeout=timeout, check=False)
    if result.returncode:
        # git stderr or Python tracebacks can include secrets; print only
        # the explicit, bounded BLOCKED status from an attestation module.
        blocked = next((line[:300] for line in reversed(result.stdout.splitlines())
                        if line.startswith("BLOCKED:")), None)
        raise RuntimeError(blocked or f"command_failed_exit_{result.returncode}")
    return result.stdout.strip()


def _stage(sha: str) -> Path:
    if SHA.fullmatch(sha) is None:
        raise ValueError("invalid_target_sha")
    stage = Path(tempfile.mkdtemp(prefix="bybitscanner-p0-" + sha[:12] + "-",
                                  dir="/var/tmp"))
    _run(["git", "clone", "--quiet", "--depth=1", "--single-branch",
          "--branch", BRANCH, "--no-checkout", ORIGIN, str(stage)], timeout=180)
    _run(["git", "-C", str(stage), "checkout", "--quiet", "--detach", sha],
         timeout=60)
    if _run(["git", "-C", str(stage), "rev-parse", "HEAD"]) != sha:
        raise RuntimeError("staged_sha_mismatch")
    if _run(["git", "-C", str(stage), "status", "--porcelain"]):
        raise RuntimeError("staged_worktree_dirty")
    head = _run(["git", "ls-remote", "--heads", ORIGIN, "refs/heads/" + BRANCH],
                timeout=30).split()
    if len(head) != 2 or head[0] != sha:
        raise RuntimeError("remote_stable_head_changed")
    return stage


def _record_one_shot(sha: str) -> None:
    """Fence even a failed/unknown coordinator invocation before it occurs."""
    parent = TRANSACTIONS.parent
    if (not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != 0 or parent.stat().st_mode & 0o022):
        raise RuntimeError("untrusted_transaction_parent")
    if not TRANSACTIONS.exists():
        TRANSACTIONS.mkdir(mode=0o700)
    if (not TRANSACTIONS.is_dir() or TRANSACTIONS.is_symlink()
            or TRANSACTIONS.stat().st_uid != 0
            or TRANSACTIONS.stat().st_mode & 0o077):
        raise RuntimeError("untrusted_transaction_directory")
    marker = TRANSACTIONS / (".chatops-invoked-" + sha)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    with os.fdopen(os.open(marker, flags, 0o600), "w") as file:
        file.write(sha + "\n")
        file.flush()
        os.fsync(file.fileno())
    fd = os.open(TRANSACTIONS, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# Restricted diagnostics: fixed GET/SELECT and systemctl is-active only.
# No shell, arbitrary filesystem reads, user-supplied SQL, journal dumps, or
# secrets. This mode never stages code or writes one-shot transaction markers.
def _read_only_diag(sha: str, *, root: Path = Path("/opt/BybitScanner"),
                    env_file: Path = Path("/etc/bybitscanner/paper.env"),
                    transactions: Path = TRANSACTIONS) -> dict:
    db_value = "paper_runtime.sqlite3"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("BYBITSCANNER_PAPER_DB="):
                db_value = line.partition("=")[2].strip().strip("\\\"'")
    if not db_value or any(c in db_value for c in ("\\x00", "\\n", "$")):
        raise ValueError("invalid_database_path")
    db_path = Path(db_value)
    if not db_path.is_absolute():
        db_path = root / db_path
    result = {"kind": "PAPER_STOP_READ_ONLY", "version": 1, "sha": sha,
              "units": {}, "api": {}, "db": {},
              "transaction": {
                  "chatops_marker": (transactions / (".chatops-invoked-" + sha)).is_file(),
                  "stop_marker": (transactions / (".stop-invoked-" + sha)).is_file(),
                  "install_journal": (transactions / sha).is_dir(),
              }}
    for unit in ("bybitscanner-paper-backend.service",
                 "bybitscanner-telegram.service",
                 "bybitscanner-paper-start.service"):
        try:
            p = subprocess.run(
                ["/usr/bin/systemctl", "is-active", unit],
                capture_output=True, text=True, timeout=4, check=False)
            status = p.stdout.strip()
            result["units"][unit] = (
                status if status in ("active", "inactive", "failed",
                                     "activating", "deactivating") else "unknown")
        except (OSError, subprocess.TimeoutExpired):
            result["units"][unit] = "unknown"
    for label, endpoint in (
        ("health", "/api/health"), ("scanner", "/api/scanner/status"),
        ("autopilot", "/api/robot/autopilot"),
        ("protection", "/api/robot/protection-health"),
    ):
        try:
            req = urlrequest.Request("http://127.0.0.1:8765" + endpoint, method="GET")
            with urlrequest.urlopen(req, timeout=3) as response:
                raw = response.read(32769)
                if response.status != 200 or len(raw) > 32768:
                    raise ValueError("bad_http_result")
                payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("bad_api_shape")
            if label == "health":
                build = payload.get("build_sha")
                result["api"][label] = {
                    "reachable": True, "ok": payload.get("ok") is True,
                    "paper": payload.get("mode") == "paper",
                    "paper_live_safe": payload.get("paper_live_safe") is True,
                    "build_sha": build if isinstance(build, str)
                                 and SHA.fullmatch(build) else "unknown",
                }
            elif label in ("scanner", "autopilot"):
                state = payload.get("mode")
                result["api"][label] = {
                    "reachable": True,
                    "mode": state if state in (
                        "SCANNER_STOPPED", "SCANNER_RUNNING", "OFF", "PAPER_AUTO"
                    ) else "unknown",
                }
            else:
                failures = payload.get("unhealthy_symbols")
                result["api"][label] = {
                    "reachable": True, "healthy": payload.get("healthy") is True,
                    "unhealthy_count": len(failures) if isinstance(failures, dict) else None,
                }
        except (OSError, ValueError, TypeError, UnicodeError):
            result["api"][label] = {"reachable": False}
    if not db_path.is_file() or db_path.is_symlink():
        result["db"] = {"available": False, "reason": "missing_or_symlink"}
        return result
    try:
        with sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro",
                             uri=True, timeout=3) as conn:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            try:
                def one(sql: str, params: tuple = ()):
                    row = conn.execute(sql, params).fetchone()
                    return row[0] if row else None
                runtime = conn.execute(
                    "SELECT mode,recovery_status FROM robot_runtime_state "
                    "WHERE trading_account_id='paper'").fetchone()
                bnc_rows = conn.execute(
                    "SELECT state_revision,robot_state_json "
                    "FROM robot_candidates WHERE trading_account_id='paper' "
                    "AND symbol='BNCUSDT' AND status='APPROVED'").fetchall()
                bnc = {"approved_count": len(bnc_rows)}
                if len(bnc_rows) == 1:
                    revision, raw_state = bnc_rows[0]
                    bnc["revision"] = revision if type(revision) is int else "invalid"
                    try:
                        state = json.loads(raw_state) if isinstance(raw_state, str) else None
                        phase = state.get("phase") if isinstance(state, dict) else None
                        bnc["phase"] = phase if phase in (
                            "RETEST_DETECTED", "BOX_ENTRY_READY", "ENTRY_PENDING",
                            "CLOSED", "EXPIRED"
                        ) else "unknown"
                        bnc["state_type"] = (
                            "null" if raw_state is None else
                            "json_object" if isinstance(state, dict) else "invalid")
                    except (ValueError, TypeError):
                        bnc["state_type"] = "invalid"
                        bnc["phase"] = "unknown"
                result["db"] = {
                    "available": True, "quick_check": one("PRAGMA quick_check") == "ok",
                    "robot_mode": runtime[0] if runtime else "missing",
                    "robot_recovery": runtime[1] if runtime else "missing",
                    "scanner_mode": one("SELECT mode FROM scanner_runtime_state "
                                        "WHERE trading_account_id='paper'"),
                    "autopilot_mode": one("SELECT mode FROM robot_autopilot_state "
                                          "WHERE trading_account_id='paper'"),
                    "pending_limits": one(
                        "SELECT COUNT(*) FROM paper_limit_orders "
                        "WHERE trading_account_id='paper' "
                        "AND status NOT IN ('cancelled','filled')"),
                    "open_robot_trades": one(
                        "SELECT COUNT(*) FROM robot_trades "
                        "WHERE trading_account_id='paper' AND exit_time_ms IS NULL"),
                    "approvals": one(
                        "SELECT COUNT(*) FROM robot_candidates "
                        "WHERE trading_account_id='paper' AND status='APPROVED'"),
                    "bnc": bnc,
                }
            finally:
                conn.rollback()
    except (sqlite3.Error, OSError, ValueError):
        result["db"] = {"available": False, "reason": "readonly_snapshot_unavailable"}
    return result


def remote(mode: str, sha: str) -> int:
    if mode not in {"preflight", "execute", "diagnose"} or SHA.fullmatch(sha) is None:
        print("BLOCKED: invalid_exact_operation_or_sha", flush=True)
        return 2
    if os.geteuid() != 0 or not VENV.is_file():
        print("BLOCKED: root_operator_or_existing_venv_unavailable", flush=True)
        return 2
    try:
        if mode == "diagnose":
            print("DIAGNOSE_READ_ONLY: " +
                  json.dumps(_read_only_diag(sha), sort_keys=True), flush=True)
            return 0
        stage = _stage(sha)
        print("STAGING_PASS: exact SHA " + sha, flush=True)
        env = {**os.environ, "PYTHONPATH": str(stage),
               "PYTHONDONTWRITEBYTECODE": "1"}
        print(_run([str(VENV), "-c", PREFLIGHT, str(stage), sha],
                   cwd=stage, env=env, timeout=120), flush=True)
        if mode == "preflight":
            return 0
        _record_one_shot(sha)
        print("EXECUTE_INTENT_FSYNCED: no replay after unknown result", flush=True)
        outcome = _run([
            str(VENV), "-m", "tools.paper_maintenance", sha,
            "--staged-gitless-editor-only", str(stage),
            "--dual-orphan-handoff-20261103",
            "--start-paper-after-editor",
        ], cwd=stage, env=env)
        last = outcome.splitlines()[-1] if outcome else ""
        if not last.startswith("READY:"):
            raise RuntimeError("canonical_final_acceptance_unproven")
        print("FINAL_ACCEPTANCE: " + last[:450], flush=True)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print("BLOCKED: " + type(exc).__name__ + ":" + str(exc)[:320],
              flush=True)
        return 2


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "request":
        try:
            mode, sha = parse_request(json.loads(Path(argv[1]).read_text()))
            with open(argv[2], "a", encoding="utf-8") as output:
                output.write("mode=" + mode + "\nsha=" + sha + "\n")
            return 0
        except (OSError, ValueError, KeyError) as exc:
            print("BLOCKED: invalid_owner_request:" + type(exc).__name__)
            return 2
    if len(argv) == 1 and argv[0] == "forced":
        try:
            mode, sha = authorized_remote_request(
                os.environ.get("SSH_ORIGINAL_COMMAND"))
        except ValueError as exc:
            print("BLOCKED: " + str(exc))
            return 2
        return remote(mode, sha)
    if len(argv) == 2 and argv[0] == "check-target":
        try:
            validate_target(argv[1])
            return 0
        except ValueError:
            print("BLOCKED: invalid_ssh_target")
            return 2
    print("BLOCKED: unsupported_operation")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
