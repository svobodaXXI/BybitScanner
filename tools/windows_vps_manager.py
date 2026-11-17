"""BybitScanner VPS Manager — standalone Windows, read-only MVP.

Reuses the repository's diagnostic entry points; never manages trading orders.
Requires Windows OpenSSH, separately configured SSH key and verified known_hosts.
Run: py -3 tools/windows_vps_manager.py
"""
from __future__ import annotations

import argparse
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import uuid
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

PROJECT = "/opt/BybitScanner"
VENV = f"{PROJECT}/venv/bin/python"
# The repo belongs to the service account; a per-command safe.directory lets
# the read-only manager user run git without any persistent config change.
GIT = f"git -c safe.directory={PROJECT} -C {PROJECT}"
# Installed immutable releases have no .git. This is not evidence of a clean
# worktree or authorization to deploy; report that status as UNKNOWN.
GIT_PROBE = (
    f"if test -e {PROJECT}/.git; then "
    "printf 'GIT_WORKTREE=PRESENT\\n'; "
    f"{GIT} status --porcelain=v1; "
    f"{GIT} branch --show-current; "
    f"{GIT} rev-parse HEAD; "
    "else printf 'GIT_WORKTREE=ABSENT\\nGIT_STATUS=UNKNOWN (release without .git)\\n'; "
    "fi"
)
HEALTH = "curl -fsS --connect-timeout 3 --max-time 6 http://127.0.0.1:8765/api/health"
HOST_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")
# Without an explicit -i, OpenSSH only tries the default id_* names, so a
# purpose-built key such as ~/.ssh/bybitscanner_laptop is never offered.
# Known operator Windows profiles only; never silently reuse a laptop key on PC.
# This is a routing hint, not cryptographic device attestation.
KNOWN_ROUTES = {
    "pc": ("212.193.14.116", "root", "bybitscanner_vdsina_gateway_20261030"),
    "laptop": ("83.217.213.181", "root", "bybitscanner_laptop"),
}

# Fixed, audited commands: no free-form shell and no trading mutations.
ACTIONS = {
    "Состояние": (
        # Abort on an unavailable service query; the last successful status
        # must not hide an earlier systemctl failure as a successful check.
        "set -e; "
        "systemctl show bybitscanner-paper-backend.service "
        "-p ActiveState -p SubState -p MainPID; "
        "systemctl show bybitscanner-telegram.service -p ActiveState -p SubState; "
        "systemctl show bybitscanner-paper-start.service -p ActiveState -p SubState"
    ),
    # tools.vps_check is a pre-start gate (ports must be free, secret env file
    # readable), so on a running VPS it can only fail; read live health instead.
    "Диагностика PAPER": (
        "set -e; "
        "systemctl show bybitscanner-paper-backend.service "
        "-p ActiveState -p SubState -p MainPID -p NRestarts -p ActiveEnterTimestamp; "
        f"{HEALTH} | python3 -m json.tool"
    ),
    "Git / локальные изменения": (
        "set -e; "
        "printf '=== INSTALLED SOURCE ===\\n'; "
        f"{GIT_PROBE}; "
        "printf '=== BACKEND BUILD ===\\n'; "
        f"{HEALTH}"
    ),
    "Предпроверка обновления": (
        "set -e; "
        "printf '=== INSTALLED SOURCE ===\\n'; "
        f"{GIT_PROBE}; "
        "printf 'DEPLOY_PREFLIGHT=NOT_PROVEN (informational only)\\n'; "
        "printf '=== BACKEND ===\\n'; "
        "systemctl show bybitscanner-paper-backend.service "
        "-p ActiveState -p SubState -p MainPID; "
        "printf '=== PAPER HEALTH ===\\n'; "
        f"{HEALTH}"
    ),
    # Without journal read access journalctl prints "-- No entries --" and exits 0,
    # which looks like a healthy empty log; fail loudly instead.
    "Последние журналы": (
        "id -nG | grep -qwE 'systemd-journal|adm' || "
        "{ echo 'NO ACCESS: this SSH user cannot read the systemd journal "
        "(needs group systemd-journal or adm)'; exit 13; }; "
        "journalctl -u bybitscanner-paper-backend.service "
        "--no-pager -n 35 --output=short-iso"
    ),
}
# All probes are read-only. Successful command completion is evidence collection,
# not proof of PAPER admission, Telegram delivery or a full Scanner pass.
PREFLIGHT = (
    "set -e; cd /opt/BybitScanner; "
    "printf '=== VERIFIED_INSTALLED_RELEASE ===\\n'; "
    f"{VENV} -m tools.vps_release_identity verify; "
    "printf '=== SYSTEMD_UNITS ===\\n'; "
    "systemctl show --no-pager -p LoadState -p ActiveState -p SubState -p MainPID "
    "bybitscanner-paper-backend.service bybitscanner-telegram.service "
    "bybitscanner-paper-start.service bybitscanner-manual-main-read.service; "
    "printf '=== BACKEND_HEALTH ===\\n'; "
    f"{HEALTH}; "
    "printf '\\n=== SCANNER_STATUS ===\\n'; "
    "curl -fsS --connect-timeout 3 --max-time 6 http://127.0.0.1:8765/api/scanner/status; "
    "printf '\\n=== AUTOPILOT_STATUS ===\\n'; "
    "curl -fsS --connect-timeout 3 --max-time 6 http://127.0.0.1:8765/api/robot/autopilot; "
    "printf '\\n=== TELEGRAM_HEALTH ===\\n'; "
    "curl -fsS --connect-timeout 3 --max-time 6 http://127.0.0.1:8766/health; "
    "printf '\\nPREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED\\n'"
)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
EXACT_SHA = re.compile(r"[0-9a-f]{40}\Z")
REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")


def request_id_store() -> Path:
    """Local, non-secret recovery pointer; never stores SSH credentials."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / ".config"
    return base / "BybitScanner" / "VPSManager" / "last_request_id"


def recover_last_request_id(path: Path | None = None) -> str:
    target = path if path is not None else request_id_store()
    try:
        value = target.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""
    return value if REQUEST_ID.fullmatch(value) else ""


def remember_request_id(request: str, path: Path | None = None) -> None:
    """Persist before submit so an interrupted client can query status only."""
    if REQUEST_ID.fullmatch(request) is None:
        raise ValueError("invalid_request_id")
    target = path if path is not None else request_id_store()
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_suffix(".tmp")
    staged.write_text(request + "\n", encoding="ascii")
    staged.replace(target)


CONTROL_ACTIONS = {
    "Обновить EDITOR_ONLY": "update",
    "Запустить PAPER-ядро": "start",
    "Остановить PAPER-ядро": "stop",
    "Обновить и запустить PAPER": "update-and-start",
    "Сопрячь один ПК (EDITOR_ONLY)": "provision-owner-pc",
    "Включить Wedge BE (EDITOR_ONLY)": "enable-wedge-be",
}
CONTROL_MODULE = "cd /opt/BybitScanner && /opt/BybitScanner/venv/bin/python -m tools.vps_owner_control"


def gui_owner_status(stdout: str, returncode: int, request: str) -> str:
    """Only an exact UUID and matching server status can color a GUI result."""
    lines = stdout.strip().splitlines()
    states = [line for line in lines if line.startswith("STATUS=")]
    if "REQUEST_ID=" + request not in lines or len(states) != 1:
        return "unproven"
    return {
        (0, "STATUS=FINISHED_OK"): "success",
        (3, "STATUS=RUNNING"): "submitted",
        (2, "STATUS=FAILED"): "failed",
    }.get((returncode, states[0]), "unproven")



# Only the original request ID is polled. This is read-only monitoring, never
# a submission retry; bounded SSH failures preserve the original owner operation.
OWNER_POLL_LIMIT = 180  # up to 15 minutes of ordinary five-second polling
OWNER_POLL_SECONDS = 5
OWNER_POLL_UNKNOWN_LIMIT = 3


def watch_owner_request(
    status_command: list[str], request: str, *, initially_submitted: bool,
    run=None, sleep=None, attempts: int = OWNER_POLL_LIMIT,
) -> tuple[str, str]:
    if run is None:
        # Recovery belongs to the read-only status query, never to submit.
        def run(command: list[str], **kwargs):
            return run_readonly_ssh_with_laptop_agent_recovery(command, **kwargs)[0]
    sleep = sleep or time.sleep
    state = "submitted" if initially_submitted else "unproven"
    latest = ""
    unknown = 0
    for attempt in range(attempts):
        if attempt:
            sleep(OWNER_POLL_SECONDS)
        try:
            reply = run(
                status_command, capture_output=True, text=True, errors="replace",
                timeout=20, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            unknown += 1
        else:
            observed = gui_owner_status(reply.stdout, reply.returncode, request)
            if observed in ("success", "failed"):
                return observed, reply.stdout.strip()
            if observed == "submitted":
                state = "submitted"
                latest = reply.stdout.strip()
                unknown = 0
            else:
                unknown += 1
        if unknown >= OWNER_POLL_UNKNOWN_LIMIT:
            return state, latest + "\nSTATUS_UNPROVEN; operation not resubmitted"
    return state, latest + "\nSTATUS_POLL_LIMIT; use the same request ID"


def ssh_command(host: str, user: str, action: str, key: str = "") -> list[str]:
    host = host.strip()
    user = user.strip()
    key = key.strip()
    if not HOST_PATTERN.fullmatch(host) or host.startswith("-"):
        raise ValueError("Недопустимое имя или адрес VPS")
    if not USER_PATTERN.fullmatch(user) and not (host == "bybitscanner-vps" and not user):
        raise ValueError("Недопустимое имя пользователя")
    if action not in ACTIONS:
        raise ValueError("Неизвестная операция")
    identity: list[str] = []
    if key:
        path = Path(key).expanduser()
        if not path.is_file():
            raise ValueError(f"Файл ключа SSH не найден: {path}")
        # IdentitiesOnly keeps the agent from racing ahead with other keys.
        identity = ["-o", "IdentitiesOnly=yes", "-i", str(path)]
    # Explicit known-device routes must not be diverted by an unrelated config.
    direct = preferred_key(host, user) == key and bool(key)
    return [
        "ssh", *(["-F", "none"] if direct else []),
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", "-o", "NumberOfPasswordPrompts=0",
        "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
        *identity, (f"{user}@{host}" if user else host), ACTIONS[action],
    ]


def known_windows_device(profile: str | None = None) -> str:
    """Identify only the two owner-confirmed Windows user profiles; else UNKNOWN."""
    value = profile if profile is not None else os.environ.get("USERPROFILE", "")
    normalized = value.strip().strip('"').replace("/", "\\").rstrip("\\").casefold()
    return {
        "c:\\users\\svobo": "pc",
        "c:\\users\\svoboda21": "laptop",
    }.get(normalized, "")


def preferred_key(host: str, user: str) -> str:
    """Only offer a pinned identity for a known device's exact VPS target."""
    route = KNOWN_ROUTES.get(known_windows_device())
    if route and (host, user) == route[:2]:
        return str(Path.home() / ".ssh" / route[2])
    return ""


def preferred_route() -> tuple[str, str]:
    # The laptop has no confirmed PC alias: use its separate proven profile.
    if known_windows_device() == "laptop":
        return KNOWN_ROUTES["laptop"][:2]
    # Existing OpenSSH alias owns the key, verified host and network route.
    config = Path.home() / ".ssh" / "config"
    try:
        if any("bybitscanner-vps" in line.split()[1:]
               for line in config.read_text(encoding="utf-8").splitlines()
               if line.strip().lower().startswith("host ")):
            return "bybitscanner-vps", ""
    except (OSError, UnicodeError):
        pass
    # On the known PC, the direct-key target is an observed safe fallback if
    # its native alias is absent. Unknown devices retain explicit configuration.
    if known_windows_device() == "pc":
        return KNOWN_ROUTES["pc"][:2]
    remote = os.environ.get("BYBITSCANNER_VPS_SSH_TARGET", "")
    if re.fullmatch(r"[A-Za-z_][A-Za-z_0-9-]*@[A-Za-z0-9._-]+", remote):
        user, host = remote.split("@", 1)
        return host, user
    return "", "bybitscanner"


def device_origin() -> str:
    profile = known_windows_device() or "unknown"
    computer = re.sub(r"[^A-Za-z0-9_.-]", "-",
                      os.environ.get("COMPUTERNAME") or "unknown")
    return ("win-" + profile + "-" + computer)[:64]


def control_ssh_command(host: str, user: str, key: str, operation: str,
                        *, sha: str = "", request_id: str = "",
                        origin: str = "") -> list[str]:
    argv = ssh_command(host, user, "Состояние", key)
    if operation in CONTROL_ACTIONS.values():
        if sha == "installed" and operation in ("start", "stop"):
            pass
        elif EXACT_SHA.fullmatch(sha) is None:
            raise ValueError("Нужен точный SHA релиза (40 символов)")
        if REQUEST_ID.fullmatch(request_id) is None:
            raise ValueError("Недопустимый ID операции")
        src = origin or device_origin()
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", src) is None:
            raise ValueError("Недопустимое имя устройства")
        args = ["submit", operation, sha, "--request-id", request_id, "--origin", src]
    elif operation == "status":
        if REQUEST_ID.fullmatch(request_id) is None:
            raise ValueError("Недопустимый ID операции")
        args = ["status", request_id]
    elif operation == "list":
        args = ["list"]
    elif operation == "preflight":
        argv[-1] = PREFLIGHT
        return argv
    else:
        raise ValueError("Неизвестная операция")
    argv[-1] = CONTROL_MODULE + " " + " ".join(shlex.quote(part) for part in args)
    return argv


def preflight_failure_class(stderr: str, exit_code: int) -> str:
    """Return a bounded, non-secret reason; never echo arbitrary SSH stderr."""
    reason = stderr.casefold()
    if exit_code == 255:
        for pattern, kind in (
            ("host key verification failed", "SSH_HOST_KEY_REJECTED"),
            ("remote host identification has changed", "SSH_HOST_KEY_REJECTED"),
            ("permission denied", "SSH_AUTH_REJECTED"),
            ("identity file", "SSH_IDENTITY_UNAVAILABLE"),
            ("could not resolve hostname", "SSH_DNS_FAILURE"),
            ("no route to host", "SSH_NETWORK_UNREACHABLE"),
            ("connection refused", "SSH_CONNECTION_REFUSED"),
            ("connection timed out", "SSH_CONNECT_TIMEOUT"),
            ("operation timed out", "SSH_CONNECT_TIMEOUT"),
            ("banner exchange", "SSH_BANNER_FAILURE"),
            ("kex_exchange_identification", "SSH_BANNER_FAILURE"),
            ("connection reset", "SSH_CONNECTION_RESET"),
        ):
            if pattern in reason:
                return kind
        return "SSH_TRANSPORT_UNCLASSIFIED"
    if "no such file or directory" in reason:
        return "REMOTE_REQUIRED_FILE_MISSING"
    if "command not found" in reason:
        return "REMOTE_COMMAND_NOT_FOUND"
    if "curl: (7)" in reason or "curl: (28)" in reason:
        return "REMOTE_API_UNREACHABLE"
    if "curl: (22)" in reason:
        return "REMOTE_API_HTTP_FAILURE"
    return "REMOTE_COMMAND_FAILED"



# Owner-confirmed Windows laptop fingerprint, public metadata only.
LAPTOP_AGENT_FINGERPRINT = "SHA256:NcIbbPki11WrAx0RjjtAuUnY/bsgsnou2Syp6fNRRc0"


def _pinned_laptop_ssh(command: list[str]) -> bool:
    """Exclude PC, custom routes, unknown identities and any noncanonical SSH."""
    if (known_windows_device() != "laptop" or len(command) < 4
            or command[0] != "ssh" or command[1:3] != ["-F", "none"]
            or command[-2] != "root@83.217.213.181"):
        return False
    if not all(flag in command for flag in
               ("IdentitiesOnly=yes", "BatchMode=yes", "StrictHostKeyChecking=yes")):
        return False
    try:
        return command[command.index("-i") + 1] == str(
            Path.home() / ".ssh" / "bybitscanner_laptop")
    except (ValueError, IndexError):
        return False


def _local_agent_call(argv: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            argv, capture_output=True, text=True, errors="replace",
            stdin=subprocess.DEVNULL, timeout=12, creationflags=NO_WINDOW,
            check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_readonly_ssh_with_laptop_agent_recovery(
    command: list[str], **kwargs,
) -> tuple[subprocess.CompletedProcess, str]:
    """At most one same-request SSH retry after observed laptop publickey denial.

    Intended only for read-only callers. No key loading, passwords, config
    updates, SSH retries on banner timeout or retry of a mutating submit.
    """
    # Even an accidental call with a write-command must be rejected BEFORE
    # the first SSH launch, not merely excluded from its second attempt.
    if command and "tools.vps_owner_control submit " in command[-1]:
        raise ValueError("readonly_recovery_cannot_submit")
    first = subprocess.run(command, **kwargs)
    if (not _pinned_laptop_ssh(command) or first.returncode != 255
            or "permission denied (publickey" not in (first.stderr or "").casefold()):
        return first, ""

    windows = Path(os.environ.get("WINDIR", r"C:\Windows"))
    ps = [str(windows / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
          "-NoProfile", "-NonInteractive", "-Command"]
    service = _local_agent_call(
        ps + ["$s=Get-Service -Name ssh-agent -ErrorAction Stop; "
              "$s.Status.ToString() + '/' + $s.StartType.ToString()"])
    if service is None or service.returncode != 0:
        return first, "SSH_AGENT_RECOVERY=BLOCKED_SERVICE_STATUS_UNKNOWN"
    if service.stdout.strip().casefold() != "stopped/manual":
        return first, "SSH_AGENT_RECOVERY=BLOCKED_SERVICE_NOT_STOPPED_MANUAL"

    started = _local_agent_call(
        ps + ["Start-Service -Name ssh-agent -ErrorAction Stop"])
    if started is None or started.returncode != 0:
        return first, "SSH_AGENT_RECOVERY=BLOCKED_SERVICE_START_FAILED"

    ssh_add = str(windows / "System32" / "OpenSSH" / "ssh-add.exe")
    identities = _local_agent_call([ssh_add, "-l"])
    if (identities is None or identities.returncode != 0
            or LAPTOP_AGENT_FINGERPRINT not in (identities.stdout or "").split()):
        return first, "SSH_AGENT_RECOVERY=BLOCKED_PINNED_KEY_NOT_IN_AGENT"

    # Same *read-only* request, once; no alternate IP, key, auth or SSH settings.
    second = subprocess.run(command, **kwargs)
    return second, ("SSH_AGENT_RECOVERY=RETRY_ONCE_OK" if second.returncode == 0
                    else "SSH_AGENT_RECOVERY=RETRY_ONCE_UNPROVEN")


def precheck_laptop_owner_submit(
    command: list[str],
) -> tuple[bool, str]:
    """Prove laptop transport using the canonical read-only owner list first.

    This is NOT a submit retry. On unproven transport there is no submit.
    A successful check says only that the remote owner-list request completed.
    """
    if not _pinned_laptop_ssh(command):
        return True, ""
    if "tools.vps_owner_control submit " not in command[-1]:
        raise ValueError("expected_canonical_owner_submit")

    probe = command.copy()
    probe[-1] = CONTROL_MODULE + " list"  # read-only, same host/key/SSH options
    try:
        receipt, agent = run_readonly_ssh_with_laptop_agent_recovery(
            probe, capture_output=True, text=True, errors="replace",
            stdin=subprocess.DEVNULL, timeout=35, creationflags=NO_WINDOW,
            check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, "SSH_SUBMIT_PREFLIGHT=CLIENT_TIMEOUT_OR_SPAWN_FAILURE"

    if receipt.returncode != 0:
        reason = preflight_failure_class(receipt.stderr or "", receipt.returncode)
        return False, ("SSH_SUBMIT_PREFLIGHT=UNPROVEN\n"
                       "SSH_SUBMIT_PREFLIGHT_FAILURE_CLASS=" + reason
                       + ("\n" + agent if agent else ""))
    return True, ("SSH_SUBMIT_PREFLIGHT=REMOTE_LIST_OBSERVED"
                  + ("\n" + agent if agent else ""))


def run_cli(options: argparse.Namespace) -> int:
    host, user = (options.host, options.user) if options.host else preferred_route()
    if not host:
        print("VPS_ROUTE_UNCONFIGURED: existing SSH alias or BYBITSCANNER_VPS_SSH_TARGET required")
        return 2
    key = options.key if options.key is not None else preferred_key(host, user)
    req = options.request_id or (uuid.uuid4().hex if options.operation in
                                  CONTROL_ACTIONS.values() else
                                  recover_last_request_id() if options.operation == "status" else "")
    sha = options.sha or ("installed" if options.operation in ("start", "stop") else "")
    try:
        argv = control_ssh_command(host, user, key, options.operation,
                                   sha=sha, request_id=req)
    except ValueError as exc:
        print("BLOCKED: " + str(exc))
        return 2
    if options.operation in CONTROL_ACTIONS.values():
        try:
            remember_request_id(req)
        except OSError:
            print("BLOCKED: request ID cannot be preserved; no operation sent")
            return 2
        print("REQUEST_ID=" + req, flush=True)
    if options.operation in CONTROL_ACTIONS.values():
        confirmed, proof = precheck_laptop_owner_submit(argv)
        if proof:
            print(proof, flush=True)
        if not confirmed:
            print("SUBMISSION=NOT_SENT; request_id=" + req)
            return 2
    try:
        if options.operation in ("status", "list", "preflight"):
            completed, recovery = run_readonly_ssh_with_laptop_agent_recovery(
                argv, capture_output=True, text=True, timeout=35,
                stdin=subprocess.DEVNULL, check=False)
        else:
            completed = subprocess.run(argv, capture_output=True, text=True,
                                       timeout=35, stdin=subprocess.DEVNULL, check=False)
            recovery = ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        if options.operation == "preflight":
            failure = ("SSH_CLIENT_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired)
                       else "SSH_CLIENT_SPAWN_FAILURE")
            print("PREFLIGHT_FAILURE_CLASS=" + failure)
            print("PREFLIGHT_BLOCKED_UNPROVEN")
        else:
            print("SSH_UNPROVEN; request_id=" + req + "; check status; do not resubmit")
        return 2
    output = completed.stdout.strip()
    print(output)
    if recovery:
        print(recovery)
    if options.operation == "preflight":
        print("PREFLIGHT_SSH_EXIT_CODE=" + str(completed.returncode))
        if completed.returncode == 0 and "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED" in output:
            print("PREFLIGHT_OBSERVED_NOT_ACCEPTED")
            return 0
        if completed.returncode != 0:
            print("PREFLIGHT_FAILURE_CLASS=" +
                  preflight_failure_class(completed.stderr or "", completed.returncode))
        else:
            print("PREFLIGHT_FAILURE_CLASS=REMOTE_RECEIPT_MISSING")
        print("PREFLIGHT_BLOCKED_UNPROVEN")
        return 2
    if options.operation == "status":
        lines = set(output.splitlines())
        # systemctl-backed status uses nonzero exit codes for known states.
        # Require the exact request ID and matching state/code; SSH failure
        # or an unrelated/partial reply must remain UNPROVEN.
        if "REQUEST_ID=" + req in lines:
            if completed.returncode == 0 and "STATUS=FINISHED_OK" in lines:
                print("OPERATION_FINISHED_OK; request_id=" + req)
                return 0
            if completed.returncode == 3 and "STATUS=RUNNING" in lines:
                print("OPERATION_RUNNING; request_id=" + req)
                return 3
            if completed.returncode == 2 and "STATUS=FAILED" in lines:
                print("OPERATION_FAILED; request_id=" + req)
                return 2
        print("REMOTE_STATUS_UNPROVEN; request_id=" + req)
        return 2
    if completed.returncode != 0:
        print("REMOTE_STATUS_UNPROVEN; request_id=" + req)
        return 2
    if options.operation in CONTROL_ACTIONS.values():
        print("SUBMITTED_NOT_COMPLETE; request_id=" + req)
    return 0


class VPSManager(tk.Tk):
    def __init__(self, host: str = "", user: str = "bybitscanner", key: str | None = None) -> None:
        super().__init__()
        self.title("BybitScanner VPS Manager — PAPER")
        self.geometry("880x510")
        self.minsize(780, 380)
        automatic = preferred_route() if not host else (host, user)
        self.host = tk.StringVar(value=automatic[0])
        self.user = tk.StringVar(value=automatic[1])
        if key is None:
            key = preferred_key(*automatic)
        self.sha = tk.StringVar(value="")
        self.last_request_id = recover_last_request_id()
        self.request_id = tk.StringVar(value=self.last_request_id)
        self.origin = device_origin()
        self.key = tk.StringVar(value=key)
        self.status = tk.StringVar(value="Не подключено · PAPER only")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        self._copy_seq = 0
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="VPS адрес:").grid(row=0, column=0, sticky="w")
        host_entry = ttk.Entry(top, textvariable=self.host, width=30)
        host_entry.grid(row=0, column=1, padx=6)
        ttk.Label(top, text="SSH пользователь:").grid(row=0, column=2)
        user_entry = ttk.Entry(top, textvariable=self.user, width=18)
        user_entry.grid(row=0, column=3, padx=6)
        ttk.Label(top, text="SSH ключ:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        key_entry = ttk.Entry(top, textvariable=self.key, width=60)
        key_entry.grid(
            row=1, column=1, columnspan=3, padx=6, pady=(7, 0), sticky="we"
        )
        ttk.Label(top, textvariable=self.status).grid(row=2, column=0, columnspan=4, sticky="w", pady=9)
        ttk.Label(top, text="Целевой SHA (для обновления):").grid(row=3, column=0, sticky="w")
        self.sha_entry = ttk.Entry(top, textvariable=self.sha, width=48)
        self.sha_entry.grid(row=3, column=1, columnspan=2, sticky="we")
        self.sha_entry.bind("<Control-KeyPress>", self.paste_sha_hotkey)
        ttk.Button(top, text="Вставить SHA", command=self.paste_sha).grid(
            row=3, column=3, padx=6, sticky="w")
        for entry in (host_entry, user_entry, key_entry):
            entry.bind("<Control-KeyPress>", self.paste_text_hotkey)
        ttk.Label(top, text="Устройство: " + self.origin).grid(
            row=4, column=0, columnspan=4, sticky="w")
        ttk.Label(top, text="ID операции (для статуса):").grid(
            row=5, column=0, sticky="w", pady=(5, 0))
        id_controls = ttk.Frame(top)
        id_controls.grid(row=5, column=1, columnspan=3, sticky="w", pady=(5, 0))
        self.request_id_entry = ttk.Entry(
            id_controls, textvariable=self.request_id, width=36, show="")
        self.request_id_entry.pack(side="left", padx=6)
        self.request_id_entry.bind("<Control-KeyPress>", self.paste_request_id_hotkey)
        ttk.Button(id_controls, text="Вставить ID",
                   command=self.paste_request_id).pack(side="left", padx=6)
        buttons = ttk.Frame(self, padding=(12, 0, 12, 9))
        buttons.pack(fill="x")
        self.buttons = []
        for index, name in enumerate(ACTIONS):
            button = ttk.Button(buttons, text=name, command=lambda selected=name: self.run_action(selected))
            button.grid(row=index // 3, column=index % 3, padx=(0, 7), pady=3, sticky="ew")
            self.buttons.append(button)
        for index, (label, mode) in enumerate(CONTROL_ACTIONS.items(), start=len(ACTIONS)):
            button = ttk.Button(buttons, text=label,
                                command=lambda selected=mode: self.run_control(selected))
            button.grid(row=index // 3, column=index % 3, padx=(0, 7), pady=3, sticky="ew")
            self.buttons.append(button)
        for index, (label, mode) in enumerate((
            ("Автопроверка VPS (только чтение)", "preflight"),
            ("Статус по ID операции", "status"),
            ("Все операции монолита", "list"),
        ), start=len(ACTIONS) + len(CONTROL_ACTIONS)):
            button = ttk.Button(buttons, text=label,
                                command=lambda selected=mode: self.run_control(selected))
            button.grid(row=index // 3, column=index % 3, padx=(0, 7), pady=3, sticky="ew")
            self.buttons.append(button)
        update_button = ttk.Button(buttons, text="Обновление",
                                   command=self.update_desktop)
        update_index = len(ACTIONS) + len(CONTROL_ACTIONS) + 3
        update_button.grid(row=update_index // 3, column=update_index % 3,
                           padx=(0, 7), pady=3, sticky="ew")
        self.buttons.append(update_button)
        for column in range(3):
            buttons.columnconfigure(column, weight=1)
        ttk.Label(self, text="Журнал (только чтение)", padding=(12, 3)).pack(anchor="w")
        frame = ttk.Frame(self, padding=(12, 0, 12, 12))
        frame.pack(fill="both", expand=True)
        self.log = tk.Text(frame, wrap="word", state="disabled", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.after(100, self.drain)

    def update_desktop(self) -> None:
        """Update ONLY this local manager, never call owner VPS monolith."""
        if self.busy:
            return
        if not messagebox.askyesno("Обновление VPS Manager",
                                  "Проверить и установить опубликованный релиз VPS Manager?"):
            return
        self.busy = True
        self.status.set("Обновление локального VPS Manager")
        for button in self.buttons:
            button.state(["disabled"])
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self) -> None:
        from tools.manager_self_update import stage_manager
        from research.local_replay_viewer.desktop_update import UpdateBlocked
        try:
            self.events.put(("desktop-update-handoff", stage_manager()))
        except (UpdateBlocked, OSError, ValueError) as exc:
            # Never reveal arbitrary remote URLs or exception details.
            reason = str(exc) if isinstance(exc, UpdateBlocked) else type(exc).__name__
            self.events.put(("failure", "LOCAL_UPDATE_BLOCKED=" + reason))

    def write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def copy_result(self, result: str, tag: str | None = None) -> None:
        """Copy one finished action and visibly acknowledge a successful click."""
        try:
            self.clipboard_clear()
            self.clipboard_append(result)
            self.update_idletasks()
        except tk.TclError:
            messagebox.showerror("VPS Manager", "Не удалось скопировать результат")
            return
        if tag is not None:
            self.log.configure(state="normal")
            try:
                first = self.log.index(f"{tag}.first")
                self.log.replace(first, f"{tag}.last", "✓ Скопировано", tag)
                self.log.tag_configure(tag, foreground="#17803d", underline=False)
            finally:
                self.log.configure(state="disabled")

    def write_result(self, result: str) -> None:
        """Append an action's output, then its visible independent copy link."""
        self._copy_seq += 1
        tag = f"copy_result_{self._copy_seq}"
        self.log.configure(state="normal")
        self.log.insert("end", result + "\n")
        self.log.insert("end", "📋 Скопировать результат", (tag,))
        self.log.insert("end", "\n\n")
        self.log.tag_configure(tag, foreground="#0066bb", underline=True)
        self.log.tag_bind(tag, "<Button-1>",
                          lambda _event, output=result, target=tag:
                          self.copy_result(output, target))
        self.log.see("end")
        self.log.configure(state="disabled")

    def run_action(self, name: str) -> None:
        if self.busy:
            return
        try:
            command = ssh_command(self.host.get(), self.user.get(), name, self.key.get())
        except ValueError as exc:
            messagebox.showerror("VPS Manager", str(exc))
            return
        self.busy = True
        self.status.set(f"Выполняется: {name}")
        for button in self.buttons:
            button.state(["disabled"])
        self.write(f"\n> {name}")
        threading.Thread(target=self.worker, args=(command,), daemon=True).start()

    def paste_sha(self) -> None:
        """Paste an exact release SHA locally; never send a remote operation."""
        try:
            value = self.clipboard_get().strip().lower()
        except tk.TclError:
            messagebox.showerror("VPS Manager", "Буфер обмена пуст или недоступен")
            return
        if EXACT_SHA.fullmatch(value) is None:
            messagebox.showerror("VPS Manager", "В буфере нет SHA релиза (40 hex символов)")
            return
        self.sha.set(value)
        self.sha_entry.icursor("end")
        self.sha_entry.focus_set()

    def paste_sha_hotkey(self, event: tk.Event) -> str | None:
        if (event.keysym.casefold() in ("v", "cyrillic_em")
                or event.keycode == 86):
            self.paste_sha()
            return "break"
        return None

    def paste_text_hotkey(self, event: tk.Event) -> str | None:
        """Layout-independent Ctrl+V for ordinary connection fields."""
        if (event.keysym.casefold() not in ("v", "cyrillic_em")
                and event.keycode != 86):
            return None
        try:
            value = self.clipboard_get()
        except tk.TclError:
            messagebox.showerror("VPS Manager", "Буфер обмена пуст или недоступен")
            return "break"
        try:
            event.widget.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        event.widget.insert("insert", value)
        return "break"

    def paste_request_id(self) -> None:
        """Paste and show the exact operation ID without an SSH call."""
        try:
            request = self.clipboard_get().strip().lower()
        except tk.TclError:
            messagebox.showerror("VPS Manager", "Буфер обмена пуст или недоступен")
            return
        if REQUEST_ID.fullmatch(request) is None:
            messagebox.showerror(
                "VPS Manager", "В буфере нет ID операции (32 шестнадцатеричных символа)")
            return
        self.request_id.set(request)
        self.request_id_entry.icursor("end")
        self.request_id_entry.focus_set()

    def paste_request_id_hotkey(self, event: tk.Event) -> str | None:
        """Handle Ctrl+V regardless of English or Russian keyboard layout."""
        if (event.keysym.casefold() in ("v", "cyrillic_em")
                or event.keycode == 86):
            self.paste_request_id()
            return "break"
        return None

    def run_control(self, mode: str) -> None:
        if self.busy:
            return
        sha = self.sha.get().strip() or (
            "installed" if mode in ("start", "stop") else "")
        request = (uuid.uuid4().hex if mode in CONTROL_ACTIONS.values()
                   else self.request_id.get().strip() if mode == "status"
                   else self.last_request_id)
        if mode == "status" and not request:
            messagebox.showinfo("VPS Manager", "Введите точный ID операции (32 символа)")
            return
        try:
            command = control_ssh_command(
                self.host.get(), self.user.get(), self.key.get(),
                mode, sha=sha, request_id=request, origin=self.origin)
        except ValueError as exc:
            messagebox.showerror("VPS Manager", str(exc))
            return
        if mode in CONTROL_ACTIONS.values():
            if not messagebox.askyesno(
                "Подтверждение PAPER", f"Отправить на VPS действие {mode} для {sha}?"):
                return
            try:
                remember_request_id(request)
            except OSError:
                messagebox.showerror(
                    "VPS Manager", "Не удалось сохранить ID операции. Действие не отправлено."
                )
                return
            self.last_request_id = request
            self.request_id.set(request)
        self.busy = True
        self.status.set("Выполняется: " + mode)
        for button in self.buttons:
            button.state(["disabled"])
        self.write(f"\n> {mode} · {request}")
        threading.Thread(target=self.worker_control,
                         args=(command, mode, request), daemon=True).start()

    def worker_control(self, command: list[str], mode: str, request: str) -> None:
        try:
            precheck_receipt = ""
            if mode in CONTROL_ACTIONS.values():
                confirmed, precheck_receipt = precheck_laptop_owner_submit(command)
                if not confirmed:
                    self.events.put(("unproven",
                                     ("SUBMISSION=NOT_SENT; REQUEST_ID=" + request
                                      + "\n" + precheck_receipt)))
                    return
            if mode not in CONTROL_ACTIONS.values():
                result, recovery = run_readonly_ssh_with_laptop_agent_recovery(
                    command, capture_output=True, text=True, errors="replace",
                    timeout=35, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                    check=False)
            else:
                try:
                    result = subprocess.run(
                        command, capture_output=True, text=True, errors="replace",
                        timeout=35, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                        check=False)
                except subprocess.TimeoutExpired:
                    # Submit may have reached the VPS before SSH timed out.
                    # Never resend it; inspect only the original durable UUID.
                    result = subprocess.CompletedProcess(
                        command, 255, stdout="", stderr="SSH_SUBMIT_TIMEOUT")
                recovery = ""
            output = result.stdout.strip()
            if mode not in CONTROL_ACTIONS.values():
                if mode == "status":
                    state = gui_owner_status(output, result.returncode, request)
                elif mode == "preflight":
                    state = ("observed" if result.returncode == 0 and
                             "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED" in output
                             else "unproven")
                elif mode == "list":
                    if result.returncode != 0 or output == "REQUEST_LIST=UNPROVEN":
                        state = "unproven"
                        output = ("REQUEST_LIST=UNPROVEN\nLIST_EXIT_CODE=" +
                                  str(result.returncode) +
                                  "\nLIST_FAILURE_CLASS=" +
                                  preflight_failure_class(result.stderr or "",
                                                          result.returncode))
                    elif not output:
                        state = "observed"
                        output = ("REQUEST_LIST=EMPTY\n"
                                  "Список сохранённых операций пуст; это не "
                                  "доказательство отсутствия прежних операций.")
                    else:
                        state = "observed"
                else:
                    state = "observed" if result.returncode == 0 else "unproven"
                if mode == "preflight" and state == "unproven":
                    reason = (preflight_failure_class(result.stderr or "", result.returncode)
                              if result.returncode != 0 else "REMOTE_RECEIPT_MISSING")
                    output += ("\nPREFLIGHT_SSH_EXIT_CODE=" + str(result.returncode) +
                               "\nPREFLIGHT_FAILURE_CLASS=" + reason)
                if recovery:
                    output = (output + "\n" + recovery).strip()
                self.events.put((state, output or "Статус не доказан"))
                return
            # Lost submit reply => only query the same request; never replay it.
            status_command = control_ssh_command(
                self.host.get(), self.user.get(), self.key.get(), "status",
                request_id=request)
            state = ("submitted" if result.returncode == 0
                     and "REQUEST_ID=" + request in output.splitlines()
                     and any(line.startswith("SUBMISSION=ACCEPTED")
                             for line in output.splitlines())
                     else "unproven")
            state, details = watch_owner_request(
                status_command, request, initially_submitted=(state == "submitted"))
            self.events.put((state, (precheck_receipt + "\n" if precheck_receipt else "")
                             + (output or "Ответ запуска неизвестен")
                             + "\n" + details + "\nREQUEST_ID=" + request))
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            if mode == "list":
                reason = ("SSH_CLIENT_TIMEOUT" if isinstance(exc, subprocess.TimeoutExpired)
                          else "SSH_CLIENT_SPAWN_FAILURE")
                self.events.put(("unproven", "REQUEST_LIST=UNPROVEN\n"
                                 "LIST_FAILURE_CLASS=" + reason))
            else:
                self.events.put(("failure", "SSH_STATUS_UNPROVEN; REQUEST_ID=" + request
                                 + "; повторять операцию нельзя, проверяйте статус"))

    def worker(self, command: list[str]) -> None:
        try:
            result, recovery = run_readonly_ssh_with_laptop_agent_recovery(
                command, capture_output=True, text=True, errors="replace",
                timeout=45, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                env=os.environ.copy(), check=False,
            )
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            if recovery:
                output = (output + "\n" + recovery).strip()
            status = "observed" if result.returncode == 0 else "failure"
            self.events.put((status, f"{output or '(нет вывода)'}\nExit code: {result.returncode}"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.events.put(("failure", f"Ошибка SSH: {type(exc).__name__}"))

    def drain(self) -> None:
        try:
            while True:
                kind, result = self.events.get_nowait()
                if kind == "desktop-update-handoff":
                    self.write("Обновление проверено; передаю запуск новой версии.")
                    self.destroy()
                    return
                self.write_result(result)
                self.busy = False
                labels = {
                    "success": "Успешно · монолит завершил операцию; приёмка владельцем отдельно",
                    "observed": "Данные VPS получены · готовность ещё не доказана",
                    "submitted": "Отправлено / выполняется",
                    "failed": "Операция завершилась ошибкой",
                    "unproven": "Результат не доказан · проверьте статус",
                }
                self.status.set(labels.get(kind, "Ошибка / результат не доказан"))
                for button in self.buttons:
                    button.state(["!disabled"])
        except queue.Empty:
            pass
        self.after(100, self.drain)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    # Lets a local desktop shortcut prefill the fields, so the VPS address
    # lives on the owner's machine and never in the repository.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--host", default="")
    parser.add_argument("--user", default="bybitscanner")
    parser.add_argument("--key", default=None)
    parser.add_argument("--operation", choices=(*CONTROL_ACTIONS.values(),
                                                 "status", "list", "preflight"), default=None)
    parser.add_argument("--sha", default="")
    parser.add_argument("--request-id", default="")
    args, _unknown = parser.parse_known_args(argv)
    return args


if __name__ == "__main__":
    options = parse_args()
    if options.operation:
        sys.exit(run_cli(options))
    VPSManager(options.host, options.user, options.key).mainloop()
