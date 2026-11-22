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
import sys
from pathlib import Path

REPO = "/opt/BybitScanner"
PYTHON = REPO + "/venv/bin/python"
SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUEST = re.compile(r"[0-9a-f]{32}\Z")
ORIGIN = re.compile(r"[A-Za-z0-9_.-]{1,64}\Z")
ACTIONS = ("update", "start", "stop", "update-and-start", "provision-owner-pc", "telegram-recover", "update-take-closed", "github-status-enable", "github-diagnostic-enable")
UNIT_PREFIX = "bybitscanner-owner-"


def unit_name(request: str) -> str:
    if REQUEST.fullmatch(request) is None:
        raise ValueError("invalid_request_id")
    return UNIT_PREFIX + request + ".service"


def _read_owner_fields(request: str, *, run=subprocess.run) -> dict:
    result = run(
        ["systemctl", "show", "--no-pager",
         "--property=LoadState,ActiveState,SubState,Result,ExecMainStatus,Description",
         unit_name(request)],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if result.returncode != 0:
        return {}
    fields = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in fields:
            return {}
        fields[key] = value
    return fields if fields.get("LoadState") == "loaded" else {}


def _owner_state(fields: dict) -> str:
    if not fields:
        return "UNPROVEN"
    if (fields.get("ActiveState") == "active"
            and fields.get("SubState") == "exited"
            and fields.get("Result") == "success"
            and fields.get("ExecMainStatus") == "0"):
        return "FINISHED_OK"
    elif fields.get("ActiveState") == "failed" or fields.get("Result") not in ("success", ""):
        return "FAILED"
    elif fields.get("ActiveState") == "activating":
        return "RUNNING"
    elif fields.get("ActiveState") == "active" and fields.get("SubState") == "running":
        return "RUNNING"
    else:
        # An inactive/dead or otherwise unexpected unit is not an executing
        # request. Never label an unknown lifecycle state RUNNING.
        return "UNPROVEN"


def read_diagnostic_outcome(request: str, action: str, target: str, *, run=subprocess.run) -> dict:
    """Strict, public-safe read of one existing owner unit. Never submit or retry."""
    from contextlib import redirect_stdout
    from io import StringIO
    from tools.github_diagnostic_protocol import (
        OWNER_ACTIONS, OWNER_RESULTS, EDITOR_ACTIONS, START_ACTIONS,
    )

    unit_name(request)
    if action not in OWNER_ACTIONS or not isinstance(target, str) or SHA.fullmatch(target) is None:
        raise ValueError("invalid owner observation identity")
    unknown = dict(owner_request_id=request, owner_action=action, target_sha=target,
                   state="UNPROVEN", result="UNKNOWN", exit_code=None, postcheck="NOT_RUN")
    try:
        fields = _read_owner_fields(request, run=run)
        expected = "BybitScanner " + action + " " + target + " origin="
        description = fields.get("Description", "")
        # Legacy truncated SHA is insufficient for a public authenticated outcome.
        if not description.startswith(expected) or not ORIGIN.fullmatch(description[len(expected):]):
            return unknown
        if not {"ActiveState", "SubState", "Result", "ExecMainStatus"} <= set(fields):
            return unknown
        state = _owner_state(fields)
        if state == "UNPROVEN":
            return unknown
        result = fields["Result"] if fields["Result"] in OWNER_RESULTS else "UNKNOWN"
        code = fields["ExecMainStatus"]
        code = int(code) if re.fullmatch(r"[0-9]{1,3}", code) and int(code) <= 255 else None
        if state == "FINISHED_OK" and (result != "success" or code != 0):
            return unknown
        if state == "RUNNING":
            code = None
        postcheck = "NOT_RUN"
        if state == "FINISHED_OK":
            if action in EDITOR_ACTIONS:
                # Existing canonical verification remains the only source of the
                # EDITOR_ONLY verdict. Never publish its raw output or exception.
                postcheck = "BLOCKED"
                try:
                    with redirect_stdout(StringIO()) as proof:
                        rc = verify_update(target)
                    if rc == 0 and "POSTCHECK=VERIFIED_EDITOR_ONLY" in proof.getvalue().splitlines():
                        postcheck = "VERIFIED_EDITOR_ONLY"
                except Exception:
                    pass
            elif action in START_ACTIONS:
                postcheck = "BLOCKED"
                try:
                    with redirect_stdout(StringIO()) as proof:
                        rc = verify_start(target)
                    if (rc == 0 and
                            "POSTCHECK=VERIFIED_PAPER_READY" in proof.getvalue().splitlines()):
                        postcheck = "VERIFIED_PAPER_READY"
                except Exception:
                    pass
            else:
                postcheck = "NOT_APPLICABLE"
        return dict(unknown, state=state, result=result, exit_code=code, postcheck=postcheck)
    except Exception:
        return unknown


def status(request: str, *, run=subprocess.run, verify_sha: str = "",
           verify_start_sha: str = "") -> int:
    unit = unit_name(request)
    fields = _read_owner_fields(request, run=run)
    if not fields:
        print("STATUS=UNPROVEN REQUEST_ID=" + request)
        return 2
    state = _owner_state(fields)
    print("REQUEST_ID=" + request)
    print("UNIT=" + unit)
    print("STATUS=" + state)
    print("RESULT=" + fields.get("Result", "unknown"))
    print("EXIT_CODE=" + fields.get("ExecMainStatus", "unknown"))
    print("DESCRIPTION=" + fields.get("Description", "")[:180])
    if state == "FINISHED_OK" and verify_sha:
        if SHA.fullmatch(verify_sha) is None:
            print("POSTCHECK=BLOCKED_INVALID_SHA")
            return 2
        # A completed UUID may refer to STOP, START or another release.
        # Bind its immutable systemd description to this approved UPDATE.
        description = fields.get("Description", "")
        if not any(description.startswith(
            "BybitScanner " + verb + " " + pinned + " origin="
        ) for verb in ("update", "update-take-closed")
          for pinned in (verify_sha, verify_sha[:12])):
            print("POSTCHECK=BLOCKED_REQUEST_TARGET_MISMATCH")
            return 2
        return verify_update(verify_sha)
    if state == "FINISHED_OK" and verify_start_sha:
        match = re.fullmatch(
            r"BybitScanner (start|update-and-start) ([0-9a-f]{40}) origin=([A-Za-z0-9_.-]{1,64})",
            fields.get("Description", ""),
        )
        if not match or verify_start_sha not in ("installed", match.group(2)):
            print("POSTCHECK=BLOCKED_REQUEST_TARGET_MISMATCH")
            return 2
        return verify_start(match.group(2))
    return 0 if state == "FINISHED_OK" else 3 if state == "RUNNING" else 2


def _verified_take_closed_stage(sha: str) -> Path:
    """Only an exact root-owned stable target worktree may run new recovery code.

    The installed old release intentionally cannot execute an unknown flag.
    This keeps the operation on the same one-shot owner UUID/monolith path;
    running an arbitrary local checkout or mutable Python module is forbidden.
    """
    from tools.paper_maintenance import _verified_staged_module_bootstrap

    stage = Path("/var/lib") / ("bybitscanner-stage-git-" + sha)
    if Path(__file__).resolve().parents[1] != stage:
        raise ValueError("take_closed_action_requires_verified_target_stage")
    if not _verified_staged_module_bootstrap(
        sha, stage, ((__name__, sys.modules[__name__]),),
    ):
        raise ValueError("take_closed_target_stage_or_module_unproven")
    return stage


def submit(action: str, sha: str, request: str, origin: str,
           *, run=subprocess.run, uid: int | None = None,
           expected_installed_sha: str | None = None) -> int:
    if action not in ACTIONS:
        raise ValueError("invalid_action")
    if sha == "installed" and action in ("start", "stop", "github-status-enable", "github-diagnostic-enable"):
        from pathlib import Path
        from tools.vps_release_identity import verify_release
        sha = verify_release(Path(REPO))
    if not isinstance(sha, str) or SHA.fullmatch(sha) is None:
        raise ValueError("invalid_exact_sha")
    if expected_installed_sha is not None and (
            action not in ("update", "update-and-start")
            or not isinstance(expected_installed_sha, str)
            or SHA.fullmatch(expected_installed_sha) is None
            or expected_installed_sha == sha):
        raise ValueError("invalid_approved_predecessor")
    if ORIGIN.fullmatch(origin) is None:
        raise ValueError("invalid_origin")
    unit = unit_name(request)
    if (os.geteuid() if uid is None else uid) != 0:
        raise ValueError("root_required_for_owner_operation")

    # A stable request ID is an idempotency fence. Successful one-shot units
    # remain loaded (RemainAfterExit), so an SSH retry cannot replay STOP/deploy.
    # Bind an idempotency UUID to its *whole* original action, SHA and origin.
    # Never treat a completed update as the result of another action/target.
    # Legacy units with 12-digit descriptions remain queryable by status()
    # but cannot silently accept a new submission under the same UUID.
    description = "BybitScanner " + action + " " + sha + " origin=" + origin
    probe = run(
        ["systemctl", "show", "--no-pager",
         "--property=LoadState,Description", unit],
        capture_output=True, text=True, timeout=12, check=False,
    )
    if probe.returncode != 0:
        print("SUBMISSION=UNPROVEN REQUEST_ID=" + request)
        return 2
    fields = dict(line.split("=", 1) for line in probe.stdout.splitlines()
                  if "=" in line)
    if fields.get("LoadState") == "loaded":
        if fields.get("Description") != description:
            print("SUBMISSION=BLOCKED_REQUEST_IDENTITY_MISMATCH REQUEST_ID=" + request)
            return 2
        print("SUBMISSION=EXISTS REQUEST_ID=" + request)
        return status(request, run=run)
    if fields.get("LoadState") != "not-found":
        print("SUBMISSION=UNPROVEN REQUEST_ID=" + request)
        return 2

    # Staging is necessary only for a *new* update, never to read an
    # already-detached operation after its verified stage has been retired.
    stage = _verified_take_closed_stage(sha) if action == "update-take-closed" else None

    cmd = [
        "systemd-run", "--no-block", "--remain-after-exit",
        "--property=Type=oneshot",
        "--working-directory=" + (str(stage) if stage is not None else REPO),
        "--unit=" + unit,
        "--description=" + description,
        PYTHON, "-m", "tools.paper_maintenance", sha, "--action", action,
        *(["--expected-installed-sha", expected_installed_sha]
          if expected_installed_sha is not None else []),
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



def verify_update(target: str) -> int:
    """Read-only proof for the exact installed EDITOR_ONLY update.

    Not an admission grant or a trading-readiness verdict. Unknown data
    fails closed; no service, DB, or order mutation is performed here.
    """
    if SHA.fullmatch(target) is None:
        print("POSTCHECK=BLOCKED_INVALID_SHA")
        return 2
    try:
        from pathlib import Path
        from tools.vps_release_identity import verify_release
        from tools.runtime_intent import http_get

        installed = verify_release(Path(REPO))
        if installed != target:
            print("POSTCHECK=BLOCKED_SHA_MISMATCH")
            return 2

        def fetch(url: str) -> dict:
            response = http_get(url, 3)
            if response.status != 200:
                raise ValueError("http_status_unproven")
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("http_payload_invalid")
            return payload

        # Reuse the existing canonical read-only durable PAPER guards:
        # healthy HTTP alone cannot prove FLAT positions or retired owners.
        from tools.paper_maintenance import _durable_editor_freeze, _paper_start_quiescent
        # Match the canonical maintenance action's systemd EnvironmentFile.
        # An SSH owner shell does not inherit the Backend's PAPER DB path.
        env_file = Path("/etc/bybitscanner/paper.env")
        expected_identity = _durable_editor_freeze(Path(REPO), env_file)
        if not _paper_start_quiescent(Path(REPO), env_file):
            print("POSTCHECK=BLOCKED_DURABLE_OWNERS")
            return 2

        backend = fetch("http://127.0.0.1:8765/api/health")
        scanner = fetch("http://127.0.0.1:8765/api/scanner/status")
        autopilot = fetch("http://127.0.0.1:8765/api/robot/autopilot")
        protection = fetch("http://127.0.0.1:8765/api/robot/protection-health")
        telegram = fetch("http://127.0.0.1:8766/health")
        identity = backend.get("database_identity")
        proven = (
            backend.get("ok") is True
            and backend.get("component") == "paper_backend"
            and backend.get("build_sha") == target
            and backend.get("mode") == "paper"
            and backend.get("paper_live_safe") is True
            and backend.get("robot_admission_ready") is False
            and isinstance(identity, str) and identity == expected_identity
            and telegram.get("component") == "telegram_monitoring"
            and telegram.get("status") == "ready"
            and telegram.get("database_identity") == identity
            and scanner.get("ok") is True
            and scanner.get("mode") == "SCANNER_STOPPED"
            and scanner.get("worker_quiescent") is True
            and autopilot.get("ok") is True
            and autopilot.get("mode") == "OFF"
            and protection.get("ok") is True
            and protection.get("healthy") is True
            and protection.get("covered_symbols") == []
            and protection.get("armed_symbols") == []
            and protection.get("coverage_roles") == {}
            and protection.get("unhealthy_symbols") == {}
        )
        print("INSTALLED_SHA=" + installed)
        print("BACKEND_TELEGRAM_DB_MATCH=" + str(
            isinstance(identity, str) and identity == expected_identity
            and telegram.get("database_identity") == identity))
        print("SCANNER_STOPPED=" + str(scanner.get("mode") == "SCANNER_STOPPED"))
        print("AUTOPILOT_OFF=" + str(autopilot.get("mode") == "OFF"))
        print("PROTECTION_QUIESCENT=" + str(
            protection.get("healthy") is True
            and protection.get("coverage_roles") == {}
            and protection.get("covered_symbols") == []
            and protection.get("armed_symbols") == []))
        print("POSTCHECK=" + ("VERIFIED_EDITOR_ONLY" if proven else "BLOCKED_UNPROVEN"))
        return 0 if proven else 2
    except Exception as exc:
        print("POSTCHECK=BLOCKED_UNPROVEN:" + type(exc).__name__)
        return 2


def verify_start(target: str) -> int:
    """Current read-only readiness, separate from historical START completion.

    Use the same canonical full-PAPER gates as maintenance. A prior successful
    unit is not proof that the release and trading contour are still ready.
    Never invoke the start path, reconciliation or service mutations.
    """
    if SHA.fullmatch(target) is None:
        print("POSTCHECK=BLOCKED_INVALID_SHA")
        return 2
    try:
        from tools.vps_release_identity import verify_release
        from tools.paper_maintenance import _paper_full_readiness

        root = Path(REPO)
        if verify_release(root) != target:
            print("POSTCHECK=BLOCKED_SHA_MISMATCH")
            return 2
        proof = _paper_full_readiness(
            root=root, env_file=Path("/etc/bybitscanner/paper.env"),
            target=target, require_gitless_telegram=True,
        )
        print("INSTALLED_SHA=" + target)
        if proof.startswith("READY:"):
            print("POSTCHECK=VERIFIED_PAPER_READY")
            return 0
        # Do not expose exception text or raw journal data.
        print("POSTCHECK=BLOCKED_PAPER_READINESS")
        return 2
    except Exception as exc:
        print("POSTCHECK=BLOCKED_UNPROVEN:" + type(exc).__name__)
        return 2


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
    proof = q.add_mutually_exclusive_group()
    proof.add_argument("--verify-update", dest="verify_sha", default="")
    proof.add_argument("--verify-start", dest="verify_start_sha", default="")
    sub.add_parser("list")
    v = sub.add_parser("verify-update")
    v.add_argument("sha")
    args = parser.parse_args(argv)
    try:
        if args.command == "submit":
            return submit(args.action, args.sha, args.request_id or uuid.uuid4().hex,
                          args.origin)
        if args.command == "status":
            return status(args.request_id, verify_sha=args.verify_sha,
                          verify_start_sha=args.verify_start_sha)
        if args.command == "verify-update":
            return verify_update(args.sha)
        return list_requests()
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print("OWNER_CONTROL_BLOCKED=" + type(exc).__name__ + ":" + str(exc)[:120],
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
