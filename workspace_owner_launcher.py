"""Owner-PC handoff for Telegram workspace requests; no trading runtime starts."""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent
ALLOWED_TF = frozenset(("15s", "1m", "5m", "15m", "1h", "1d"))
GEOMETRY_TOKEN_ENV = "BYBITSCANNER_SIGNAL_GEOMETRY_TOKEN"


class WorkspaceUnavailable(RuntimeError):
    """Known fail-closed reason the owner must see in Telegram."""


def request_owner_workspace_open(mode: str, symbol: str, timeframe: str, signal_id: str | None = None) -> None:
    # Do not trust callback text as a command, path or URL.
    import re
    if mode not in ("EDITOR", "TERMINAL") or timeframe not in ALLOWED_TF:
        raise ValueError("Invalid workspace target")
    if not re.fullmatch(r"[A-Z0-9]{2,32}USDT", symbol):
        raise ValueError("Invalid workspace symbol")
    if signal_id is not None and not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", signal_id):
        raise ValueError("Invalid workspace signal identity")
    if os.name != "nt":
        raise RuntimeError("Windows owner workspace launcher only")
    if mode == "EDITOR" and signal_id is not None:
        # The launcher console closes as soon as its script fails, so a missing
        # authorization or archive must be reported here, before Telegram is
        # told that the open command was handed to the PC.
        if len(os.environ.get(GEOMETRY_TOKEN_ENV, "").strip()) < 32:
            raise WorkspaceUnavailable("signal_geometry_token_missing")
        from signal_archive import load_frozen_signal_geometry
        if load_frozen_signal_geometry(signal_id) is None:
            raise WorkspaceUnavailable("frozen_geometry_missing")
    script = REPO / "tools" / "open_signal_workspace.ps1"
    if not script.is_file():
        raise RuntimeError("Workspace launcher missing")
    # Starting a new console is intentional: owner sees URL and preparation result.
    # Use the OS executable directly: untrusted worktree files named powershell.exe
    # must not shadow the Windows system PowerShell during CreateProcess lookup.
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    powershell = system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not powershell.is_file():
        raise RuntimeError("System PowerShell executable missing")
    args = [str(powershell), "-NoProfile", "-File", str(script),
            "-Mode", mode, "-Symbol", symbol, "-Timeframe", timeframe]
    if signal_id is not None:
        args.extend(["-SignalId", signal_id])
    subprocess.Popen(
        args,
        cwd=str(REPO), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        close_fds=True,
    )
