"""Read-only, PUBLIC and deliberately coarse VPS/PAPER status -> GitHub Issue #1212.

One short-lived run from a separately authorized systemd timer; never imported by
the trading owner. GitHub is observation only, never runtime/trading authority.
The reporter is OFF until a protected token file is provisioned on the VPS.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen

ISSUE_URL = "https://api.github.com/repos/svobodaXXI/BybitScanner/issues/1212/comments"
BACKEND = "http://127.0.0.1:8765"
TELEGRAM = "http://127.0.0.1:8766"
TOKEN_FILE = Path("/etc/bybitscanner/github-status.token")
STATE_DIR = Path("/var/lib/bybitscanner-github-status")
MAX_PENDING = 64
MAX_SEND = 3
SHA = re.compile(r"[0-9a-f]{40}")
EVENT_ID = re.compile(r"[0-9a-f]{64}")
UTC_TIME = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z")

_MODES = {
    "robot": {"ROBOT_RUNNING", "ROBOT_STOPPED"},
    "recovery": {"READY", "PAUSED", "RECONCILING", "RECONCILIATION_REQUIRED", "ROBOT_STOPPED"},
    "scanner": {"SCANNER_RUNNING", "SCANNER_PAUSED", "SCANNER_STOPPED"},
    "autopilot": {"OFF", "SHADOW", "PAPER_AUTO"},
    "coverage": {"REPORTED_COVERED", "REPORTED_MISSING", "UNKNOWN", "NOT_APPLICABLE"},
    "backend": {"REACHABLE", "UNAVAILABLE", "SAFETY_FLAG_FAILED"},
    "telegram": {"READY", "UNAVAILABLE"},
    "assessment": {"ATTENTION", "OBSERVED", "UNKNOWN"},
}
_FIELDS = ("backend", "telegram", "backend_build_sha", "robot", "recovery",
           "scanner", "autopilot", "position_count", "coverage", "assessment")


def _get(url: str) -> dict:
    with urlopen(Request(url, headers={"Accept": "application/json"}), timeout=3) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError("unexpected local status")
    return payload


def _enum(value, choices: set[str]) -> str:
    return value if type(value) is str and value in choices else "UNKNOWN"


def observe(fetch=_get) -> dict:
    """No raw API fields, names, symbols, amounts, IDs or exceptions escape."""
    unavailable = {"backend": "UNAVAILABLE", "telegram": "UNAVAILABLE",
                   "backend_build_sha": "UNKNOWN", "robot": "UNKNOWN",
                   "recovery": "UNKNOWN", "scanner": "UNKNOWN", "autopilot": "UNKNOWN",
                   "position_count": None, "coverage": "UNKNOWN", "assessment": "UNKNOWN"}
    try:
        health = fetch(BACKEND + "/api/health")
        if (health.get("ok") is not True or health.get("component") != "paper_backend"
                or health.get("mode") != "paper"):
            return unavailable
        if health.get("paper_live_safe") is not True:
            # The API is reachable but its explicit safety claim failed.
            # Publish a coarse incident without trusting any further runtime fields.
            return {**unavailable, "backend": "SAFETY_FLAG_FAILED",
                    "assessment": "ATTENTION"}
        robot = fetch(BACKEND + "/api/robot/state")
        scanner = fetch(BACKEND + "/api/scanner/status")
        autopilot = fetch(BACKEND + "/api/robot/autopilot")
        positions = fetch(BACKEND + "/api/open-positions").get("positions")
        coverage = fetch(BACKEND + "/api/robot/protection-health")
        if not isinstance(positions, list) or len(positions) > 100_000:
            return unavailable
        if any(not isinstance(p, dict) or not isinstance(p.get("symbol"), str)
               for p in positions):
            return unavailable
        sha = health.get("build_sha")
        digest = sha if type(sha) is str and SHA.fullmatch(sha) else "UNKNOWN"
        covered = coverage.get("covered_symbols")
        if not positions:
            protection = "NOT_APPLICABLE"
        elif (coverage.get("healthy") is True and isinstance(covered, list)
              and all(type(s) is str for s in covered)
              and {p["symbol"] for p in positions}.issubset(set(covered))):
            # A coverage report is NOT independent proof that STOP/TAKE will execute.
            protection = "REPORTED_COVERED"
        elif isinstance(covered, list) and coverage.get("healthy") in (True, False):
            protection = "REPORTED_MISSING"
        else:
            protection = "UNKNOWN"
        result = {
            "backend": "REACHABLE",
            "telegram": "UNAVAILABLE",
            "backend_build_sha": digest,
            "robot": _enum(robot.get("mode"), _MODES["robot"]),
            "recovery": _enum(robot.get("recovery_status"), _MODES["recovery"]),
            "scanner": _enum(scanner.get("mode"), _MODES["scanner"]),
            "autopilot": _enum(autopilot.get("mode"), _MODES["autopilot"]),
            "position_count": len(positions),
            "coverage": protection,
        }
        try:
            tg = fetch(TELEGRAM + "/health")
            if tg.get("component") == "telegram_monitoring" and tg.get("status") == "ready":
                result["telegram"] = "READY"
        except Exception:
            pass
        uncertain = any(result[k] == "UNKNOWN" for k in
                        ("robot", "recovery", "scanner", "autopilot"))
        incident = (result["recovery"] in {"RECONCILIATION_REQUIRED", "RECONCILING"}
                    or (len(positions) > 0 and protection != "REPORTED_COVERED")
                    or result["telegram"] == "UNAVAILABLE")
        result["assessment"] = "UNKNOWN" if uncertain else "ATTENTION" if incident else "OBSERVED"
        return result
    except Exception:
        return unavailable


def _safe_snapshot(raw: dict) -> dict:
    """Revalidate even locally persisted payloads before any public POST."""
    if not isinstance(raw, dict) or set(raw) != set(_FIELDS):
        raise ValueError("unsafe public snapshot shape")
    data = {}
    for key in _FIELDS:
        value = raw[key]
        if key == "backend_build_sha":
            if value != "UNKNOWN" and (type(value) is not str or not SHA.fullmatch(value)):
                raise ValueError("unsafe sha")
        elif key == "position_count":
            if value is not None and (type(value) is not int or not 0 <= value <= 100_000):
                raise ValueError("unsafe count")
        elif value != "UNKNOWN" and value not in _MODES[key]:
            raise ValueError("unsafe status")
        data[key] = value
    return data


def _token(path: Path) -> str:
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077
            or meta.st_uid != os.geteuid() or meta.st_size > 512):
        raise ValueError("unsafe token file")
    token = path.read_text(encoding="ascii").strip()
    if len(token) < 30 or len(token) > 256 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("unsafe token format")
    return token


def _directory(path: Path) -> None:
    if path.exists() or path.is_symlink():
        meta = path.lstat()
        if (not stat.S_ISDIR(meta.st_mode) or meta.st_mode & 0o077
                or meta.st_uid != os.geteuid()):
            raise ValueError("unsafe outbox directory")
    else:
        path.mkdir(mode=0o700, parents=False)


def _load(path: Path) -> dict:
    if not path.exists() and not path.is_symlink():
        return {"queue": [], "last_hash": "", "last_at_ms": 0, "gap": False}
    meta = path.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_mode & 0o077
            or meta.st_uid != os.geteuid() or meta.st_size > 60_000):
        raise ValueError("unsafe outbox state")
    state = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(state, dict) or not isinstance(state.get("queue"), list):
        raise ValueError("invalid outbox")
    if len(state["queue"]) > MAX_PENDING:
        raise ValueError("outbox capacity exceeded")
    for entry in state["queue"]:
        if (not isinstance(entry, dict) or set(entry) != {"id", "observed_at", "snapshot"}
                or type(entry["id"]) is not str or not EVENT_ID.fullmatch(entry["id"])
                or type(entry["observed_at"]) is not str
                or not UTC_TIME.fullmatch(entry["observed_at"])):
            raise ValueError("invalid pending event")
        _safe_snapshot(entry["snapshot"])
    if (type(state.get("last_hash")) is not str
            or (state["last_hash"] and not EVENT_ID.fullmatch(state["last_hash"]))
            or type(state.get("last_at_ms")) is not int
            or type(state.get("gap")) is not bool):
        raise ValueError("invalid outbox markers")
    return state


def _save(path: Path, state: dict) -> None:
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            os.fchmod(out.fileno(), 0o600)
            json.dump(state, out, sort_keys=True, separators=(",", ":"))
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def _post(token: str, body: str) -> None:
    request = Request(
        ISSUE_URL,
        data=json.dumps({"body": body}).encode("utf-8"),
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "bybitscanner-public-status",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=8) as response:
        if response.status != 201:
            raise ValueError("GitHub publication not acknowledged")


def report_once(*, token_file: Path = TOKEN_FILE, state_dir: Path = STATE_DIR,
                fetch=_get, post=_post, now_ms: int | None = None) -> int:
    """One bounded observer pass; no operations against trading or PAPER storage."""
    try:
        token = _token(token_file)
        _directory(state_dir)
        path = state_dir / "pending.json"
        state = _load(path)
        now = int(time.time() * 1000) if now_ms is None else now_ms
        snapshot = _safe_snapshot(observe(fetch))
        fingerprint = hashlib.sha256(json.dumps(
            snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        frequency_ms = 5 * 60_000 if snapshot["assessment"] != "OBSERVED" else 30 * 60_000
        elapsed = now - state["last_at_ms"]
        if (fingerprint != state["last_hash"] or elapsed < 0 or elapsed >= frequency_ms):
            observed = datetime.fromtimestamp(now / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            event_id = hashlib.sha256((observed + "|" + fingerprint).encode()).hexdigest()
            state["queue"].append({"id": event_id, "observed_at": observed, "snapshot": snapshot})
            if len(state["queue"]) > MAX_PENDING:
                state["queue"].pop(0)
                state["gap"] = True
            state["last_hash"] = fingerprint
            state["last_at_ms"] = now
            _save(path, state)  # durability BEFORE any ambiguous remote POST

        for _ in range(min(MAX_SEND, len(state["queue"]))):
            event = state["queue"][0]
            payload = _safe_snapshot(event["snapshot"])
            body = ("BYBITSCANNER_PUBLIC_STATUS_V1\n"
                    + "event_id=" + event["id"] + "\n"
                    + "observed_at_utc=" + event["observed_at"] + "\n"
                    + "delivery_gap=" + ("true" if state["gap"] else "false") + "\n"
                    + "~~~~json\n" + json.dumps(payload, sort_keys=True) + "\n~~~~")
            # A GitHub timeout has an unknown POST outcome. Preserve the event
            # ID for reader-side deduplication; do not claim exactly-once delivery.
            post(token, body)
            state["queue"].pop(0)
            state["gap"] = False
            _save(path, state)
        return 0
    except Exception:
        # Deliberately do not print arbitrary error strings, URLs or credentials.
        return 2


def enable_observer(expected_sha: str, *, root: Path = Path("/opt/BybitScanner"),
                    unit_dir: Path = Path("/etc/systemd/system"),
                    token_file: Path = TOKEN_FILE, manifest_path=None,
                    uid: int = 0, run=subprocess.run) -> str:
    """Explicit owner opt-in; never stop/start trading or manage credentials."""
    names = ("bybitscanner-github-status.service", "bybitscanner-github-status.timer")
    try:
        if os.geteuid() != uid:
            return "BLOCKED: observer_owner_required"
        _token(token_file)
    except (OSError, ValueError):
        return "BLOCKED: observer_token_missing_or_unprotected"

    return _enable_pinned_timer(expected_sha, names=names,
                                source_paths=("tools/github_status_reporter.py",),
                                label="observer", root=root, unit_dir=unit_dir,
                                manifest_path=manifest_path, uid=uid, run=run)


def _enable_pinned_timer(expected_sha: str, *, names, source_paths, label,
                         root: Path, unit_dir: Path, manifest_path, uid, run) -> str:
    """Private fixed-profile activation shared by the two read-only timers."""
    from tools.vps_release_identity import MANIFEST, verify_release, git_blob_hash, _safe_file
    from tools.vps_gitless_release_activate import _trusted_file, _atomic_new_file, _manifest

    try:
        manifest_path = MANIFEST if manifest_path is None else manifest_path
        if verify_release(root, manifest_path) != expected_sha:
            return f"BLOCKED: {label}_release_mismatch"
        manifest = _manifest(_trusted_file(manifest_path, uid))
        if manifest["build_sha"] != expected_sha:
            return f"BLOCKED: {label}_release_mismatch"
        meta = unit_dir.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != uid or meta.st_mode & 0o022:
            return f"BLOCKED: {label}_unit_directory_unprotected"

        def command(*args):
            result = run(["systemctl", *args], capture_output=True, text=True,
                         timeout=20, check=False)
            if result.returncode:
                raise ValueError(f"{label}_systemd_unproven")
            return result.stdout

        def properties(name):
            result = run(["systemctl", "show", "--all", name,
                          "--property=LoadState,FragmentPath,DropInPaths,ActiveState,UnitFileState,NeedDaemonReload"],
                         capture_output=True, text=True, timeout=20, check=False)
            values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
            # systemctl versions can return 1 for a genuinely absent unit.
            # Do not interpret arbitrary probe failures as absence.
            if result.returncode and not (result.returncode == 1
                    and values.get("LoadState") == "not-found"
                    and values.get("FragmentPath") == ""
                    and values.get("DropInPaths") == ""):
                raise ValueError(f"{label}_systemd_unproven")
            return values

        def exact_unit(name, values):
            return (values.get("LoadState") == "loaded"
                    and values.get("FragmentPath") == str(unit_dir / name)
                    and values.get("DropInPaths") == ""
                    and values.get("NeedDaemonReload") == "no")

        # Verify all sources and existing destinations before any file mutation.
        sources = {}
        for rel in (*source_paths, *("deploy/systemd/" + n for n in names)):
            data = _trusted_file(_safe_file(root, rel), uid)
            if manifest["blobs"].get(rel) != git_blob_hash(data):
                return f"BLOCKED: {label}_source_not_pinned"
            sources[rel] = data
        pending = []
        for name in names:
            path = unit_dir / name
            data = sources["deploy/systemd/" + name]
            values = properties(name)
            if os.path.lexists(path):
                if _trusted_file(path, uid) != data:
                    return f"BLOCKED: {label}_existing_unit_conflict"
                if (values.get("FragmentPath") not in ("", str(path))
                        or values.get("DropInPaths") != ""):
                    return f"BLOCKED: {label}_effective_unit_conflict"
            else:
                if (values.get("LoadState") != "not-found"
                        or values.get("FragmentPath") != ""
                        or values.get("DropInPaths") != ""):
                    return f"BLOCKED: {label}_effective_unit_conflict"
                pending.append((path, data))

        for path, data in pending:
            _atomic_new_file(path, data)
        command("daemon-reload")
        if not all(exact_unit(name, properties(name)) for name in names):
            return f"BLOCKED: {label}_effective_unit_unproven"
        command("enable", "--now", names[1])
        values = properties(names[1])
        if (not exact_unit(names[1], values)
                or values.get("UnitFileState") != "enabled"
                or values.get("ActiveState") != "active"):
            return f"BLOCKED: {label}_timer_activation_unproven; no retry"
        return f"READY: GitHub {label} timer enabled and active; delivery unverified"
    except Exception:
        # Never print credentials, subprocess stderr or arbitrary unit contents.
        return f"BLOCKED: {label}_setup_unproven; no automatic retry"


def main() -> int:
    result = report_once()
    print("PUBLIC_GITHUB_STATUS=" + ("PUBLISHED_OR_UNCHANGED" if result == 0 else "DEFERRED_OR_DISABLED"))
    return result


if __name__ == "__main__":
    sys.exit(main())
