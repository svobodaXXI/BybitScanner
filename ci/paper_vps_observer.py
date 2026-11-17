"""Read-only PAPER observer: public-safe snapshot and change-only GitHub journal.

The existing owner-restricted VPS forced command remains the *only* host entry.
Never import this module on VPS, execute arbitrary SSH, or log raw diagnostics.
GitHub repository and Actions logs are public: publish allowlisted enums only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib import request

REPO = "svobodaXXI/BybitScanner"
ISSUE = 1136
MARKER = "<!-- BYBITSCANNER_PAPER_OBSERVER_V1:"
RAW_MARKER = "DIAGNOSE_READ_ONLY: "
MAX_RAW_BYTES = 65536
API = "https://api.github.com"
SHA = re.compile(r"[0-9a-f]{40}\Z")
ROBOT_STATES = frozenset({
    "READY", "PAUSED", "RECONCILING", "RECONCILIATION_REQUIRED", "ROBOT_STOPPED",
})
REASON_CLASSES = frozenset({
    "NONE", "PROTECTION_COVERAGE_LOST", "FLAT_ROBOT_TRADE_LEDGER_UNRESOLVED",
    "PENDING_ENTRY_SYNCHRONIZATION", "ROBOT_CLOSE_UNCONFIRMED",
    "PAPER_CLOSE_UNCONFIRMED", "OPERATOR_MAINTENANCE",
    "RESTART_RECONCILIATION", "OTHER_REQUIRES_PRIVATE_REVIEW",
})


def _enum(value: object, allowed: frozenset[str]) -> str:
    return value if isinstance(value, str) and value in allowed else "UNKNOWN"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unknown(at: str) -> dict:
    return {
        "schema": 1, "observed_at": at, "status": "UNKNOWN",
        "backend": "UNKNOWN", "telegram": "UNKNOWN", "scanner": "UNKNOWN",
        "autopilot": "UNKNOWN", "robot": "UNKNOWN", "protection": "UNKNOWN",
        "database": "UNKNOWN", "reason_class": "UNAVAILABLE",
        "installed_sha": None,
    }


def sanitize_diagnostic(raw: str, *, ssh_exit: int, at: str | None = None) -> dict:
    """Fail closed on missing/invalid data; never propagate source text."""
    observed = at or _timestamp()
    result = _unknown(observed)
    if ssh_exit != 0 or len(raw.encode("utf-8")) > MAX_RAW_BYTES:
        return result
    matches = [line[len(RAW_MARKER):] for line in raw.splitlines()
               if line.startswith(RAW_MARKER)]
    if len(matches) != 1:
        return result
    try:
        payload = json.loads(matches[0])
        if (not isinstance(payload, dict)
                or payload.get("kind") != "PAPER_STOP_READ_ONLY"
                or payload.get("version") not in (1, 2)):
            return result
        api, db, units = payload["api"], payload["db"], payload["units"]
        if not all(isinstance(x, dict) for x in (api, db, units)):
            return result
        health = api.get("health", {})
        if not isinstance(health, dict):
            return result
        if (health.get("reachable") is True and health.get("ok") is True
                and health.get("paper") is True):
            result["backend"] = "UP"
        elif health.get("reachable") is True:
            result["backend"] = "DEGRADED"
        result["telegram"] = _enum(
            units.get("bybitscanner-telegram.service"),
            frozenset({"active", "inactive", "failed"}),
        ).upper()
        scanner, autopilot = api.get("scanner", {}), api.get("autopilot", {})
        if isinstance(scanner, dict) and scanner.get("reachable") is True:
            result["scanner"] = _enum(
                scanner.get("mode"),
                frozenset({"SCANNER_RUNNING", "SCANNER_STOPPED"}),
            )
        if isinstance(autopilot, dict) and autopilot.get("reachable") is True:
            result["autopilot"] = _enum(
                autopilot.get("mode"), frozenset({"OFF", "SHADOW", "PAPER_AUTO"}),
            )
        protection = api.get("protection", {})
        if isinstance(protection, dict) and protection.get("reachable") is True:
            if protection.get("healthy") is True:
                result["protection"] = "HEALTHY"
            elif protection.get("healthy") is False:
                result["protection"] = "UNHEALTHY"
        if db.get("available") is True and db.get("quick_check") is True:
            result["database"] = "OK"
            if db.get("robot_mode") in ("ROBOT_RUNNING", "ROBOT_STOPPED"):
                result["robot"] = _enum(db.get("robot_recovery"), ROBOT_STATES)
            if payload["version"] == 2:
                reason = db.get("robot_reason")
                if isinstance(reason, dict):
                    kind = reason.get("kind")
                    if isinstance(kind, str) and kind in REASON_CLASSES:
                        result["reason_class"] = kind
        build = health.get("build_sha")
        if isinstance(build, str) and SHA.fullmatch(build):
            result["installed_sha"] = build
    except (KeyError, TypeError, ValueError, UnicodeError):
        return _unknown(observed)
    if result["backend"] != "UP" or result["database"] != "OK":
        result["status"] = "UNKNOWN"
    elif result["robot"] == "RECONCILIATION_REQUIRED":
        result["status"] = "FENCED"
    elif result["protection"] != "HEALTHY":
        result["status"] = "DEGRADED"
    elif result["robot"] == "READY":
        result["status"] = "RUNNING_REPORTED"
    elif result["robot"] in ("PAUSED", "ROBOT_STOPPED"):
        result["status"] = "NOT_TRADING_REPORTED"
    else:
        result["status"] = "UNKNOWN"
    return result


def fingerprint(snapshot: dict) -> str:
    """Exclude heartbeat timestamp. Only predefined public-safe fields."""
    fixed = {k: snapshot[k] for k in (
        "status", "backend", "telegram", "scanner", "autopilot", "robot",
        "protection", "database", "reason_class", "installed_sha",
    )}
    data = json.dumps(fixed, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:20]


def render_comment(snapshot: dict) -> str:
    """No raw reason, trade IDs, balances, symbols, counts or SSH paths."""
    stamp = snapshot["observed_at"]
    sign = fingerprint(snapshot)
    return (
        f"{MARKER}{sign} -->\n"
        f"**PAPER наблюдение:** `{snapshot['status']}` · {stamp} UTC\n\n"
        f"Robot: `{snapshot['robot']}` · Защита: `{snapshot['protection']}` · "
        f"Backend: `{snapshot['backend']}` · БД: `{snapshot['database']}`\n\n"
        f"Scanner: `{snapshot['scanner']}` · Autopilot: `{snapshot['autopilot']}` · "
        f"Telegram: `{snapshot['telegram']}`\n\n"
        f"Класс причины: `{snapshot['reason_class']}` · "
        f"Установленный SHA: `{snapshot['installed_sha'] or 'UNKNOWN'}`\n\n"
        "Это ограниченное наблюдение, **не** доказательство FLAT, "
        "полноты STOP/TAKE или разрешение на торговлю. "
        "Время выше — отметка записи журнала, не последнего опроса. "
        "Для проверки свежести смотрите последний GitHub Actions run: "
        "https://github.com/svobodaXXI/BybitScanner/actions/workflows/"
        "paper-vps-observer.yml . "
        "Если последний успешный опрос старше 30 минут, статус STALE."
    )


def _api(token: str, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        API + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "bybitscanner-paper-observer",
            **({"Content-Type": "application/json"} if payload is not None else {}),
        },
    )
    with request.urlopen(req, timeout=12) as res:
        body = res.read(200001)
        if len(body) > 200000:
            raise ValueError("github_response_too_large")
        return json.loads(body), res.headers.get("Link", "")


def _last_bot_record(token: str) -> tuple[str | None, datetime | None]:
    endpoint = f"/repos/{REPO}/issues/{ISSUE}/comments?per_page=100&page=1"
    first, links = _api(token, "GET", endpoint)
    if not isinstance(first, list):
        raise ValueError("unexpected_issue_comments")
    last = re.search(r"[?&]page=(\d+)>;\s*rel=\"last\"", links)
    comments = first
    if last and int(last.group(1)) > 1:
        comments, _ = _api(
            token, "GET",
            f"/repos/{REPO}/issues/{ISSUE}/comments?per_page=100&page={last.group(1)}",
        )
    for item in reversed(comments):
        if not isinstance(item, dict):
            continue
        user = item.get("user") or {}
        body = item.get("body")
        if (user.get("login") != "github-actions[bot]" or
                not isinstance(body, str) or not body.startswith(MARKER)):
            continue
        match = re.match(re.escape(MARKER) + r"([0-9a-f]{20}) -->", body)
        if not match:
            continue
        try:
            created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
        except (KeyError, TypeError, ValueError):
            continue
        return match.group(1), created
    return None, None


def publish(snapshot: dict, token: str, now: datetime | None = None) -> str:
    if not token:
        raise ValueError("missing_github_token")
    if snapshot.get("schema") != 1 or set(snapshot) != set(_unknown("sample")):
        raise ValueError("unexpected_snapshot_fields")
    # Any corrupt or unexpected value is rejected rather than published.
    safe = sanitize_diagnostic("", ssh_exit=1, at=snapshot["observed_at"])
    for key in safe:
        if key not in ("schema", "installed_sha", "observed_at") and not isinstance(snapshot[key], str):
            raise ValueError("unexpected_snapshot_value")
    if snapshot["status"] not in {
        "UNKNOWN", "FENCED", "DEGRADED", "RUNNING_REPORTED", "NOT_TRADING_REPORTED",
    }:
        raise ValueError("unexpected_public_status")
    if snapshot["installed_sha"] is not None and (
        not isinstance(snapshot["installed_sha"], str) or
        not SHA.fullmatch(snapshot["installed_sha"])
    ):
        raise ValueError("unexpected_public_sha")
    # A strict allowlist of fields and enum choices also rejects injected text.
    for key, allowed in (
        ("backend", {"UP", "DEGRADED", "UNKNOWN"}),
        ("telegram", {"ACTIVE", "INACTIVE", "FAILED", "UNKNOWN"}),
        ("scanner", {"SCANNER_RUNNING", "SCANNER_STOPPED", "UNKNOWN"}),
        ("autopilot", {"PAPER_AUTO", "SHADOW", "OFF", "UNKNOWN"}),
        ("robot", ROBOT_STATES | {"UNKNOWN"}),
        ("protection", {"HEALTHY", "UNHEALTHY", "UNKNOWN"}),
        ("database", {"OK", "UNKNOWN"}),
        ("reason_class", REASON_CLASSES | {"UNAVAILABLE"}),
    ):
        if snapshot[key] not in allowed:
            raise ValueError("unexpected_public_enum")
    datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
    previous_hash, previous_at = _last_bot_record(token)
    current_hash = fingerprint(snapshot)
    clock = now or datetime.now(timezone.utc)
    if previous_hash == current_hash and previous_at is not None and (
        0 <= (clock - previous_at).total_seconds() < 24 * 3600
    ):
        return "UNCHANGED"
    _api(token, "POST", f"/repos/{REPO}/issues/{ISSUE}/comments",
         {"body": render_comment(snapshot)})
    return "RECORDED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("sanitize")
    collect.add_argument("--input", required=True)
    collect.add_argument("--output", required=True)
    collect.add_argument("--ssh-exit", required=True, type=int)
    publish_cmd = sub.add_parser("publish")
    publish_cmd.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "sanitize":
            path = Path(args.input)
            raw = path.read_text(encoding="utf-8") if path.is_file() else ""
            snapshot = sanitize_diagnostic(raw, ssh_exit=args.ssh_exit)
            Path(args.output).write_text(
                json.dumps(snapshot, sort_keys=True) + "\n", encoding="utf-8",
            )
            print("OBSERVER_SNAPSHOT: " + snapshot["status"])
        else:
            snapshot = json.loads(Path(args.input).read_text(encoding="utf-8"))
            outcome = publish(snapshot, os.environ.get("GITHUB_TOKEN", ""))
            print("OBSERVER_JOURNAL: " + outcome)
        return 0
    except Exception as exc:
        # Never print caller-provided values, tokens or raw remote data.
        print("OBSERVER_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
