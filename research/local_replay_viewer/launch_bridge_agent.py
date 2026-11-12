"""Optional paired Windows agent for one fixed local Machine Time utility.

No token or pairing config is shipped in the Windows package. The agent starts
only after a locally created, exact HTTPS/device-token configuration exists.
It never opens inbound ports, asks for VPS operator/PAPER credentials, or runs
shell commands received from the network.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__:
    from .protocol_launcher import HERE, EPISODE_RE, launch_local_viewer, viewer_is_running
else:
    from protocol_launcher import HERE, EPISODE_RE, launch_local_viewer, viewer_is_running

CONFIG_PATH = HERE / "simulator-v2-data" / "launch-bridge.json"
DEVICE_RE = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
REQUEST_RE = re.compile(r"[0-9a-f]{32}\Z")
SCHEMA = "BYBITSCANNER_SIMULATOR_LAUNCH_DEVICE_V1"
AGENT_RUN_NAME = "BybitScannerMachineTimeLaunchAdapter"
POLL_SECONDS = 3


class AgentConfigError(ValueError):
    pass


def read_config(path: Path = CONFIG_PATH) -> dict[str, str] | None:
    if not path.exists():
        return None
    if path.is_symlink() or path.parent.is_symlink() or not path.is_file():
        raise AgentConfigError("untrusted_device_config_path")
    try:
        with path.open("rb") as f:
            payload = f.read(1100)
        if not payload or len(payload) > 1024:
            raise AgentConfigError("invalid_device_config_size")
        doc = json.loads(payload.decode("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise AgentConfigError("invalid_device_config") from exc
    if not isinstance(doc, dict) or set(doc) != {"schema", "origin", "device_id", "token"}:
        raise AgentConfigError("invalid_device_config_schema")
    origin, device, token = doc.get("origin"), doc.get("device_id"), doc.get("token")
    if (doc.get("schema") != SCHEMA or not isinstance(origin, str)
            or not isinstance(device, str) or not DEVICE_RE.fullmatch(device)
            or not isinstance(token, str) or not 48 <= len(token) <= 256
            or token.strip() != token):
        raise AgentConfigError("invalid_device_pairing")
    try:
        parsed = urlsplit(origin)
        valid_origin = (parsed.scheme == "https" and bool(parsed.hostname)
                        and parsed.username is None and parsed.password is None
                        and not parsed.path and not parsed.query and not parsed.fragment
                        and origin == f"https://{parsed.netloc}" and parsed.port != 0)
    except ValueError:
        valid_origin = False
    if not valid_origin:
        raise AgentConfigError("invalid_device_origin")
    return {"origin": origin, "device_id": device, "token": token}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _send(config: dict[str, str], *, path: str, body: dict | None = None,
          opener=None) -> dict:
    client = opener or build_opener(_NoRedirect())
    headers = {
        "X-BybitScanner-Simulator-Device-Token": config["token"],
        "Cache-Control": "no-store",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = Request(
        config["origin"] + path,
        data=(json.dumps(body, separators=(",", ":")).encode("utf-8")
              if body is not None else None),
        headers=headers,
    )
    with client.open(request, timeout=5) as response:
        if response.status != 200:
            raise URLError("simulator_bridge_http_not_ok")
        data = response.read(1025)
    if len(data) > 1024:
        raise AgentConfigError("simulator_bridge_reply_too_large")
    decoded = json.loads(data.decode("utf-8"))
    if not isinstance(decoded, dict) or decoded.get("ok") is not True:
        raise AgentConfigError("invalid_simulator_bridge_reply")
    return decoded


def poll_once(config: dict[str, str], *, opener=None, launch=launch_local_viewer) -> str:
    """One bounded outbound poll, at most one local open, one ACK."""
    # Only an authenticated boolean heartbeat is sent. Never disclose
    # Windows process details, private network addresses or trading data.
    viewer_running = viewer_is_running()
    uri = ("/api/diary/simulator-bridge/poll?"
           + urlencode({"device_id": config["device_id"],
                        "viewer_running": "1" if viewer_running else "0"}))
    response = _send(config, path=uri, opener=opener)
    if response.get("state") == "IDLE":
        if set(response) != {"ok", "state"}:
            raise AgentConfigError("unexpected_idle_reply")
        return "IDLE"
    episode = response.get("episode_id")
    request_id = response.get("request_id")
    if (response.get("state") != "OPEN_EPISODE"
            or set(response) != {"ok", "state", "episode_id", "request_id"}
            or not isinstance(episode, str) or not EPISODE_RE.fullmatch(episode)
            or not isinstance(request_id, str) or not REQUEST_RE.fullmatch(request_id)):
        raise AgentConfigError("untrusted_launch_instruction")
    opened = False
    try:
        launch(episode)
        opened = True
    except (OSError, ValueError):
        pass
    # ACK never contains a file, command, URL, credentials or PAPER data.
    ack = _send(config, path="/api/diary/simulator-bridge/ack", body={
        "device_id": config["device_id"], "request_id": request_id,
        "launched": opened,
    }, opener=opener)
    if (set(ack) != {"ok", "state"}
            or ack["state"] != ("LAUNCHED" if opened else "FAILED")):
        raise AgentConfigError("simulator_bridge_ack_unproven")
    return "OPEN_REQUESTED" if opened else "OPEN_FAILED"


def _acquire_windows_singleton():
    if os.name != "nt":
        raise OSError("Windows_only")
    # One lightweight adapter per interactive Windows session; never stop or
    # replace unrelated processes. Hold the handle until process exit.
    handle = ctypes.windll.kernel32.CreateMutexW(
        None, False, r"Local\BybitScannerMachineTimeLaunchAdapter"
    )
    if not handle:
        raise OSError("local_simulator_mutex_unavailable")
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.kernel32.CloseHandle(handle)
        return None
    return handle


def install_if_configured() -> bool:
    """Owner's START_LOCAL.cmd opts in only if a paired local config exists."""
    config = read_config()
    if config is None:
        return False
    if os.name != "nt":
        raise OSError("Windows_only")
    import winreg

    path = Path(__file__).resolve()
    candidate = Path(sys.executable).with_name("pythonw.exe")
    executable = candidate if candidate.is_file() else Path(sys.executable).resolve()
    # Known installed script only; no arguments from a remote URL.
    command = f'"{executable}" -B "{path}" --poll'
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER,
                          r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        winreg.SetValueEx(key, AGENT_RUN_NAME, 0, winreg.REG_SZ, command)
    subprocess.Popen(
        [str(executable), "-B", str(path), "--poll"],
        cwd=str(HERE), stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    return True


def run_poll_loop(config: dict[str, str]) -> None:
    mutex = _acquire_windows_singleton()
    if mutex is None:
        return
    try:
        while True:
            try:
                poll_once(config)
            except HTTPError as error:
                if error.code in {401, 403, 404}:
                    # Missing public relay routing or revoked pairing: stop.
                    return
            except (AgentConfigError, URLError, OSError, ValueError):
                # Network outage never launches anything. Small idle wake-ups.
                pass
            time.sleep(POLL_SECONDS)
    finally:
        ctypes.windll.kernel32.CloseHandle(mutex)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paired local SIMULATION launcher only")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--install-if-configured", action="store_true")
    mode.add_argument("--poll", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.install_if_configured:
            install_if_configured()
        else:
            config = read_config()
            if config is None:
                return 2
            run_poll_loop(config)
        return 0
    except (AgentConfigError, OSError, ValueError):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
