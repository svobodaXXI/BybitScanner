"""Optional paired Windows agent for one fixed local Machine Time utility.

No token or pairing config is shipped in the Windows package. The agent starts
only after a locally created, exact HTTPS/device-token configuration exists.
It never opens inbound ports, asks for VPS operator/PAPER credentials, or runs
shell commands received from the network.
"""
from __future__ import annotations

import argparse
import base64
import io
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
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

if __package__:
    from .protocol_launcher import HERE, EPISODE_RE, launch_local_viewer, viewer_is_running
else:
    from protocol_launcher import HERE, EPISODE_RE, launch_local_viewer, viewer_is_running

def _installed_releases(here: Path) -> Path | None:
    """Recognize only the per-user installed desktop layout, not source trees."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return None
    releases = Path(local).resolve() / "BybitScanner" / "MachineTime" / "releases"
    sha = here.parent.name
    marker = here / "desktop-build-sha.txt"
    if (here.name == "MachineTime" and here.parent.parent == releases
            and not any(p.is_symlink() for p in (releases, releases.parent, here.parent, here))
            and re.fullmatch(r"[0-9a-f]{40}", sha)
            and marker.is_file() and not marker.is_symlink()
            and marker.stat().st_size <= 64
            and marker.read_text(encoding="ascii").strip() == sha):
        return releases
    return None


def _config_path(here: Path) -> Path:
    releases = _installed_releases(here)
    root = releases.parent if releases is not None else here
    return root / "simulator-v2-data" / "launch-bridge.json"


CONFIG_PATH = _config_path(HERE)
DEVICE_RE = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
REQUEST_RE = re.compile(r"[0-9a-f]{32}\Z")
SCHEMA = "BYBITSCANNER_SIMULATOR_LAUNCH_DEVICE_V1"
AGENT_RUN_NAME = "BybitScannerMachineTimeLaunchAdapter"
POLL_SECONDS = 3


class AgentConfigError(ValueError):
    pass


def read_config(path: Path | None = None) -> dict[str, str] | None:
    if path is None:
        path = CONFIG_PATH
        if not path.exists() and not path.is_symlink():
            _recover_installed_pairing(path)
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


def _recover_installed_pairing(path: Path) -> None:
    """Copy one unambiguous existing pairing; never re-pair or replace a token."""
    releases = _installed_releases(HERE)
    if releases is None or path != _config_path(HERE):
        return
    if path.parent.is_symlink() or path.is_symlink():
        raise AgentConfigError("untrusted_device_config_path")
    candidate = None
    for version in sorted(releases.iterdir()):
        app = version / "MachineTime"
        if version.is_symlink() or app.is_symlink() or not app.is_dir():
            continue
        if _installed_releases(app) != releases:
            continue
        existing = read_config(app / "simulator-v2-data" / "launch-bridge.json")
        if existing is None:
            continue
        if candidate is not None and existing != candidate:
            raise AgentConfigError("conflicting_legacy_pairings")
        candidate = existing
    if candidate is None:
        return
    if candidate["origin"] != _trusted_statistics_origin():
        raise AgentConfigError("legacy_pairing_origin_mismatch")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise AgentConfigError("untrusted_device_config_path")
    raw = json.dumps({"schema": SCHEMA, **candidate}, separators=(",", ":")).encode("utf-8")
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if read_config(path) != candidate:
            raise AgentConfigError("existing_device_pairing_preserved")
        return
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _direct_https_opener():
    """Explicit direct transport for isolated loopback diagnostics."""
    return build_opener(ProxyHandler({}), _NoRedirect())


# Fixed script: request data and secrets enter only through the child's stdin.
# Use the same native .NET HTTPS stack already used for public candle history.
_WINDOWS_RELAY_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$inputDoc = [Console]::In.ReadToEnd() | ConvertFrom-Json
$request = [Net.HttpWebRequest]::Create([string]$inputDoc.url)
$request.Method = [string]$inputDoc.method
$request.AllowAutoRedirect = $false
$request.Timeout = [int]$inputDoc.timeout_ms
$request.ReadWriteTimeout = [int]$inputDoc.timeout_ms
$request.UseDefaultCredentials = $false
$request.PreAuthenticate = $false
foreach ($header in $inputDoc.headers.PSObject.Properties) {
    if ($header.Name -eq 'content-type') {
        $request.ContentType = [string]$header.Value
    } else {
        $request.Headers[$header.Name] = [string]$header.Value
    }
}
try {
    if ($request.Method -eq 'POST') {
        $body = [Convert]::FromBase64String([string]$inputDoc.body)
        $request.ContentLength = $body.Length
        $stream = $request.GetRequestStream()
        try { $stream.Write($body, 0, $body.Length) } finally { $stream.Dispose() }
    }
    $response = $request.GetResponse()
} catch {
    $errorCause = $_.Exception.GetBaseException()
    if ($errorCause -is [Net.WebException] -and $null -ne $errorCause.Response) {
        $response = $errorCause.Response
    } else {
        exit 3
    }
}
try {
    $stream = $response.GetResponseStream()
    $buffer = New-Object byte[] 65536
    $result = New-Object IO.MemoryStream
    try {
        while (($n = $stream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            if ($result.Length + $n -gt [int]$inputDoc.max_bytes) { exit 4 }
            $result.Write($buffer, 0, $n)
        }
        $reply = @{ status = [int]$response.StatusCode; body = [Convert]::ToBase64String($result.ToArray()) }
        [Console]::Write(($reply | ConvertTo-Json -Compress))
    } finally {
        $result.Dispose()
        $stream.Dispose()
    }
} finally { $response.Dispose() }
"""


class _WindowsRelayOpener:
    def open(self, request, timeout):
        parsed = urlsplit(request.full_url)
        routes = {
            "/api/diary/simulator-bridge/pair-claim": "POST",
            "/api/diary/simulator-bridge/poll": "GET",
            "/api/diary/simulator-bridge/facts": "GET",
            "/api/diary/simulator-bridge/ack": "POST",
        }
        method = request.get_method()
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.fragment
                or routes.get(parsed.path) != method
                or (method == "POST" and parsed.query)):
            raise AgentConfigError("invalid_windows_relay_request")
        headers = {k.lower(): v for k, v in request.header_items()}
        if not set(headers) <= {"content-type", "cache-control",
                               "x-bybitscanner-simulator-device-token",
                               "x-bybitscanner-local-pair-claim"}:
            raise AgentConfigError("invalid_windows_relay_headers")
        body = request.data or b""
        if not isinstance(body, bytes) or len(body) > 320 or (method == "GET" and body):
            raise AgentConfigError("invalid_windows_relay_body")
        if parsed.path.endswith("/facts"):
            from research.local_replay_viewer.paper_episode_local_store import MAX_BYTES
            limit = MAX_BYTES + 1
        else:
            limit = 1025
        # Match the proven native Windows timeout; one attempt only.
        seconds = max(12, timeout)
        payload = json.dumps({
            "url": request.full_url, "method": method, "headers": headers,
            "body": base64.b64encode(body).decode("ascii"),
            "timeout_ms": int(seconds * 1000), "max_bytes": limit,
        }, separators=(",", ":")).encode("ascii")
        shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        encoded = base64.b64encode(_WINDOWS_RELAY_SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            result = subprocess.run(
                [str(shell), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                input=payload, capture_output=True, timeout=seconds + 8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired):
            raise URLError("windows_relay_transport_failed") from None
        if result.returncode == 4:
            raise AgentConfigError("windows_relay_reply_too_large")
        if result.returncode != 0:
            raise URLError("windows_relay_transport_failed")
        try:
            if len(result.stdout) > ((limit + 2) // 3) * 4 + 128:
                raise ValueError("oversized")
            reply = json.loads(result.stdout)
            if set(reply) != {"status", "body"} or type(reply["status"]) is not int:
                raise ValueError("invalid response")
            status = reply["status"]
            if not 100 <= status <= 599:
                raise ValueError("invalid status")
            data = base64.b64decode(reply["body"], validate=True)
            if len(data) > limit:
                raise ValueError("oversized")
        except (ValueError, TypeError, KeyError):
            raise AgentConfigError("invalid_windows_relay_reply") from None
        response = io.BytesIO(data)
        response.status = status
        if status != 200:
            raise HTTPError(request.full_url, status, "windows_relay_http_rejected", {}, response)
        return response


def _relay_https_opener():
    """One configured route; no automatic replay of a consumed claim."""
    if os.name == "nt":
        return _WindowsRelayOpener()
    return build_opener(ProxyHandler(), _NoRedirect())


def _send(config: dict[str, str], *, path: str, body: dict | None = None,
          opener=None) -> dict:
    client = opener or _relay_https_opener()
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


def _verified_facts(config: dict[str, str], *, request_id: str, episode_id: str,
                    owner: str, revision: int, opener=None) -> bytes:
    """Fetch only the owner-queued, device-bound episode; never an arbitrary API URL."""
    from research.local_replay_viewer.paper_episode_local_store import MAX_BYTES
    client = opener or _relay_https_opener()
    request = Request(
        config["origin"] + "/api/diary/simulator-bridge/facts?" + urlencode({
            "device_id": config["device_id"], "request_id": request_id,
        }),
        headers={
            "X-BybitScanner-Simulator-Device-Token": config["token"],
            "Cache-Control": "no-store",
        },
    )
    with client.open(request, timeout=10) as response:
        if response.status != 200:
            raise AgentConfigError("episode_facts_http_not_ok")
        raw = response.read(MAX_BYTES + 1)
    if not 2 <= len(raw) <= MAX_BYTES:
        raise AgentConfigError("invalid_episode_facts_size")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as exc:
        raise AgentConfigError("invalid_episode_facts_json") from exc
    if (not isinstance(payload, dict) or payload.get("ok") is not True
            or payload.get("trade_episode_id") != episode_id
            or payload.get("owner") != owner
            or payload.get("source_revision") != revision
            or payload.get("account_id") != "paper"
            or payload.get("namespace") != "PAPER_READ_ONLY"
            or payload.get("schema") != "BYBITSCANNER_CLOSED_EPISODE_FACTS_V1"
            or payload.get("source") != "PAPER_EXECUTIONS_ATTRIBUTED"
            or payload.get("replay_evidence")
               != "EXECUTION_FACTS_ONLY_NO_DECISIONS_OR_CANDLES"):
        raise AgentConfigError("episode_facts_scope_mismatch")
    return raw


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
    scoped = "owner" in response or "source_revision" in response
    expected_fields = {"ok", "state", "episode_id", "request_id"}
    if scoped:
        expected_fields |= {"owner", "source_revision"}
    if (response.get("state") != "OPEN_EPISODE"
            or set(response) != expected_fields
            or not isinstance(episode, str) or not EPISODE_RE.fullmatch(episode)
            or not isinstance(request_id, str) or not REQUEST_RE.fullmatch(request_id)
            or (scoped and (
                response.get("owner") not in {"ROBOT", "MANUAL"}
                or type(response.get("source_revision")) is not int
                or response["source_revision"] < 1
            ))):
        raise AgentConfigError("untrusted_launch_instruction")
    opened = False
    try:
        if scoped:
            from research.local_replay_viewer.paper_episode_local_store import store_episode, release_archive_root
            raw = _verified_facts(
                config, request_id=request_id, episode_id=episode,
                owner=response["owner"], revision=response["source_revision"],
                opener=opener,
            )
            stored = store_episode(release_archive_root(HERE), raw)
            if stored != episode:
                raise AgentConfigError("local_episode_identity_mismatch")
        launch(episode)
        opened = True
    except (OSError, ValueError, URLError):
        # No FACTS_SYNCED/LAUNCHED success on failed read, mismatch or conflict.
        pass
    # ACK contains no PAPER data, financial values or device secrets.
    ack = _send(config, path="/api/diary/simulator-bridge/ack", body={
        "device_id": config["device_id"], "request_id": request_id,
        "launched": opened,
    }, opener=opener)
    if (set(ack) != {"ok", "state"}
            or ack["state"] != ("LAUNCHED" if opened else "FAILED")):
        raise AgentConfigError("simulator_bridge_ack_unproven")
    return "OPEN_REQUESTED" if opened else "OPEN_FAILED"


def _trusted_statistics_origin() -> str:
    """Reuse the local owner's existing handoff trust anchor, never the URI."""
    data_dir = CONFIG_PATH.parent
    pinned = data_dir / "trusted-statistics-origin.txt"
    if data_dir.is_symlink() or pinned.is_symlink():
        raise AgentConfigError("trusted_statistics_origin_not_installed")
    if not pinned.is_file():
        # A verified Machine Time release carries a *separate, non-secret*
        # reviewed HTTPS trust anchor. Never take the origin from a browser,
        # device token, redirect or protocol URI. Existing owner pin wins.
        pinned = HERE / "trusted-statistics-origin.txt"
        if pinned.is_symlink() or not pinned.is_file():
            raise AgentConfigError("trusted_statistics_origin_not_installed")
    try:
        with pinned.open("rb") as stream:
            raw = stream.read(258)
        if not raw or len(raw) > 257:
            raise AgentConfigError("invalid_trusted_statistics_origin")
        origin = raw.decode("ascii").removesuffix("\n")
        parsed = urlsplit(origin)
        if (not origin or len(origin) > 256 or origin.strip() != origin
                or any(c in origin for c in ("*", "\\", "\r", "\n"))
                or parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path or parsed.query or parsed.fragment
                or origin != f"https://{parsed.netloc}"
                or (parsed.port is not None and not 1 <= parsed.port <= 65535)):
            raise AgentConfigError("invalid_trusted_statistics_origin")
        return origin
    except (OSError, UnicodeError, ValueError) as exc:
        raise AgentConfigError("invalid_trusted_statistics_origin") from exc


def claim_one_time_pairing_code(device_id: str, code: str, *, opener=None) -> None:
    """Redeem an owner-authenticated one-time code directly over pinned TLS.

    The reusable device token is received only by this local Python adapter,
    never by Telegram frontend, local browser JS, a URL or the clipboard.
    """
    if not isinstance(device_id, str) or not DEVICE_RE.fullmatch(device_id):
        raise AgentConfigError("invalid_pairing_device")
    if not isinstance(code, str) or not re.fullmatch(r"[A-Z2-7]{24}\Z", code):
        raise AgentConfigError("invalid_one_time_pair_code")
    if read_config() is not None:
        raise AgentConfigError("existing_device_pairing_preserved")
    origin = _trusted_statistics_origin()
    request = Request(
        origin + "/api/diary/simulator-bridge/pair-claim",
        data=json.dumps({"device_id": device_id, "code": code},
                        separators=(",", ":")).encode("ascii"),
        headers={
            "Content-Type": "application/json",
            "X-BybitScanner-Local-Pair-Claim": "v1",
            "Cache-Control": "no-store",
        },
        method="POST",
    )
    client = opener or _relay_https_opener()
    with client.open(request, timeout=5) as response:
        if response.status != 200:
            raise AgentConfigError("pair_code_claim_http_not_ok")
        raw = response.read(1025)
    if len(raw) > 1024:
        raise AgentConfigError("pair_claim_response_too_large")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise AgentConfigError("invalid_pair_claim_response") from exc
    if (not isinstance(result, dict) or set(result) !=
            {"ok", "device_id", "token"} or result["ok"] is not True
            or result["device_id"] != device_id
            or not isinstance(result["token"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{48,256}\Z", result["token"])):
        raise AgentConfigError("invalid_pair_claim_response")
    pair_device(device_id, result["token"])


def pair_device(device_id: str, token: str) -> None:
    """One-shot opt-in; no new service, no shell, no untrusted destination.

    Device secret is supplied only by the authenticated Statistics owner UI.
    A verified 200/IDLE reply from the already pinned origin is mandatory
    before saving anything. Existing configurations are never overwritten.
    """
    if not DEVICE_RE.fullmatch(device_id) or not isinstance(token, str):
        raise AgentConfigError("invalid_device_pairing_identity")
    if not 48 <= len(token) <= 256 or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise AgentConfigError("invalid_device_pairing_token")
    origin = _trusted_statistics_origin()
    config = {"origin": origin, "device_id": device_id, "token": token}
    current = read_config()
    if current is not None:
        if current != config:
            raise AgentConfigError("existing_device_pairing_preserved")
        # Idempotent: a re-open cannot rewrite an existing owner secret.
        install_if_configured()
        return
    path = CONFIG_PATH
    if path.is_symlink() or path.parent.is_symlink():
        raise AgentConfigError("untrusted_device_config_path")
    proof = _send(config, path="/api/diary/simulator-bridge/poll?" + urlencode({
        "device_id": device_id, "viewer_running": "0",
    }))
    if set(proof) != {"ok", "state"} or proof["state"] != "IDLE":
        raise AgentConfigError("device_pairing_not_verified")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink():
        raise AgentConfigError("untrusted_device_config_path")
    content = json.dumps({"schema": SCHEMA, **config}, separators=(",", ":")).encode("utf-8")
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise AgentConfigError("existing_device_pairing_preserved") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)
    install_if_configured()


def _poll_executable() -> Path:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return candidate if candidate.is_file() else Path(sys.executable).resolve()


def _expected_autostart_command() -> str:
    """Canonical per-user Windows Run entry for THIS installed release."""
    return f'"{_poll_executable()}" -B "{HERE / "launch_bridge_agent.py"}" --poll'


def _this_release_still_registered() -> bool:
    """Old release retires voluntarily when START_LOCAL registers a successor."""
    if os.name != "nt":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            value, kind = winreg.QueryValueEx(key, AGENT_RUN_NAME)
        return kind == winreg.REG_SZ and value == _expected_autostart_command()
    except OSError:
        return False  # Never poll or launch when local ownership is unproven.


def _acquire_windows_singleton():
    if os.name != "nt":
        raise OSError("Windows_only")
    # Wait only for the existing same-product agent to release its handle.
    # The old version checks the Run registration and exits on supersession.
    # No process is killed, no file deleted, and no second poller may run.
    for attempt in range(31):
        handle = ctypes.windll.kernel32.CreateMutexW(
            None, False, r"Local\BybitScannerMachineTimeLaunchAdapter"
        )
        if not handle:
            raise OSError("local_simulator_mutex_unavailable")
        if ctypes.windll.kernel32.GetLastError() != 183:
            return handle
        ctypes.windll.kernel32.CloseHandle(handle)
        if attempt < 30:
            time.sleep(POLL_SECONDS)
    return None


def install_if_configured() -> bool:
    """Owner's START_LOCAL.cmd opts in only if a paired local config exists."""
    config = read_config()
    if config is None:
        return False
    if os.name != "nt":
        raise OSError("Windows_only")
    import winreg

    # Known installed script only; no arguments from a remote URL.
    command = _expected_autostart_command()
    executable = _poll_executable()
    path = HERE / "launch_bridge_agent.py"
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
        while _this_release_still_registered():
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
