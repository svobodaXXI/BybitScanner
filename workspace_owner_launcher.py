"""Owner-PC handoff for Telegram workspace requests; no trading runtime starts."""
import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent
ALLOWED_TF = frozenset(("15s", "1m", "5m", "15m", "1h", "1d"))


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
    script = REPO / "tools" / "open_signal_workspace.ps1"
    if not script.is_file():
        raise RuntimeError("Workspace launcher missing")
    # Starting a new console is intentional: owner sees URL and preparation result.
    args = ["powershell.exe", "-NoProfile", "-File", str(script),
            "-Mode", mode, "-Symbol", symbol, "-Timeframe", timeframe]
    if signal_id is not None:
        args.extend(["-SignalId", signal_id])
    subprocess.Popen(
        args,
        cwd=str(REPO), creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0),
        close_fds=True,
    )
