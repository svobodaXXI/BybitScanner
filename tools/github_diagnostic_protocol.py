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
OWNER_STATUS_FIELDS = {"owner_request_id", "owner_action", "target_sha"}
OWNER_ACTIONS = frozenset(("update", "update-take-closed", "update-and-start", "start",
                          "stop", "telegram-recover", "provision-owner-pc",
                          "github-status-enable", "github-diagnostic-enable"))
EDITOR_ACTIONS = frozenset(("update", "update-take-closed"))
OWNER_STATES = frozenset(("FINISHED_OK", "RUNNING", "FAILED", "UNPROVEN"))
OWNER_RESULTS = frozenset(("success", "exit-code", "signal", "core-dump", "timeout",
                          "watchdog", "resources", "start-limit-hit", "oom-kill",
                          "protocol", "exec-condition", "UNKNOWN"))
_OWNER_SHA = re.compile(r"[0-9a-f]{40}")
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


def _owner_identity(payload):
    return (type(payload.get("owner_request_id")) is str
            and _HEX32.fullmatch(payload["owner_request_id"]) is not None
            and type(payload.get("owner_action")) is str
            and payload["owner_action"] in OWNER_ACTIONS
            and type(payload.get("target_sha")) is str
            and _OWNER_SHA.fullmatch(payload["target_sha"]) is not None)


def _request(payload: dict, audience: str, now: int) -> None:
    if type(payload) is not dict:
        raise ValueError("invalid diagnostic request")
    operation = payload.get("operation")
    if operation == "observe":
        fields = _REQUEST_FIELDS
    elif operation == "owner_status" and _owner_identity(payload):
        fields = _REQUEST_FIELDS | OWNER_STATUS_FIELDS
    else:
        raise ValueError("invalid diagnostic operation")
    if (set(payload) != fields
            or type(payload["version"]) is not int or payload["version"] != 1
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


def _safe_owner_snapshot(raw, request):
    fields = OWNER_STATUS_FIELDS | {"state", "result", "exit_code", "postcheck"}
    if (type(raw) is not dict or set(raw) != fields or not _owner_identity(raw)
            or any(raw[k] != request[k] for k in OWNER_STATUS_FIELDS)
            or type(raw["state"]) is not str or raw["state"] not in OWNER_STATES
            or type(raw["result"]) is not str or raw["result"] not in OWNER_RESULTS
            or (raw["exit_code"] is not None and
                (type(raw["exit_code"]) is not int or not 0 <= raw["exit_code"] <= 255))
            or type(raw["postcheck"]) is not str):
        raise ValueError("unsafe owner outcome")
    state, result, code, postcheck = (raw[k] for k in ("state", "result", "exit_code", "postcheck"))
    if state == "UNPROVEN" and (result != "UNKNOWN" or code is not None):
        raise ValueError("unproven owner outcome")
    if state == "RUNNING" and code is not None:
        raise ValueError("running owner outcome has no final exit")
    if state == "FINISHED_OK" and (result != "success" or code != 0):
        raise ValueError("owner success unproven")
    expected = ({"VERIFIED_EDITOR_ONLY", "BLOCKED"} if state == "FINISHED_OK"
                and raw["owner_action"] in EDITOR_ACTIONS else
                {"NOT_APPLICABLE"} if state == "FINISHED_OK" else {"NOT_RUN"})
    if postcheck not in expected:
        raise ValueError("owner postcheck inconsistent")
    return raw


def _safe_reply(snapshot, request):
    if request["operation"] == "observe":
        return _safe_snapshot(snapshot)
    return _safe_owner_snapshot(snapshot, request)


def sign_request(payload: dict, *, issuer_key: EccKey, audience: str, now: int) -> bytes:
    """For a separately trusted issuer; never the Github Issues PAT."""
    _request(payload, audience, now)
    return _sign("request", payload, issuer_key)


def process_request(wire: bytes, *, issuer_public: EccKey, responder_key: EccKey,
                    audience: str, clock: Callable[[], int],
                    reserve: Callable[[str, str], bool], fetch: Callable[[str], dict],
                    owner_status=None) -> bytes:
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
    if request["operation"] == "observe":
        snapshot = _safe_snapshot(observe(fetch))
    else:
        if owner_status is None:
            raise ValueError("owner status reader unavailable")
        snapshot = _safe_owner_snapshot(owner_status(
            request["owner_request_id"], request["owner_action"], request["target_sha"]), request)
    observed_at = clock()
    _request(request, audience, observed_at)
    payload = {
        "version": 1, "operation": request["operation"], "audience": audience,
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
            or data["operation"] != request["operation"] or data["authority"] != "OBSERVATION_ONLY"
            or data["audience"] != audience or data["request_id"] != request["request_id"]
            or data["request_digest"] != hashlib.sha256(expected_request).hexdigest()
            or type(data["observed_at"]) is not int
            or not request["issued_at"] <= data["observed_at"] <= now):
        raise ValueError("response correlation unproven")
    return _safe_reply(data["snapshot"], request)
