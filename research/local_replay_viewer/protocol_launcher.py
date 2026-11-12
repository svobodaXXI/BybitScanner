"""Owner-only Windows URI adapter: open the existing local Machine Time viewer.

The HTTPS Statistics UI may REQUEST launching this registered application from
a direct user click. This protocol never accepts commands, file paths, hosts,
account data, credentials, or PAPER fills. It only accepts a typed episode ID.
The browser's existing nonce + exact-origin handshake owns fact transfer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import webbrowser
from urllib.parse import parse_qs, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

SCHEME = "bybitscanner-simulator"
PORT = 48765
HERE = Path(__file__).resolve().parent
EPISODE_RE = re.compile(r"te_[0-9a-f]{24}\Z")


def parse_open_uri(value: str) -> str:
    """Permit only bybitscanner-simulator://open?episode=te_<24hex>."""
    if not isinstance(value, str) or len(value) > 160:
        raise ValueError("invalid simulator link length")
    url = urlsplit(value)
    if (url.scheme != SCHEME or url.netloc != "open" or url.path
            or url.fragment or not url.query or url.username is not None
            or url.password is not None):
        raise ValueError("unsupported simulator link")
    params = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
    if set(params) != {"episode"} or len(params["episode"]) != 1:
        raise ValueError("simulator link must have one episode ID")
    episode_id = params["episode"][0]
    if not EPISODE_RE.fullmatch(episode_id):
        raise ValueError("invalid episode ID")
    return episode_id


def register_windows_protocol() -> None:
    """Per-user HKCU registration only. No administrator or system changes."""
    if os.name != "nt":
        raise OSError("Windows protocol registration is supported only on Windows")
    import winreg

    executable = str(Path(sys.executable).resolve())
    script = str(Path(__file__).resolve())
    # Both paths originate from this local installation, not the URI.
    command = f'"{executable}" -B "{script}" "%1"'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{SCHEME}") as root:
        winreg.SetValueEx(root, "", 0, winreg.REG_SZ, "URL:BybitScanner Simulator")
        winreg.SetValueEx(root, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          rf"Software\Classes\{SCHEME}\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def viewer_is_running() -> bool:
    """Probe fixed loopback only; never access an arbitrary user-supplied URL."""
    try:
        opener = build_opener(ProxyHandler({}))
        request = Request(f"http://127.0.0.1:{PORT}/local-replay/simulation/status")
        with opener.open(request, timeout=0.4) as response:
            if response.status != 200:
                return False
            raw = response.read(4096)
        return json.loads(raw).get("namespace") == "SIMULATION"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def launch_local_viewer(episode_id: str) -> None:
    if not EPISODE_RE.fullmatch(episode_id):
        raise ValueError("invalid episode ID")
    if os.name != "nt":
        raise OSError("Windows-only local launch")
    if not viewer_is_running():
        server = HERE / "server.py"
        if not server.is_file() or server.is_symlink():
            raise OSError("local simulator server missing")
        # Explicit argv; no shell, no remote command interpreter or VPS access.
        subprocess.Popen(
            [sys.executable, "-B", str(server), "--no-browser"],
            cwd=str(HERE), stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
            close_fds=True,
        )
        for _ in range(24):
            if viewer_is_running():
                break
            time.sleep(0.25)
        else:
            raise OSError("local simulator did not become available")
    # Locator only. Never place PAPER fills or original decisions in the URL.
    webbrowser.open(f"http://127.0.0.1:{PORT}/replay.html#locator={episode_id}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--register"]:
        try:
            register_windows_protocol()
            return 0
        except OSError:
            return 2
    if len(args) != 1:
        return 2
    try:
        episode = parse_open_uri(args[0])
        launch_local_viewer(episode)
        return 0
    except (OSError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
