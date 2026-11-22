"""Offline durable diagnostic receipts; no service, network or trading DB.

The caller must supply a dedicated, owner-protected directory on a local
filesystem supporting flock, atomic rename and fsync. Never auto-initialize
an absent journal during processing. No retention/deletion in this slice.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat

from tools import github_diagnostic_protocol as protocol
from tools.github_status_reporter import _save

MAX_ENTRIES = 128
MAX_STATE = MAX_ENTRIES * (4 * protocol.MAX_WIRE + 256) + 1024
MAX_DELIVERY = 3


def _digest(wire):
    return hashlib.sha256(wire).hexdigest()


def _wire(value):
    if type(value) is not str or not 0 < len(value) <= 2 * protocol.MAX_WIRE:
        raise ValueError("invalid journal wire")
    data = bytes.fromhex(value)
    if data.hex() != value:
        raise ValueError("noncanonical journal wire")
    return data


def verify_historical_response(wire, *, expected_request, issuer_public,
                               responder_public, audience, now):
    """Prove original validity, never present a delayed receipt as current."""
    data = protocol._verify("response", wire, responder_public)
    observed = data.get("observed_at")
    if type(now) is not int or type(observed) is not int or not 0 <= observed <= now:
        raise ValueError("unproven historical observation time")
    snapshot = protocol.verify_response(
        wire, expected_request=expected_request, issuer_public=issuer_public,
        responder_public=responder_public, audience=audience, now=observed)
    return {"observed_at": observed, "fresh": False, "snapshot": snapshot}


class DiagnosticJournal:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / "diagnostic-receipts.json"

    @contextmanager
    def _lock(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError("unprotected journal directory")
            # Lock the stable directory inode, not the replaced state file.
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def initialize(self):
        """Explicit offline provisioning, never called by process/delivery."""
        with self._lock():
            if any(self.directory.iterdir()):
                raise ValueError("journal directory not empty")
            _save(self.path, {"version": 1, "entries": {}})

    def _load(self):
        info = self.path.lstat()  # missing/corrupt is a hard failure
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_size > MAX_STATE):
            raise ValueError("unprotected journal state")
        state = json.loads(self.path.read_text(encoding="utf-8"),
                           object_pairs_hook=protocol._unique_pairs)
        if (type(state) is not dict or set(state) != {"version", "entries"}
                or type(state["version"]) is not int or state["version"] != 1
                or type(state["entries"]) is not dict
                or len(state["entries"]) > MAX_ENTRIES):
            raise ValueError("invalid journal state")
        for rid, entry in state["entries"].items():
            if (not protocol._HEX32.fullmatch(rid) or type(entry) is not dict
                    or set(entry) != {"request", "digest", "response", "delivered"}
                    or type(entry["delivered"]) is not bool
                    or _digest(_wire(entry["request"])) != entry["digest"]):
                raise ValueError("invalid receipt")
            if entry["response"] is not None:
                _wire(entry["response"])
            elif entry["delivered"]:
                raise ValueError("delivery without response")
        return state

    def process(self, wire, *, issuer_public, responder_key, audience, clock, fetch):
        """Consume before observation; save signed receipt before returning it."""
        def reserve(rid, digest):
            with self._lock():
                state = self._load()
                if rid in state["entries"] or len(state["entries"]) >= MAX_ENTRIES:
                    return False
                state["entries"][rid] = {
                    "request": wire.hex(), "digest": digest,
                    "response": None, "delivered": False,
                }
                _save(self.path, state)
                return True

        reply = protocol.process_request(
            wire, issuer_public=issuer_public, responder_key=responder_key,
            audience=audience, clock=clock, reserve=reserve, fetch=fetch)
        verify_historical_response(
            reply, expected_request=wire, issuer_public=issuer_public,
            responder_public=responder_key.public_key(), audience=audience, now=clock())
        rid = protocol._verify("request", wire, issuer_public)["request_id"]
        with self._lock():
            state = self._load()
            entry = state["entries"][rid]
            if entry["digest"] != _digest(wire) or entry["response"] is not None:
                raise ValueError("reservation changed")
            entry["response"] = reply.hex()
            _save(self.path, state)
        return reply

    def deliver_pending(self, *, issuer_public, responder_public, audience, clock, post):
        """Bounded injected transport; post(request, response) must prove ACK.

        A timeout/unknown ACK leaves the exact bytes pending. Repeated POST can
        duplicate transport messages; receiver deduplicates by request/digest.
        No observation or signing occurs in this method.
        """
        with self._lock():
            state = self._load()
            pending = [(rid, _wire(e["request"]), _wire(e["response"]))
                       for rid, e in state["entries"].items()
                       if e["response"] is not None and not e["delivered"]][:MAX_DELIVERY]
        count = 0
        for rid, request, response in pending:
            verify_historical_response(
                response, expected_request=request, issuer_public=issuer_public,
                responder_public=responder_public, audience=audience, now=clock())
            if protocol._verify("request", request, issuer_public)["request_id"] != rid:
                raise ValueError("receipt identity mismatch")
            if post(request, response) is not True:
                break
            with self._lock():
                state = self._load()
                entry = state["entries"][rid]
                if entry["request"] != request.hex() or entry["response"] != response.hex():
                    raise ValueError("receipt changed before ACK")
                entry["delivered"] = True
                _save(self.path, state)
            count += 1
        return count
