"""Offline exact-release owner authorization; no polling, CLI or automatic activation.

A future protected owner-confirmation adapter must provide an independent pinned
approval key (never the diagnostic issuer/responder or Telegram bot credential),
a trusted current-release reader and an explicitly enabled root-owned ledger.
Only the existing owner monolith may perform UPDATE. No START or trading action.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time

from Crypto.PublicKey.ECC import EccKey
from Crypto.Signature import eddsa

from tools.github_diagnostic_protocol import _canonical, _unique_pairs

MAX_TTL = 300
MAX_WIRE = 4096
HEX32 = re.compile(r"[0-9a-f]{32}")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX128 = re.compile(r"[0-9a-f]{128}")
DOMAIN = b"BybitScanner-Owner-Update-Grant-v1\x00"
FIELDS = {"version", "operation", "audience", "owner_request_id",
          "expected_installed_sha", "target_sha", "approved_at", "expires_at"}


def _key(key, private):
    if not isinstance(key, EccKey) or key.curve != "Ed25519" or key.has_private() != private:
        raise ValueError("invalid owner authority key")


def _hex(value, pattern):
    return type(value) is str and pattern.fullmatch(value) is not None


def _validate(payload, audience, now):
    if (type(payload) is not dict or set(payload) != FIELDS
            or type(payload["version"]) is not int or payload["version"] != 1
            or payload["operation"] != "update"
            or not _hex(audience, HEX32) or payload["audience"] != audience
            or not _hex(payload["owner_request_id"], HEX32)
            or not _hex(payload["expected_installed_sha"], HEX40)
            or not _hex(payload["target_sha"], HEX40)
            or payload["expected_installed_sha"] == payload["target_sha"]
            or type(now) is not int or type(payload["approved_at"]) is not int
            or type(payload["expires_at"]) is not int
            or not 0 <= payload["approved_at"] <= now < payload["expires_at"]
            or not 0 < payload["expires_at"] - payload["approved_at"] <= MAX_TTL):
        raise ValueError("invalid or expired owner update grant")


def sign_grant(payload, *, approval_key, audience, now):
    """Called only by an independently authorized owner signer; not a UI proof."""
    _key(approval_key, True)
    _validate(payload, audience, now)
    signature = eddsa.new(approval_key, "rfc8032").sign(DOMAIN + _canonical(payload))
    return _canonical({"payload": payload, "signature": signature.hex()})


def verify_grant(wire, *, approval_public, diagnostic_issuer_public,
                 diagnostic_responder_public, audience, now):
    for key in (approval_public, diagnostic_issuer_public, diagnostic_responder_public):
        _key(key, False)
    if (approval_public == diagnostic_issuer_public
            or approval_public == diagnostic_responder_public
            or diagnostic_issuer_public == diagnostic_responder_public):
        raise ValueError("owner and diagnostic keys must be independent")
    if type(wire) is not bytes or not 0 < len(wire) <= MAX_WIRE:
        raise ValueError("invalid owner grant size")
    try:
        envelope = json.loads(wire.decode("ascii"), object_pairs_hook=_unique_pairs)
        if (type(envelope) is not dict or set(envelope) != {"payload", "signature"}
                or not _hex(envelope["signature"], HEX128) or wire != _canonical(envelope)):
            raise ValueError("invalid grant envelope")
        payload = envelope["payload"]
        eddsa.new(approval_public, "rfc8032").verify(
            DOMAIN + _canonical(payload), bytes.fromhex(envelope["signature"]))
        _validate(payload, audience, now)
        return payload
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("owner update authorization unproven") from None


class GrantLedger:
    """Append-only, private local receipts; never recreates or prunes on dispatch.

    A separately authorized provisioning operation must create the directory
    and marker under a protected parent. An interrupted claim remains consumed.
    The host adapter must keep this dedicated directory across releases/reboots.
    """

    def __init__(self, directory):
        self.directory = Path(directory)

    @contextmanager
    def _open(self):
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.geteuid() or info.st_mode & 0o077:
                raise ValueError("unprotected owner grant ledger")
            yield fd
        finally:
            os.close(fd)

    def initialize(self):
        """Explicit provisioning only; never called by dispatch."""
        with self._open() as directory:
            if os.listdir(directory):
                raise ValueError("owner grant ledger not empty")
            self._write_once(directory, "initialized", b"owner-update-v1\n")

    @staticmethod
    def _write_once(directory, name, data):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory)

    def reserve(self, request_id, digest):
        if not _hex(request_id, HEX32) or not _hex(digest, re.compile(r"[0-9a-f]{64}")):
            raise ValueError("invalid reservation identity")
        with self._open() as directory:
            fd = os.open("initialized", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=directory)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or info.st_mode & 0o077 or stream.read(64) != b"owner-update-v1\n"):
                    raise ValueError("owner grant ledger not initialized")
            try:
                self._write_once(directory, request_id + ".used", (digest + "\n").encode("ascii"))
            except FileExistsError:
                return False
            return True


def submit_granted_update(wire, *, enabled, approval_public, diagnostic_issuer_public,
                          diagnostic_responder_public, audience, ledger, installed_sha,
                          clock=lambda: int(time.time()), submit=None):
    """Root-host integration boundary, intentionally not wired to any transport.

    Only the trusted host supplies pins, ledger and release reader. The test
    seam substitutes canonical submit; production must use vps_owner_control.
    A claimed UUID is never submitted again, including on uncertain submission.
    Return code is submission evidence only, not final installation proof.
    """
    if enabled is not True:
        raise ValueError("owner update transport disabled")
    pins = dict(approval_public=approval_public, diagnostic_issuer_public=diagnostic_issuer_public,
                diagnostic_responder_public=diagnostic_responder_public, audience=audience)
    grant = verify_grant(wire, now=clock(), **pins)
    if installed_sha() != grant["expected_installed_sha"]:
        raise ValueError("installed release changed")
    if not ledger.reserve(grant["owner_request_id"], hashlib.sha256(wire).hexdigest()):
        raise ValueError("owner grant already consumed")
    # No retry when the release or clock changes after consumption.
    verify_grant(wire, now=clock(), **pins)
    if installed_sha() != grant["expected_installed_sha"]:
        raise ValueError("installed release changed after claim")
    verify_grant(wire, now=clock(), **pins)
    if submit is None:
        from tools.vps_owner_control import submit
    return submit("update", grant["target_sha"], grant["owner_request_id"], "owner-approved-update")
