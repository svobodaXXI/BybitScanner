"""One remote owner command for VPS console, Windows CLI and VPS Manager.

The actual release/PAPER work belongs only to tools.paper_maintenance.  This
module submits that existing one-action command to a transient systemd service
so the action is not tied to the lifetime of the SSH/Termius connection.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import uuid

REPO = "/opt/BybitScanner"
PYTHON = REPO + "/venv/bin/python"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUEST = re.compile(r"[0-9a-f]{32}\Z")
ORIGIN = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
ACTIONS = ("update", "start", "stop", "update-and-start")
UNIT_PREFIX = "bybitscanner-owner-"


def unit_name(request: str) -> str:
    if REQUEST.fullmatch(request) is None:
        raise ValueError("invalid_request_id")
    return UNIT_PREFIX + request + ".service"


def status(request: str, *, run=subprocess.run) -> int:
    unit = unit_name(request)
    result = run(
        ["systemctl", "show", "--no-pager",
         "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,Description",
         unit],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if result.returncode != 0:
        print("STATUS=UNPROVEN REQUEST_ID=" + request)
        return 2
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if fields.get("LoadState") != "loaded":
        print("STATUS=UNPROVEN REQUEST_ID=" + request)
        return 2
    if (fields.get("ActiveState") == "active"
            and fields.get("SubState") == "exited"
            and fields.get("Result") == "success"
            and fields.get("ExecMainStatus") == "0"):
        state = "FINISHED_OK"
    elif fields.get("ActiveState") == "failed" or fields.get("Result") not in ("success", ""):
        state = "FAILED"
    elif fields.get("ActiveState") == "activating":
        state = "RUNNING"
    elif fields.get("ActiveState") == "active" and fields.get("SubState") == "running":
        state = "RUNNING"
    else:
        # An inactive/dead or otherwise unexpected unit is not an executing
        # request. Never label an unknown lifecycle state RUNNING.
        state = "UNPROVEN"
    print("REQUEST_ID=" + request)
    print("UNIT=" + unit)
    print("STATUS=" + state)
    print("RESULT=" + fields.get("Result", "unknown"))
    print("EXIT_CODE=" + fields.get("ExecMainStatus", "unknown"))
    print("DESCRIPTION=" + fields.get("Description", "")[:180])
    return 0 if state == "FINISHED_OK" else 3 if state == "RUNNING" else 2


def submit(action: str, sha: str, request: str, origin: str,
           *, run=subprocess.run, uid: int | None = None) -> int:
    if action not in ACTIONS:
        raise ValueError("invalid_action")
    if sha == "installed" and action in ("start", "stop"):
        from pathlib import Path
        from tools.vps_release_identity import verify_release
        sha = verify_release(Path(REPO))
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise ValueError("invalid_exact_sha")
    if ORIGIN.fullmatch(origin) is None:
        raise ValueError("invalid_origin")
    unit = unit_name(request)
    if (os.geteuid() if uid is None else uid) != 0:
        raise ValueError("root_required_for_owner_operation")

    # A stable request ID is an idempotency fence. Successful one-shot units
    # remain loaded (RemainAfterExit), so an SSH retry cannot replay STOP/deploy.
    probe = run(["systemctl", "show", "--no-pager", "--property=LoadState", unit],
                capture_output=True, text=True, timeout=12, check=False)
    if probe.returncode != 0:
        print("SUBMISSION=UNPROVEN REQUEST_ID=" + request)
        return 2
    if "LoadState=loaded" in probe.stdout.splitlines():
        print("SUBMISSION=EXISTS REQUEST_ID=" + request)
        return status(request, run=run)

    cmd = [
        "systemd-run", "--no-block", "--remain-after-exit",
        "--property=Type=oneshot", "--working-directory=" + REPO,
        "--unit=" + unit,
        "--description=BybitScanner " + action + " " + sha[:12] + " origin=" + origin,
        PYTHON, "-m", "tools.paper_maintenance", sha, "--action", action,
    ]
    result = run(cmd, capture_output=True, text=True, timeout=20, check=False)
    print("REQUEST_ID=" + request)
    print("UNIT=" + unit)
    if result.returncode != 0:
        # Do not rerun an operation after an uncertain systemd-run response.
        print("SUBMISSION=UNPROVEN; use status, never retry the action")
        return 2
    print("SUBMISSION=ACCEPTED; action continues on VPS independently of SSH")
    return 0


def list_requests(*, run=subprocess.run) -> int:
    result = run(
        ["systemctl", "list-units", "--all", "--plain", "--no-legend",
         "--no-pager", UNIT_PREFIX + "*.service"],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if result.returncode:
        print("REQUEST_LIST=UNPROVEN")
        return 2
    for line in result.stdout.splitlines()[:30]:
        if line.strip().startswith(UNIT_PREFIX):
            print(line[:240])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Owner monolith request/status via systemd")
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("submit")
    s.add_argument("action", choices=ACTIONS)
    s.add_argument("sha")
    s.add_argument("--request-id", default=None)
    s.add_argument("--origin", default="vps-console")
    q = sub.add_parser("status")
    q.add_argument("request_id")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    try:
        if args.command == "submit":
            return submit(args.action, args.sha, args.request_id or uuid.uuid4().hex,
                          args.origin)
        if args.command == "status":
            return status(args.request_id)
        return list_requests()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("OWNER_CONTROL_BLOCKED=" + type(exc).__name__ + ":" + str(exc)[:120],
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
