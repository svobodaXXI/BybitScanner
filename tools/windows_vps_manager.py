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
    "set -e; "
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
    try:
        completed = subprocess.run(argv, capture_output=True, text=True,
                                   timeout=35, stdin=subprocess.DEVNULL, check=False)
    except (OSError, subprocess.TimeoutExpired):
        print("SSH_UNPROVEN; request_id=" + req + "; check status; do not resubmit")
        return 2
    output = completed.stdout.strip()
    print(output)
    if options.operation == "preflight":
        if completed.returncode == 0 and "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED" in output:
            print("PREFLIGHT_OBSERVED_NOT_ACCEPTED")
            return 0
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
        self.origin = device_origin()
        self.key = tk.StringVar(value=key)
        self.status = tk.StringVar(value="Не подключено · PAPER only")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="VPS адрес:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.host, width=30).grid(row=0, column=1, padx=6)
        ttk.Label(top, text="SSH пользователь:").grid(row=0, column=2)
        ttk.Entry(top, textvariable=self.user, width=18).grid(row=0, column=3, padx=6)
        ttk.Label(top, text="SSH ключ:").grid(row=1, column=0, sticky="w", pady=(7, 0))
        ttk.Entry(top, textvariable=self.key, width=60).grid(
            row=1, column=1, columnspan=3, padx=6, pady=(7, 0), sticky="we"
        )
        ttk.Label(top, textvariable=self.status).grid(row=2, column=0, columnspan=4, sticky="w", pady=9)
        ttk.Label(top, text="Целевой SHA (для обновления):").grid(row=3, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.sha, width=48).grid(
            row=3, column=1, columnspan=3, sticky="we")
        ttk.Label(top, text="Устройство: " + self.origin).grid(
            row=4, column=0, columnspan=4, sticky="w")
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
            ("Статус последней операции", "status"),
            ("Все операции монолита", "list"),
        ), start=len(ACTIONS) + len(CONTROL_ACTIONS)):
            button = ttk.Button(buttons, text=label,
                                command=lambda selected=mode: self.run_control(selected))
            button.grid(row=index // 3, column=index % 3, padx=(0, 7), pady=3, sticky="ew")
            self.buttons.append(button)
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

    def write(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
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

    def run_control(self, mode: str) -> None:
        if self.busy:
            return
        sha = self.sha.get().strip() or (
            "installed" if mode in ("start", "stop") else "")
        request = (uuid.uuid4().hex if mode in CONTROL_ACTIONS.values()
                   else self.last_request_id)
        if mode == "status" and not request:
            messagebox.showinfo("VPS Manager", "Операций в этом сеансе пока нет")
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
        self.busy = True
        self.status.set("Выполняется: " + mode)
        for button in self.buttons:
            button.state(["disabled"])
        self.write(f"\n> {mode} · {request}")
        threading.Thread(target=self.worker_control,
                         args=(command, mode, request), daemon=True).start()

    def worker_control(self, command: list[str], mode: str, request: str) -> None:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, errors="replace",
                timeout=35, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                check=False)
            output = result.stdout.strip()
            if mode not in CONTROL_ACTIONS.values():
                if mode == "status":
                    state = gui_owner_status(output, result.returncode, request)
                elif mode == "preflight":
                    state = ("observed" if result.returncode == 0 and
                             "PREFLIGHT_READ_ONLY_DATA_COLLECTED_NOT_ACCEPTED" in output
                             else "unproven")
                else:
                    state = "success" if result.returncode == 0 else "failure"
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
            for attempt in range(3):
                if attempt:
                    time.sleep(2)
                probe = subprocess.run(
                    status_command, capture_output=True, text=True, errors="replace",
                    timeout=20, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                    check=False)
                verified = gui_owner_status(probe.stdout, probe.returncode, request)
                if verified != "unproven":
                    state = verified
                    output += "\n" + probe.stdout.strip()
                    break
            self.events.put((state, (output or "Ответ запуска неизвестен")
                             + "\nREQUEST_ID=" + request))
        except (OSError, subprocess.TimeoutExpired, ValueError):
            self.events.put(("failure", "SSH_STATUS_UNPROVEN; REQUEST_ID=" + request
                             + "; повторять операцию нельзя, проверяйте статус"))

    def worker(self, command: list[str]) -> None:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, errors="replace",
                timeout=45, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                env=os.environ.copy(), check=False,
            )
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            status = "success" if result.returncode == 0 else "failure"
            self.events.put((status, f"{output or '(нет вывода)'}\nExit code: {result.returncode}"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.events.put(("failure", f"Ошибка SSH: {type(exc).__name__}"))

    def drain(self) -> None:
        try:
            while True:
                kind, result = self.events.get_nowait()
                self.write(result)
                self.busy = False
                labels = {
                    "success": "Успешно · подтверждён результат",
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
