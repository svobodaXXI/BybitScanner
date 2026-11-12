"""Fail-closed, in-memory remote locator relay for the local Machine Time utility.

The relay does not import PAPER runtime, touch database files, perform OS
operations, forward arbitrary commands, or keep episode facts. Configuration is
disabled by default. Device polls need an independent device-only secret.
"""
from __future__ import annotations

from dataclasses import dataclass
import hmac
import json
import os
import re
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit

EPISODE_ID = re.compile(r"te_[0-9a-f]{24}\Z")
DEVICE_ID = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
REQUEST_ID = re.compile(r"[0-9a-f]{32}\Z")
MAX_CONFIG_BYTES = 8192
ONLINE_SECONDS = 12
REQUEST_SECONDS = 35
STATUS_SECONDS = 90


class RelayUnavailable(ValueError):
    pass


class RelayForbidden(ValueError):
    pass


class RelayInvalid(ValueError):
    pass


def _valid_origin(value: str) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        return False
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment
                and value == f"https://{parsed.netloc}" and parsed.port != 0)
    except ValueError:
        return False


@dataclass
class _Request:
    id: str
    device_id: str
    episode_id: str
    created: float
    state: str = "QUEUED"


class SimulatorLaunchRelay:
    """Thread-safe ephemeral queue, at most one in-flight locator per device."""

    def __init__(self, *, origin: str, devices: dict[str, str],
                 clock=time.monotonic):
        if not _valid_origin(origin) or not devices or len(devices) > 4:
            raise RelayInvalid("invalid_relay_configuration")
        if any(not DEVICE_ID.fullmatch(k) or not isinstance(v, str)
               or len(v) < 48 or len(v) > 256 or v.strip() != v
               for k, v in devices.items()):
            raise RelayInvalid("invalid_relay_device_configuration")
        if len(set(devices.values())) != len(devices):
            raise RelayInvalid("shared_device_tokens_forbidden")
        self.origin = origin
        self._devices = dict(devices)
        self._clock = clock
        self._lock = Lock()
        self._last_seen: dict[str, float] = {}
        self._requests: dict[str, _Request] = {}

    @classmethod
    def from_environment(cls) -> "SimulatorLaunchRelay | None":
        origin = os.environ.get("BYBITSCANNER_SIMULATOR_BRIDGE_ORIGIN", "")
        raw = os.environ.get("BYBITSCANNER_SIMULATOR_BRIDGE_DEVICES_JSON", "")
        if not origin and not raw:
            return None
        if not raw or len(raw) > MAX_CONFIG_BYTES:
            raise RelayInvalid("simulator_bridge_configuration_unavailable")
        try:
            devices = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise RelayInvalid("simulator_bridge_configuration_invalid") from exc
        if not isinstance(devices, dict):
            raise RelayInvalid("simulator_bridge_configuration_invalid")
        return cls(origin=origin, devices=devices)

    def _authenticated(self, device: str, token: str) -> bool:
        secret = self._devices.get(device)
        return (bool(secret) and isinstance(token, str)
                and hmac.compare_digest(secret, token))

    def _trim(self, now: float) -> None:
        for key, item in list(self._requests.items()):
            if now - item.created >= REQUEST_SECONDS and item.state in {"QUEUED", "DELIVERED"}:
                item.state = "EXPIRED"
            if now - item.created >= STATUS_SECONDS:
                del self._requests[key]

    def enqueue(self, episode_id: str, *, request_origin: str, fetch_site: str) -> dict[str, str]:
        # Nginx must additionally enforce owner authentication on this POST.
        # Origin and fetch-metadata prevent cross-site form/CSRF requests.
        if (request_origin != self.origin
                or fetch_site not in {"same-origin", ""}):
            raise RelayForbidden("relay_origin_not_authorized")
        if not isinstance(episode_id, str) or not EPISODE_ID.fullmatch(episode_id):
            raise RelayInvalid("invalid_episode_locator")
        with self._lock:
            now = self._clock()
            self._trim(now)
            online = [(when, device) for device, when in self._last_seen.items()
                      if now - when <= ONLINE_SECONDS]
            if not online:
                raise RelayUnavailable("no_connected_simulator_adapter")
            # Most recently contacted paired local device; never select an
            # arbitrary host, URL, command, username or filesystem path.
            device = max(online)[1]
            if any(r.device_id == device and r.state in {"QUEUED", "DELIVERED"}
                   for r in self._requests.values()):
                raise RelayUnavailable("simulator_adapter_busy")
            rid = secrets.token_hex(16)
            self._requests[rid] = _Request(rid, device, episode_id, now)
            return {"request_id": rid, "state": "QUEUED"}

    def poll(self, *, device: str, token: str) -> dict[str, str]:
        if not self._authenticated(device, token):
            raise RelayForbidden("simulator_device_unauthorized")
        with self._lock:
            now = self._clock()
            self._trim(now)
            self._last_seen[device] = now
            queued = [r for r in self._requests.values()
                      if r.device_id == device and r.state == "QUEUED"]
            if not queued:
                return {"state": "IDLE"}
            req = min(queued, key=lambda r: r.created)
            req.state = "DELIVERED"
            return {"state": "OPEN_EPISODE", "request_id": req.id,
                    "episode_id": req.episode_id}

    def acknowledge(self, *, device: str, token: str, request_id: str,
                    launched: bool) -> dict[str, str]:
        if not self._authenticated(device, token):
            raise RelayForbidden("simulator_device_unauthorized")
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id) or type(launched) is not bool:
            raise RelayInvalid("invalid_simulator_ack")
        with self._lock:
            self._trim(self._clock())
            req = self._requests.get(request_id)
            if req is None or req.device_id != device or req.state != "DELIVERED":
                raise RelayInvalid("unknown_or_completed_launch_request")
            req.state = "LAUNCHED" if launched else "FAILED"
            return {"state": req.state}

    def status(self, request_id: str, *, request_origin: str,
               fetch_site: str) -> dict[str, str]:
        if request_origin != self.origin or fetch_site not in {"same-origin", ""}:
            raise RelayForbidden("relay_origin_not_authorized")
        if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
            raise RelayInvalid("invalid_launch_status_id")
        with self._lock:
            self._trim(self._clock())
            request = self._requests.get(request_id)
            if request is None:
                raise RelayInvalid("launch_request_not_found")
            return {"request_id": request_id, "state": request.state}
