"""Exact one-shot FUSDT Box STOP reconciliation via the existing owner monolith.

Incident-specific: never a general RELEASE/STOP/PAPER recovery or an alternative
backend controller. A failed or uncertain POST consumes its one-shot receipt.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

OLD_SHA = "7dcac2af9bac1bf1583a2b9ff8d1b1fb880acda3"
TARGET_SHA = "6cb6ea4c0d767227b6aa7f84faa35d141daebc47"
CANDIDATE = "box-robot-21ed39d6dff9aeb6ed65c1eb147410d646b999426cb86194a4a879d40be127f1"
REASON = "ROBOT_BOX_TAKE_TRADE_MISSING symbol=FUSDT candidate_id=" + CANDIDATE
STOP_EXIT_MS = 1795061215475


def _attest(sha: str, root: Path, env_file: Path | None, *, after: bool = False) -> str | None:
    """Read-only proof for the sole approved incident and current runtime owner."""
    from terminal.domain.models import TradingAccountId
    from terminal.persistence.sqlite_store import SQLiteStore
    from terminal.statistics.reader import RobotStatisticsReader
    from tools.paper_maintenance import _active_required_flat_proof
    from tools.runtime_intent import expected_database_identity, http_get
    from tools.stop_robot_runtime import _database_path, _environment
    from tools.vps_release_identity import verify_release

    if sha != OLD_SHA or verify_release(root) != sha:
        return None
    env = _environment(env_file)
    db = _database_path(root, env)
    expected = ("ROBOT_RUNNING", "PAUSED", None) if after else (
        "ROBOT_RUNNING", "RECONCILIATION_REQUIRED", REASON
    )
    if _active_required_flat_proof(db) != expected:
        return None
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        store = SQLiteStore(conn, db, 2000)
        candidate = store.get_robot_candidate(CANDIDATE)
        # The canonical flat proof above accepts only APPROVED candidates
        # independently shown to lack trades, fills, limits and obligations.
        # Reject OPEN, but do not reject safe pre-entry APPROVED candidates.
        active = store.load_active_robot_candidate_states(TradingAccountId("paper"))
        if (candidate is None or candidate.status != "CLOSED"
                or candidate.symbol.value != "FUSDT"
                or any(item.status != "APPROVED" for item in active)):
            return None
    completed = tuple(
        t for t in RobotStatisticsReader(db).load_completed_trades(
            trading_account_id="paper"
        ) if t.candidate_id == CANDIDATE
    )
    if (len(completed) != 1 or completed[0].symbol != "FUSDT"
            or completed[0].exit_reason != "STOP"
            or completed[0].exit_time_ms != STOP_EXIT_MS):
        return None

    def get(url: str) -> dict:
        reply = http_get(url, 5)
        value = reply.json()
        if reply.status != 200 or not isinstance(value, dict):
            raise ValueError("owner endpoint unavailable")
        return value

    base = "http://127.0.0.1:8765"
    health = get(base + "/api/health")
    scanner = get(base + "/api/scanner/status")
    autopilot = get(base + "/api/robot/autopilot")
    robot = get(base + "/api/robot/state")
    protection = get(base + "/api/robot/protection-health")
    telegram = get("http://127.0.0.1:8766/health")
    identity = expected_database_identity(root, env)
    instance = health.get("process_instance_id")
    if not (
        health.get("ok") is True and health.get("component") == "paper_backend"
        and health.get("mode") == "paper" and health.get("paper_live_safe") is True
        and health.get("build_sha") == sha and health.get("database_identity") == identity
        and isinstance(instance, str) and bool(instance)
        and scanner.get("ok") is True and scanner.get("mode") == "SCANNER_STOPPED"
        and autopilot.get("ok") is True and autopilot.get("mode") == "OFF"
        and autopilot.get("trading_account_id") == {"value": "paper"}
        and robot.get("mode") == expected[0] and robot.get("recovery_status") == expected[1]
        and (after or robot.get("reason") == REASON)
        and protection.get("ok") is True and protection.get("healthy") is True
        and protection.get("covered_symbols") == []
        and protection.get("armed_symbols") == []
        and protection.get("coverage_roles") == {}
        and protection.get("unhealthy_symbols") == {}
        and telegram.get("component") == "telegram_monitoring"
        and telegram.get("status") == "ready"
        and telegram.get("database_identity") == identity
    ):
        return None
    return instance


def reconcile_once(
    sha: str, *, root: Path = Path("/opt/BybitScanner"),
    env_file: Path | None = Path("/etc/bybitscanner/paper.env"),
    journal_root: Path = Path("/var/lib/bybitscanner-release-transactions"),
    trusted_uid: int = 0,
) -> str:
    """Exactly one canonical POST, never STOP/start/switch/SQL mutation."""
    from tools.paper_maintenance import _known_drain_receipt
    from tools.runtime_intent import http_post_json
    from tools.vps_gitless_release_activate import _sync_directory

    try:
        if (sha != OLD_SHA or os.geteuid() != trusted_uid
                or not root.is_dir() or root.is_symlink()
                or not journal_root.is_dir() or journal_root.is_symlink()
                or journal_root.stat().st_uid != trusted_uid
                or journal_root.stat().st_mode & 0o077):
            return "BLOCKED: reconcile_pinned_release_or_owner_unproven"
        if (not _known_drain_receipt(journal_root, TARGET_SHA, sha, phase="deferred",
                                     uid=trusted_uid)
                or _known_drain_receipt(journal_root, TARGET_SHA, sha,
                                        phase="continuation-invoked", uid=trusted_uid)
                or _known_drain_receipt(journal_root, TARGET_SHA, sha,
                                        phase="completed", uid=trusted_uid)):
            return "BLOCKED: reconcile_known_drain_receipt_unproven"
        first = _attest(sha, root, env_file)
        if first is None or _attest(sha, root, env_file) != first:
            return "BLOCKED: reconcile_runtime_or_STOP_ledger_unproven"
        marker = journal_root / (".owner-fusdt-box-stop-reconcile-" + TARGET_SHA)
        try:
            fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            return "BLOCKED: reconcile_once_already_invoked; no_replay"
        with os.fdopen(fd, "wb") as seal:
            seal.write(("ONE_SHOT_FUSDT_STOP_RECONCILE:" + sha + ":" + TARGET_SHA + "\n").encode("ascii"))
            seal.flush()
            os.fsync(seal.fileno())
        _sync_directory(journal_root)
        # No re-post for any outcome, even HTTP timeout or a lost response.
        reply = http_post_json("http://127.0.0.1:8765/api/robot/reconcile", {}, 180)
        body = reply.json()
        if (reply.status != 200 or not isinstance(body, dict)
                or body.get("ok") is not True or body.get("success") is not True
                or body.get("mode") != "ROBOT_RUNNING"
                or body.get("recovery_status") != "PAUSED"):
            return "BLOCKED: reconcile_post_not_confirmed; no_replay"
        if _attest(sha, root, env_file, after=True) != first:
            return "BLOCKED: reconcile_postconditions_unproven; no_replay"
        return "READY: FUSDT STOP reconciled to PAUSED; Scanner STOPPED, Autopilot OFF"
    except Exception as exc:
        return ("BLOCKED: reconcile_unproven:" + type(exc).__name__
                + "; no_replay, no_STOP, no_deployment")
