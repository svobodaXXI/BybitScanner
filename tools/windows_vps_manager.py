"""BybitScanner VPS Manager — standalone Windows, read-only MVP.

Reuses the repository's diagnostic entry points; never manages trading orders.
Requires Windows OpenSSH, separately configured SSH key and verified known_hosts.
Run: py -3 tools/windows_vps_manager.py
"""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

PROJECT = "/opt/BybitScanner"
VENV = f"{PROJECT}/venv/bin/python"
HOST_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
USER_PATTERN = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")
# Fixed, audited commands: no free-form shell and no trading mutations.
ACTIONS = {
    "Состояние": (
        "systemctl show bybitscanner-paper-backend.service "
        "-p ActiveState -p SubState -p MainPID; "
        "systemctl show bybitscanner-telegram.service -p ActiveState -p SubState; "
        "systemctl show bybitscanner-paper-start.service -p ActiveState -p SubState"
    ),
    "Диагностика PAPER": f"cd {PROJECT} && {VENV} -m tools.vps_check --no-systemd",
    "Git / локальные изменения": (
        f"git -C {PROJECT} status --short && "
        f"git -C {PROJECT} branch --show-current && "
        f"git -C {PROJECT} rev-parse --short HEAD"
    ),
    "Предпроверка обновления": (
        "printf '=== GIT ===\\n'; "
        f"git -C {PROJECT} status --porcelain=v1; "
        f"git -C {PROJECT} branch --show-current; "
        f"git -C {PROJECT} rev-parse HEAD; "
        "printf '=== BACKEND ===\\n'; "
        "systemctl show bybitscanner-paper-backend.service "
        "-p ActiveState -p SubState -p MainPID; "
        "printf '=== PAPER HEALTH ===\\n'; "
        "curl -fsS --connect-timeout 3 --max-time 6 "
        "http://127.0.0.1:8765/api/health"
    ),
    "Последние журналы": (
        "journalctl -u bybitscanner-paper-backend.service "
        "--no-pager -n 35 --output=short-iso"
    ),
}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def ssh_command(host: str, user: str, action: str) -> list[str]:
    host = host.strip()
    user = user.strip()
    if not HOST_PATTERN.fullmatch(host) or host.startswith("-"):
        raise ValueError("Недопустимое имя или адрес VPS")
    if not USER_PATTERN.fullmatch(user):
        raise ValueError("Недопустимое имя пользователя")
    if action not in ACTIONS:
        raise ValueError("Неизвестная операция")
    return [
        "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
        "-o", "ConnectTimeout=8", "-o", "NumberOfPasswordPrompts=0",
        "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
        f"{user}@{host}", ACTIONS[action],
    ]


class VPSManager(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BybitScanner VPS Manager — PAPER")
        self.geometry("880x510")
        self.minsize(780, 380)
        self.host = tk.StringVar(value="")
        self.user = tk.StringVar(value="bybitscanner")
        self.status = tk.StringVar(value="Не подключено · PAPER only")
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.busy = False
        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="VPS адрес:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.host, width=30).grid(row=0, column=1, padx=6)
        ttk.Label(top, text="SSH пользователь:").grid(row=0, column=2)
        ttk.Entry(top, textvariable=self.user, width=18).grid(row=0, column=3, padx=6)
        ttk.Label(top, textvariable=self.status).grid(row=1, column=0, columnspan=4, sticky="w", pady=9)
        buttons = ttk.Frame(self, padding=(12, 0, 12, 9))
        buttons.pack(fill="x")
        self.buttons = []
        for index, name in enumerate(ACTIONS):
            button = ttk.Button(buttons, text=name, command=lambda selected=name: self.run_action(selected))
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
            command = ssh_command(self.host.get(), self.user.get(), name)
        except ValueError as exc:
            messagebox.showerror("VPS Manager", str(exc))
            return
        self.busy = True
        self.status.set(f"Выполняется: {name}")
        for button in self.buttons:
            button.state(["disabled"])
        self.write(f"\n> {name}")
        threading.Thread(target=self.worker, args=(command,), daemon=True).start()

    def worker(self, command: list[str]) -> None:
        try:
            result = subprocess.run(
                command, capture_output=True, text=True, errors="replace",
                timeout=45, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW,
                env=os.environ.copy(), check=False,
            )
            output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
            self.events.put(("done", f"{output or '(нет вывода)'}\nExit code: {result.returncode}"))
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.events.put(("done", f"Ошибка SSH: {exc}"))

    def drain(self) -> None:
        try:
            while True:
                _kind, result = self.events.get_nowait()
                self.write(result)
                self.busy = False
                self.status.set("Завершено · проверьте Exit code в журнале")
                for button in self.buttons:
                    button.state(["!disabled"])
        except queue.Empty:
            pass
        self.after(100, self.drain)


if __name__ == "__main__":
    VPSManager().mainloop()
