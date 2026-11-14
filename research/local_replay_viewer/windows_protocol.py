"""Optional per-user Windows filmstrip launcher for the LOCAL read-only viewer.

The URL transports a typed trade episode ID only. It does not fetch, sync, or
authorize PAPER evidence and never reaches private exchange/Robot APIs.
No system-wide registry or administrator access is required.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
from urllib.request import urlopen

SCHEME = "bybitscanner-simulator"
URI = re.compile(r"bybitscanner-simulator://open\?episode=(te_[a-f0-9]{24})\Z")
CLASSES_KEY = r"Software\Classes\bybitscanner-simulator"
APP_KEY = r"Software\BybitScanner\MachineTime"


def episode_from_url(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) > 130:
        raise ValueError("invalid_simulator_uri")
    matched = URI.fullmatch(raw)
    if not matched:
        raise ValueError("invalid_simulator_uri")
    return matched.group(1)


def _registry():
    if os.name != "nt":
        return None
    import winreg
    return winreg


def install_per_user_handler(script: Path, python: Path) -> bool:
    """Register only HKCU URI dispatch, not machine-wide associations."""
    registry = _registry()
    if registry is None:
        return False
    script, python = script.resolve(), python.resolve()
    if not script.is_file() or not python.is_file():
        raise ValueError("missing_simulator_handler_binary")
    with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, CLASSES_KEY) as key:
        registry.SetValueEx(key, "", 0, registry.REG_SZ, "BybitScanner Machine Time (local)")
        registry.SetValueEx(key, "URL Protocol", 0, registry.REG_SZ, "")
    with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, CLASSES_KEY + r"\shell\open\command") as key:
        registry.SetValueEx(
            key, "", 0, registry.REG_SZ,
            f'"{python}" -B "{script}" --open-url "%1"',
        )
    return True


def set_active_viewer(script: Path, port: int) -> None:
    registry = _registry()
    if registry is None:
        return
    if not 1 <= port <= 65535:
        raise ValueError("invalid_local_viewer_port")
    with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, APP_KEY) as key:
        registry.SetValueEx(key, "Script", 0, registry.REG_SZ, str(script.resolve()))
        registry.SetValueEx(key, "Port", 0, registry.REG_DWORD, port)


def active_viewer_port(script: Path) -> int | None:
    registry = _registry()
    if registry is None:
        return None
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, APP_KEY) as key:
            expected = registry.QueryValueEx(key, "Script")[0]
            port = registry.QueryValueEx(key, "Port")[0]
        if expected != str(script.resolve()) or type(port) is not int or not 1 <= port <= 65535:
            return None
        # Explicit loopback health, never use a configurable origin/hostname.
        with urlopen(f"http://127.0.0.1:{port}/replay.html", timeout=1.0) as response:
            if response.status != 200 or not response.headers.get("Server", "").startswith("MachineTimeLocal/"):
                return None
        return port
    except (OSError, ValueError, KeyError, TimeoutError):
        return None


def clear_active_viewer(script: Path, port: int) -> None:
    registry = _registry()
    if registry is None:
        return
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, APP_KEY, 0, registry.KEY_READ | registry.KEY_WRITE) as key:
            if (registry.QueryValueEx(key, "Script")[0] == str(script.resolve())
                and registry.QueryValueEx(key, "Port")[0] == port):
                registry.DeleteValue(key, "Script")
                registry.DeleteValue(key, "Port")
    except OSError:
        pass
