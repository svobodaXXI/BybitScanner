"""Exact-ownership fallback for legacy BybitScanner consoles without a shutdown endpoint.

Used only after the caller proved the health component + PAPER DB identity, finished
the canonical Scanner/Robot stop, and the graceful endpoint answered 404/501. The
listener PID of the exact localhost port is resolved, its ancestry is proven by
command line up to the launcher-owned console, and only that verified chain is
terminated by exact PID. Anything ambiguous raises and nothing is terminated.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable, Mapping

BACKEND = "backend"
TELEGRAM = "telegram"
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class LegacyOwnerUnproven(RuntimeError):
    """The legacy listener's owning process chain could not be proven exactly."""


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    ppid: int
    name: str
    command_line: str
    executable: str
    created: int


def _has_path(command_line: str, path: Path) -> bool:
    needle = re.escape(str(path).lower())
    return re.search(rf"(^|[\s\"'&;]){needle}($|[\s\"'&;])", command_line.lower()) is not None


def _has_flag(command_line: str, flag: str) -> bool:
    return re.search(rf"(^|\s){re.escape(flag)}(\s|$)", command_line.lower()) is not None


def _is(process: ProcessInfo, name: str) -> bool:
    return process.name.lower() == name


def _parent(process: ProcessInfo, processes: Mapping[int, ProcessInfo]) -> ProcessInfo:
    parent = processes.get(process.ppid)
    # A parent created after its child is a reused PID, not the real ancestor.
    if parent is None or parent.created > process.created:
        raise LegacyOwnerUnproven(f"ancestor of PID {process.pid} is not provable")
    return parent


def select_legacy_chain(
    kind: str, listener_pids: Iterable[int], processes: Mapping[int, ProcessInfo], root: Path,
) -> tuple[int, ...]:
    """Verified chain listener -> ... -> console owner, in termination order."""
    listeners = {int(pid) for pid in listener_pids}
    if len(listeners) != 1:
        raise LegacyOwnerUnproven(f"expected exactly one listener PID, found {sorted(listeners)}")
    listener = processes.get(listeners.pop())
    if listener is None or not _is(listener, "python.exe"):
        raise LegacyOwnerUnproven("listener is not a proven Python process")

    venv_python = str(root / "venv" / "Scripts" / "python.exe").lower()
    if kind == BACKEND:
        script = root / "start_paper_backend.bat"

        def python_proven(command_line: str) -> bool:
            return _has_flag(command_line, "-m") and re.search(
                r"(^|\s)-m\s+terminal\.runtime\.paper_http_server(\s|$)", command_line.lower(),
            ) is not None
    elif kind == TELEGRAM:
        script = root / "telegram_monitoring.py"

        def python_proven(command_line: str) -> bool:
            return _has_path(command_line, script)
    else:
        raise LegacyOwnerUnproven(f"unknown legacy process kind {kind!r}")
    if not python_proven(listener.command_line):
        raise LegacyOwnerUnproven("listener command line is not the expected BybitScanner process")

    chain = [listener.pid]
    rooted = listener.executable.lower() == venv_python
    parent = _parent(listener, processes)
    if _is(parent, "python.exe"):
        # Windows venv redirector: venv\Scripts\python.exe runs the base interpreter as a child.
        if parent.executable.lower() != venv_python or not python_proven(parent.command_line):
            raise LegacyOwnerUnproven("Python launcher is not this project's venv")
        rooted = True
        chain.append(parent.pid)
        parent = _parent(parent, processes)
    if not rooted:
        raise LegacyOwnerUnproven("listener interpreter is not this project's venv")

    if kind == BACKEND:
        if _is(parent, "cmd.exe") and _has_path(parent.command_line, script):
            if _has_flag(parent.command_line, "/k"):
                return (*chain, parent.pid)
            if _has_flag(parent.command_line, "/c"):
                # Canonical tools.runtime_intent launches a visible console as
                # cmd.exe /c start_paper_backend.bat.  Older launchers wrapped
                # that same exact cmd in PowerShell -NoExit.  In both cases the
                # cmd process is already a fully proven project owner because
                # the listener is this venv/module and cmd names this exact bat.
                owner = processes.get(parent.ppid)
                if (
                    owner is not None and owner.created <= parent.created
                    and _is(owner, "powershell.exe")
                    and _has_flag(owner.command_line, "-noexit")
                    and _has_path(owner.command_line, script)
                ):
                    return (*chain, parent.pid, owner.pid)
                return (*chain, parent.pid)
    else:
        if _is(parent, "cmd.exe") and _has_path(parent.command_line, script):
            if _has_flag(parent.command_line, "/k"):
                return (*chain, parent.pid)
            if _has_flag(parent.command_line, "/c") \
                    and _has_path(parent.command_line, root / "venv" / "Scripts" / "python.exe"):
                # Canonical tools.runtime_intent uses
                # cmd.exe /c <venv-python> telegram_monitoring.py.
                return (*chain, parent.pid)
        if _is(parent, "powershell.exe") and _has_flag(parent.command_line, "-noexit") \
                and _has_path(parent.command_line, script):
            return (*chain, parent.pid)
    raise LegacyOwnerUnproven("console owner is not a proven BybitScanner launcher window")


_QUERY = r"""
$ErrorActionPreference = 'Stop'
$listeners = @(Get-NetTCPConnection -State Listen -LocalAddress '127.0.0.1' -LocalPort {port} -ErrorAction SilentlyContinue |
  ForEach-Object {{ [int]$_.OwningProcess }} | Sort-Object -Unique)
$chain = @()
if ($listeners.Count -eq 1) {{
  $id = $listeners[0]
  for ($i = 0; $i -lt 6 -and $id; $i++) {{
    $p = Get-CimInstance Win32_Process -Filter "ProcessId = $id"
    if (-not $p) {{ break }}
    $chain += [pscustomobject]@{{
      pid = [int]$p.ProcessId; ppid = [int]$p.ParentProcessId; name = [string]$p.Name
      command_line = [string]$p.CommandLine; executable = [string]$p.ExecutablePath
      created = [long]$p.CreationDate.ToFileTimeUtc()
    }}
    $id = [int]$p.ParentProcessId
  }}
}}
[pscustomobject]@{{ listeners = $listeners; chain = $chain }} | ConvertTo-Json -Depth 4 -Compress
"""


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def resolve_legacy_chain(kind: str, host: str, port: int, root: Path) -> tuple[int, ...]:
    """Exact listener + ancestry for ``host:port`` (read-only query), proven by command line."""
    if os.name != "nt":
        raise LegacyOwnerUnproven("legacy process fallback is available only on Windows")
    if host != "127.0.0.1" or not isinstance(port, int) or not 0 < port < 65536:
        raise LegacyOwnerUnproven(f"legacy listener {host}:{port} is not an exact localhost port")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _QUERY.format(port=port)],
            capture_output=True, text=True, timeout=30, creationflags=_NO_WINDOW,
        )
        payload = json.loads(completed.stdout)
        listeners = [int(pid) for pid in _as_list(payload.get("listeners"))]
        processes = {
            int(item["pid"]): ProcessInfo(
                int(item["pid"]), int(item["ppid"]), str(item["name"] or ""),
                str(item["command_line"] or ""), str(item["executable"] or ""), int(item["created"]),
            )
            for item in _as_list(payload.get("chain"))
        }
    except Exception as exc:
        raise LegacyOwnerUnproven(f"listener ownership query failed: {type(exc).__name__}") from exc
    return select_legacy_chain(kind, listeners, processes, root)


def terminate_exact_pids(pids: Iterable[int]) -> None:
    """Force-terminate each verified PID individually; never by name, never with /T."""
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/F"],
            capture_output=True, text=True, timeout=15, creationflags=_NO_WINDOW,
        )
