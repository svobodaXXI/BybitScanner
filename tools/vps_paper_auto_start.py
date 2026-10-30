"""VPS PAPER-only owner-authorized final step of the unified startup.

Run *after* canonical runtime_intent ALL returns READY. Never schedules a
start on reboot: the operator invokes the oneshot and explicitly opts in via
the protected server environment file. No LIVE path or alternate order engine.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit

BASE = "http://127.0.0.1:8765"
HEADER = "X-BybitScanner-Autopilot-Owner-Token"


class StartupBlocked(Exception):
    pass


def request(path: str, *, data: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers[HEADER] = token
    base = os.environ.get("BYBITSCANNER_PAPER_BACKEND_URL", BASE).rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise StartupBlocked("Backend URL must be local PAPER loopback")
    req = urllib.request.Request(
        base + path,
        data=None if data is None else json.dumps(data).encode("utf-8"),
        headers=headers,
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.load(response)
            if response.status != 200 or not isinstance(result, dict):
                raise StartupBlocked(f"{path}: unexpected HTTP response")
            return result
    except urllib.error.HTTPError as exc:
        # Do not echo response bodies: they may contain internal details.
        raise StartupBlocked(f"{path}: HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise StartupBlocked(f"{path}: unavailable or invalid response") from exc


def enable_from_authorized_start(env: dict[str, str] | None = None) -> None:
    env = os.environ if env is None else env
    if env.get("BYBITSCANNER_VPS_PAPER_AUTO_ON_START") != "1":
        raise StartupBlocked(
            "PAPER_AUTO not enabled: explicit BYBITSCANNER_VPS_PAPER_AUTO_ON_START=1 "
            "is required in the protected VPS environment"
        )
    token = env.get("BYBITSCANNER_AUTOPILOT_OWNER_TOKEN", "").strip()
    if len(token) < 32:
        raise StartupBlocked("PAPER_AUTO owner token is missing or invalid")

    health = request("/api/health")
    if not (
        health.get("ok") is True
        and health.get("component") == "paper_backend"
        and health.get("mode") == "paper"
        and health.get("paper_live_safe") is True
        and health.get("robot_admission_ready") is True
        and health.get("scanner_acceptance_ready") is True
        and health.get("database_identity")
    ):
        raise StartupBlocked("PAPER backend / LIVE isolation / admission not proven")
    scanner = request("/api/scanner/status")
    if scanner.get("ok") is not True or scanner.get("mode") != "SCANNER_RUNNING":
        raise StartupBlocked("Scanner is not RUNNING")
    protection = request("/api/robot/protection-health")
    if protection.get("ok") is not True or protection.get("healthy") is not True:
        raise StartupBlocked("Robot STOP/TAKE protection is not healthy")

    before = request("/api/robot/autopilot")
    if before.get("ok") is not True or before.get("trading_account_id") != {"value": "paper"}:
        raise StartupBlocked("PAPER autopilot account identity is unproven")
    if before.get("mode") != "PAPER_AUTO":
        if before.get("mode") != "OFF":
            raise StartupBlocked("Autopilot is neither OFF nor PAPER_AUTO; refusing override")
        changed = request(
            "/api/robot/autopilot",
            data={"mode": "PAPER_AUTO", "confirm_paper_auto": True},
            token=token,
        )
        if changed.get("ok") is not True or changed.get("mode") != "PAPER_AUTO":
            raise StartupBlocked("PAPER_AUTO transition was not confirmed")
    after = request("/api/robot/autopilot")
    if (
        after.get("ok") is not True
        or after.get("mode") != "PAPER_AUTO"
        or after.get("trading_account_id") != {"value": "paper"}
    ):
        raise StartupBlocked("PAPER_AUTO final state not confirmed")
    print("READY: PAPER backend + Scanner + Robot runtime intent + protection + PAPER_AUTO")


def main() -> int:
    try:
        enable_from_authorized_start()
    except StartupBlocked as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
