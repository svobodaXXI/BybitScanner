"""Protected, incident-scoped proof of the 26 Nov read-only STOP refusal.

Retire only the exact abandoned intent; never synthesize a successful STOP.
The original marker is retained, and a successor must execute the normal
canonical STOP, installation and PAPER readiness gates.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
from pathlib import Path

from tools.vps_gitless_release_activate import _sync_directory, _trusted_file

OLD = "9d88a1f8e6bff8544a864ed79456a54df8927ae5"
PRIOR = "a8909e073ffc33301cff179b7d9339d072be0ef5"
REQUEST = "ae682fba5a6d4a678b830fdef422cb93"
MARKER_MS = 1795704570764
AUTOPILOT_VERSION = 64
AUTOPILOT_UPDATED_MS = 1795614439529
UNIT = "bybitscanner-owner-" + REQUEST + ".service"
DESCRIPTION = "BybitScanner update-and-start " + PRIOR + " origin=win-pc"
REFUSAL = ("BLOCKED: canonical_safe_stop_unproven: STOP BLOCKED: "
           "Autopilot state unavailable; runtime kept alive; no retry, no deployment")
MARKER = b"STOP_INVOKED; not install authorization\\n"
RECEIPT = (f"READ_ONLY_STOP_REFUSAL:{OLD}:{PRIOR}:{REQUEST}:"
           f"{MARKER_MS}:{AUTOPILOT_VERSION}:{AUTOPILOT_UPDATED_MS}\n").encode("ascii")


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _paths(directory):
    return (directory / (".stop-invoked-" + PRIOR),
            directory / (".readonly-stop-refusal-proven-" + PRIOR))


def _journal_preflight(directory, uid):
    parent = directory.parent
    for path, mask in ((parent, 0o022), (directory, 0o077)):
        info = path.lstat()
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid
                 and not info.st_mode & mask, "untrusted_readonly_stop_journal")
    marker, receipt = _paths(directory)
    _require(_trusted_file(marker, uid) == MARKER
             and not marker.stat().st_mode & 0o077
             and marker.stat().st_mtime_ns // 1000000 == MARKER_MS,
             "readonly_stop_marker_mismatch")
    for path in (directory / PRIOR, directory / (".stop-confirmed-" + PRIOR)):
        _require(not path.exists() and not path.is_symlink(),
                 "readonly_stop_install_or_success_receipt_exists")
    return marker, receipt


def proven_readonly_refusal(directory, prior, *, uid):
    """Historical proof of no first mutation, not an install entitlement."""
    if prior != PRIOR:
        return False
    try:
        _, receipt = _journal_preflight(directory, uid)
        return (_trusted_file(receipt, uid) == RECEIPT
                and not receipt.stat().st_mode & 0o077)
    except (OSError, ValueError):
        return False


def _failed_unit_proof(*, run=subprocess.run):
    result = run(["systemctl", "show", "--no-pager",
                  "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,Description,InvocationID",
                  UNIT], capture_output=True, text=True, timeout=12, check=False)
    _require(result.returncode == 0, "readonly_stop_unit_unavailable")
    fields = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            _require(key not in fields, "duplicate_unit_property")
            fields[key] = value
    expected = {"LoadState": "loaded", "ActiveState": "failed", "SubState": "failed",
                "Result": "exit-code", "ExecMainStatus": "2", "Description": DESCRIPTION}
    _require(all(fields.get(key) == value for key, value in expected.items()),
             "readonly_stop_unit_identity_or_outcome_mismatch")
    invocation = fields.get("InvocationID", "")
    _require(re.fullmatch(r"[0-9a-f]{32}", invocation) is not None
             and invocation != "0" * 32, "readonly_stop_invocation_unproven")
    result = run(["journalctl", "--no-pager", "--quiet", "--output=json",
                  "--unit", UNIT, "_SYSTEMD_INVOCATION_ID=" + invocation],
                 capture_output=True, text=True, timeout=12, check=False)
    _require(result.returncode == 0, "readonly_stop_log_unavailable")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip().replace("-", "")
    records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    _require(all(isinstance(row, dict) for row in records), "readonly_stop_log_invalid")
    refusals = [row for row in records
                if isinstance(row.get("MESSAGE"), str) and row["MESSAGE"].startswith("BLOCKED:")]
    _require(len(refusals) == 1, "readonly_stop_refusal_not_unique")
    row = refusals[0]
    observed_ms = int(row["__REALTIME_TIMESTAMP"]) // 1000
    _require(row["MESSAGE"] == REFUSAL and row.get("_UID") == "0"
             and row.get("_SYSTEMD_UNIT") == UNIT
             and row.get("_SYSTEMD_INVOCATION_ID") == invocation
             and row.get("_BOOT_ID") == boot
             and MARKER_MS <= observed_ms <= MARKER_MS + 120000,
             "readonly_stop_log_identity_or_time_mismatch")


def seal_readonly_refusal(*, root, env_file, directory, uid=0):
    """Called only from the verified successor monolith under owner-action lock."""
    from tools.paper_maintenance import _legacy_paused_backend_predates_stop
    from tools.runtime_intent import expected_database_identity
    from tools.stop_robot_runtime import _environment, _http_get, PROBE_TIMEOUT_S, Unreachable
    from tools.vps_release_identity import verify_release

    _require(os.geteuid() == uid, "readonly_stop_requires_trusted_owner")
    marker, receipt = _journal_preflight(directory, uid)
    descriptor = os.open(directory / ".release.lock", os.O_RDWR | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "rb") as lock:
        meta = os.fstat(lock.fileno())
        _require(stat.S_ISREG(meta.st_mode) and meta.st_uid == uid
                 and not meta.st_mode & 0o077, "readonly_stop_lock_untrusted")
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        marker, receipt = _journal_preflight(directory, uid)
        _require(verify_release(root) == OLD, "readonly_stop_installed_sha_changed")
        if receipt.exists() or receipt.is_symlink():
            _require(proven_readonly_refusal(directory, PRIOR, uid=uid),
                     "readonly_stop_retirement_receipt_invalid")
            return
        _failed_unit_proof()
        _require(_legacy_paused_backend_predates_stop(marker),
                 "readonly_stop_backend_continuity_unproven")
        env = _environment(env_file)
        identity = expected_database_identity(root, env)
        url = "http://127.0.0.1:8765"
        _require((env.get("BYBITSCANNER_PAPER_BACKEND_URL") or url).rstrip("/") == url,
                 "readonly_stop_backend_route_changed")

        def read(path):
            try:
                return _http_get(url + path, PROBE_TIMEOUT_S)
            except Unreachable as exc:
                raise ValueError("readonly_stop_runtime_observation_unavailable") from exc

        def health():
            code, body = read("/api/health")
            _require(code == 200 and isinstance(body, dict)
                     and body.get("ok") is True and body.get("component") == "paper_backend"
                     and body.get("mode") == "paper" and body.get("paper_live_safe") is True
                     and body.get("build_sha") == OLD and body.get("database_identity") == identity
                     and isinstance(body.get("process_instance_id"), str)
                     and bool(body["process_instance_id"]), "readonly_stop_health_unproven")
            return body["process_instance_id"]

        before = health()
        code, body = read("/api/robot/autopilot")
        # In the pinned installed implementation, the only preceding mutation
        # is an OFF POST. A successful change increments the durable version
        # and advances updated_at_ms; PAPER_AUTO cannot be restored silently.
        # Exact unchanged pre-intent timestamp plus the failed unit and same
        # owner continuity distinguishes this refusal from an unknown POST.
        _require(code == 200 and isinstance(body, dict) and body.get("ok") is True
                 and body.get("trading_account_id") == {"value": "paper"}
                 and body.get("mode") == "PAPER_AUTO"
                 and type(body.get("version")) is int and body["version"] == AUTOPILOT_VERSION
                 and type(body.get("updated_at_ms")) is int
                 and body["updated_at_ms"] == AUTOPILOT_UPDATED_MS < MARKER_MS,
                 "readonly_stop_autopilot_mutation_not_excluded")
        _require(health() == before and _legacy_paused_backend_predates_stop(marker)
                 and verify_release(root) == OLD, "readonly_stop_owner_changed")
        _journal_preflight(directory, uid)
        fd = os.open(receipt, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(RECEIPT)
            stream.flush()
            os.fsync(stream.fileno())
        _sync_directory(directory)
