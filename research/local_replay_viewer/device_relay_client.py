"""Opt-in, outbound-only PAPER evidence receiver for one paired local viewer.

Requires an explicitly pinned HTTPS owner origin and independent device token.
The token has no exchange/order privilege. No remote URLs, trading actions,
shell commands, or database accesses are accepted from a relay message.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import threading
import time
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request

from research.local_replay_viewer.paper_episode_local_store import (
    MAX_BYTES, load_episode, store_episode,
)

EPISODE_ID = re.compile(r"te_[a-f0-9]{24}\Z")
DEVICE_ID = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
REQUEST_ID = re.compile(r"[a-f0-9]{32}\Z")


class _DenyRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def valid_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (parsed.scheme == "https" and bool(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment
                and value == "https://" + parsed.netloc and parsed.port != 0)
    except (ValueError, TypeError):
        return False


class PairedEpisodeReceiver:
    def __init__(self, *, origin: str, device_id: str, token: str,
                 local_archive: Path, open_episode: Callable[[str], bool],
                 transport=None):
        if (not valid_origin(origin) or not DEVICE_ID.fullmatch(device_id)
                or not isinstance(token, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{48,256}", token)):
            raise ValueError("untrusted_simulator_device_configuration")
        self.origin = origin
        self.device_id = device_id
        self.token = token
        self.archive = local_archive
        self.open_episode = open_episode
        self.transport = transport or build_opener(_DenyRedirects())

    def _request(self, path: str, body: dict | None = None) -> dict:
        raw = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request = Request(
            self.origin + path,
            data=raw,
            headers={
                "X-BybitScanner-Simulator-Device-Token": self.token,
                "Cache-Control": "no-store",
                **({"Content-Type": "application/json"} if raw is not None else {}),
            },
            method="POST" if raw is not None else "GET",
        )
        with self.transport.open(request, timeout=8) as response:
            if response.status != 200:
                raise ValueError("bridge_unavailable")
            binary = response.read(MAX_BYTES + 8192)
            if len(binary) > MAX_BYTES + 8191:
                raise ValueError("relay_response_too_large")
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                raise ValueError("relay_not_json")
        result = json.loads(binary)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise ValueError("invalid_relay_response")
        return result

    def poll_once(self) -> str:
        data = self._request("/api/diary/simulator-bridge/poll?" +
            urlencode({"device_id": self.device_id, "viewer_running": "1"}))
        if data.get("state") == "IDLE":
            return "IDLE"
        if (data.get("state") != "OPEN_EPISODE"
                or not isinstance(data.get("episode_id"), str)
                or not EPISODE_ID.fullmatch(data["episode_id"])
                or not isinstance(data.get("request_id"), str)
                or not REQUEST_ID.fullmatch(data["request_id"])):
            raise ValueError("invalid_relay_event")
        episode_id = data["episode_id"]
        request_id = data["request_id"]
        success = False
        try:
            payload = data.get("episode_facts")
            if payload is not None:
                if (not isinstance(payload, dict) or payload.get("trade_episode_id") != episode_id
                        or payload.get("account_id") != "paper"
                        or payload.get("namespace") != "PAPER_READ_ONLY"
                        or payload.get("owner") not in {"ROBOT", "MANUAL"}):
                    raise ValueError("cross_account_relay_evidence")
                raw = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
                if len(raw) > MAX_BYTES:
                    raise ValueError("relay_evidence_too_large")
                stored = store_episode(self.archive, raw)
                if stored != episode_id:
                    raise ValueError("local_relay_episode_mismatch")
            elif load_episode(self.archive, episode_id) is None:
                raise ValueError("no_verified_paper_evidence")
            # Only a local read-only viewer URL containing an exact ID is opened.
            success = self.open_episode(episode_id) is True
        finally:
            # A false ACK communicates a failed local import/open. No silent
            # fallback to a simulated or foreign account episode.
            ack = self._request("/api/diary/simulator-bridge/ack", {
                "device_id": self.device_id, "request_id": request_id,
                "launched": success,
            })
            if ack.get("state") != ("LAUNCHED" if success else "FAILED"):
                raise ValueError("invalid_simulator_bridge_ack")
        return "LAUNCHED" if success else "FAILED"

    def loop(self, stop: threading.Event, *, poll_interval: float = 3.0) -> None:
        """No remote state changes; independent of Scanner/Robot runtime."""
        while not stop.is_set():
            try:
                self.poll_once()
            except (OSError, ValueError, HTTPError, TimeoutError,
                    UnicodeError, json.JSONDecodeError):
                # Keep device ready for later owner requests. Fail closed on
                # this event; never silently manufacture missing data.
                pass
            stop.wait(poll_interval)
