"""Offline protocol for a single authenticated, public read-only diagnostic.

No polling, service, credentials, key loading, runtime commands or default
network callback. GitHub transport and protected durable reservation are
separate acceptance gates. No request or response grants mutation authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Callable

from Crypto.PublicKey.ECC import EccKey
from Crypto.Signature import eddsa

from tools.github_status_reporter import _safe_snapshot, observe

MAX_WIRE = 4096
MAX_AGE = 300
_HEX32 = re.compile(r"[0-9a-f]{32}")
_SIGNATURE = re.compile(r"[0-9a-f]{128}")
_REQUEST_FIELDS = {"version", "operation", "audience", "request_id", "issued_at", "expires_at"}
_RESPONSE_FIELDS = {"version", "operation", "audience", "request_id", "request_digest",
                    "observed_at", "authority", "snapshot"}


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _key(key: EccKey, private: bool) -> None:
    if (not isinstance(key, EccKey) or key.curve != "Ed25519"
            or key.has_private() != private):
        raise ValueError("invalid trusted key")


def _domain(kind: str, payload: dict) -> bytes:
    return b"BybitScanner-GitHub-Diagnostic-v1/" + kind.encode("ascii") + b"\x00" + _canonical(payload)


def _sign(kind: str, payload: dict, key: EccKey) -> bytes:
    _key(key, True)
    signature = eddsa.new(key, "rfc8032").sign(_domain(kind, payload))
    return _canonical({"payload": payload, "signature": signature.hex()})


def _verify(kind: str, wire: bytes, public_key: EccKey) -> dict:
    _key(public_key, False)
    if type(wire) is not bytes or not 0 < len(wire) <= MAX_WIRE:
        raise ValueError("invalid message size")
    try:
        message = json.loads(wire.decode("ascii"), object_pairs_hook=_unique_pairs)
        if type(message) is not dict or set(message) != {"payload", "signature"}:
            raise ValueError("invalid envelope")
        payload, signature = message["payload"], message["signature"]
        if (type(payload) is not dict or type(signature) is not str
                or not _SIGNATURE.fullmatch(signature)
                or wire != _canonical(message)):
            raise ValueError("invalid envelope")
        eddsa.new(public_key, "rfc8032").verify(
            _domain(kind, payload), bytes.fromhex(signature))
        return payload
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError("message authentication failed") from None


def _request(payload: dict, audience: str, now: int) -> None:
    if (type(payload) is not dict or set(payload) != _REQUEST_FIELDS
            or type(payload["version"]) is not int or payload["version"] != 1
            or payload["operation"] != "observe"
            or type(audience) is not str or not _HEX32.fullmatch(audience)
            or payload["audience"] != audience
            or type(payload["request_id"]) is not str
            or not _HEX32.fullmatch(payload["request_id"])
            or type(now) is not int
            or type(payload["issued_at"]) is not int
            or type(payload["expires_at"]) is not int
            or not 0 <= payload["issued_at"] <= now < payload["expires_at"]
            or not 0 < payload["expires_at"] - payload["issued_at"] <= MAX_AGE):
        raise ValueError("invalid or expired diagnostic request")


def sign_request(payload: dict, *, issuer_key: EccKey, audience: str, now: int) -> bytes:
    """For a separately trusted issuer; never the Github Issues PAT."""
    _request(payload, audience, now)
    return _sign("request", payload, issuer_key)


def process_request(wire: bytes, *, issuer_public: EccKey, responder_key: EccKey,
                    audience: str, clock: Callable[[], int],
                    reserve: Callable[[str, str], bool], fetch: Callable[[str], dict]) -> bytes:
    """Verify before even reading a local API. No automatic runtime action.

    reserve must atomically/durably consume the ID+digest (including across
    reboots) or return False. This prototype deliberately does not supply a
    production reservation implementation. A consumed request is not replayed
    after failure; production delivery must use its separately durable receipt.
    """
    _key(issuer_public, False)
    _key(responder_key, True)
    if issuer_public == responder_key.public_key():
        raise ValueError("request and response keys must differ")
    request = _verify("request", wire, issuer_public)
    _request(request, audience, clock())
    digest = hashlib.sha256(wire).hexdigest()
    if reserve(request["request_id"], digest) is not True:
        raise ValueError("request already consumed or reservation unproven")
    snapshot = _safe_snapshot(observe(fetch))
    observed_at = clock()
    _request(request, audience, observed_at)
    payload = {
        "version": 1, "operation": "observe", "audience": audience,
        "request_id": request["request_id"], "request_digest": digest,
        "observed_at": observed_at, "authority": "OBSERVATION_ONLY",
        "snapshot": snapshot,
    }
    return _sign("response", payload, responder_key)


def verify_response(wire: bytes, *, expected_request: bytes, issuer_public: EccKey,
                    responder_public: EccKey, audience: str, now: int) -> dict:
    """Authenticate a response for one outstanding, still-valid request."""
    if issuer_public == responder_public:
        raise ValueError("request and response keys must differ")
    request = _verify("request", expected_request, issuer_public)
    _request(request, audience, now)
    data = _verify("response", wire, responder_public)
    if (set(data) != _RESPONSE_FIELDS
            or type(data["version"]) is not int or data["version"] != 1
            or data["operation"] != "observe" or data["authority"] != "OBSERVATION_ONLY"
            or data["audience"] != audience or data["request_id"] != request["request_id"]
            or data["request_digest"] != hashlib.sha256(expected_request).hexdigest()
            or type(data["observed_at"]) is not int
            or not request["issued_at"] <= data["observed_at"] <= now):
        raise ValueError("response correlation unproven")
    return _safe_snapshot(data["snapshot"])
