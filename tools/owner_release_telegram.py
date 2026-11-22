"""Independent Telegram confirmation for the existing owner release grant.

No network, polling, root escalation, or alternate executor in this module.
A trusted Gateway attests only a real upstream Telegram callback. The protected
host binds it to its own exact displayed challenge before producing a grant.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import secrets

from Crypto.Signature import eddsa

from tools import owner_update_grant as grants

DOMAIN = b"BybitScanner-Telegram-Release-Callback-v1\x00"
MAX_PROPOSAL_TTL = 900
MAX_RECEIPT_AGE = 120
MAX_WIRE = 4096
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[1-9][0-9]{0,15}\Z")
PROPOSAL_FIELDS = {"version", "operation", "owner_request_id",
                   "expected_installed_sha", "target_sha", "issued_at", "expires_at"}
RECEIPT_FIELDS = {"version", "nonce", "decision", "owner_id", "bot_id",
                  "message_id", "text_sha256", "observed_at", "update_id"}


def proposal(value, now):
    if (type(value) is not dict or set(value) != PROPOSAL_FIELDS
            or type(value["version"]) is not int or value["version"] != 1
            or type(value["operation"]) is not str or value["operation"] not in grants.ACTIONS
            or not grants._hex(value["owner_request_id"], grants.HEX32)
            or not grants._hex(value["expected_installed_sha"], grants.HEX40)
            or not grants._hex(value["target_sha"], grants.HEX40)
            or value["expected_installed_sha"] == value["target_sha"]
            or type(now) is not int
            or type(value["issued_at"]) is not int or type(value["expires_at"]) is not int
            or not 0 <= value["issued_at"] <= now < value["expires_at"]
            or not 0 < value["expires_at"] - value["issued_at"] <= MAX_PROPOSAL_TTL):
        raise ValueError("invalid or expired release proposal")
    return value


def prompt_text(value, nonce):
    label = ("Обновить и запустить PAPER (Scanner, Robot, Autopilot)"
             if value["operation"] == "update-and-start"
             else "Обновить, оставить EDITOR_ONLY (без торговли)")
    deadline = datetime.fromtimestamp(value["expires_at"], timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (f"Подтверждение релиза BybitScanner\n{label}\n"
            f"Текущий SHA: {value['expected_installed_sha']}\n"
            f"Целевой SHA: {value['target_sha']}\n"
            f"UUID: {value['owner_request_id']}\n"
            f"Действует до: {deadline}\n"
            f"Запрос: {nonce}\nLIVE запрещён.")


def new_challenge(value, now, installed_sha):
    proposal(value, now)
    if installed_sha != value["expected_installed_sha"]:
        raise ValueError("proposal predecessor differs")
    nonce = secrets.token_hex(16)
    text = prompt_text(value, nonce)
    return {"proposal": dict(value), "nonce": nonce,
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "message_id": None}


def keyboard(nonce):
    if not grants._hex(nonce, grants.HEX32):
        raise ValueError("invalid challenge nonce")
    return {"inline_keyboard": [[
        {"text": "Подтвердить", "callback_data": "owner-release:yes:" + nonce},
        {"text": "Отклонить", "callback_data": "owner-release:no:" + nonce},
    ]]}


def verify_callback(wire, *, challenge, callback_public, owner_id, bot_id, now):
    """Require the independently signed upstream click and exact saved prompt."""
    grants._key(callback_public, False)
    if (type(wire) is not bytes or not 0 < len(wire) <= MAX_WIRE
            or not grants._hex(owner_id, ID) or not grants._hex(bot_id, ID)):
        raise ValueError("invalid callback envelope")
    try:
        envelope = json.loads(wire.decode("ascii"), object_pairs_hook=grants._unique_pairs)
        if (type(envelope) is not dict or set(envelope) != {"payload", "signature"}
                or not grants._hex(envelope["signature"], grants.HEX128)
                or grants._canonical(envelope) != wire):
            raise ValueError("invalid callback envelope")
        receipt = envelope["payload"]
        eddsa.new(callback_public, "rfc8032").verify(
            DOMAIN + grants._canonical(receipt), bytes.fromhex(envelope["signature"]))
        if (type(receipt) is not dict or set(receipt) != RECEIPT_FIELDS
                or type(receipt["version"]) is not int or receipt["version"] != 1
                or type(receipt["decision"]) is not str or receipt["decision"] not in ("yes", "no")
                or receipt["owner_id"] != owner_id or receipt["bot_id"] != bot_id
                or not grants._hex(receipt["nonce"], grants.HEX32)
                or receipt["nonce"] != challenge["nonce"]
                or type(challenge["message_id"]) is not int or challenge["message_id"] <= 0
                or type(receipt["message_id"]) is not int
                or receipt["message_id"] != challenge["message_id"]
                or not grants._hex(receipt["text_sha256"], HEX64)
                or receipt["text_sha256"] != challenge["text_sha256"]
                or type(receipt["update_id"]) is not int or receipt["update_id"] < 0
                or type(receipt["observed_at"]) is not int
                or not 0 <= now - receipt["observed_at"] < MAX_RECEIPT_AGE):
            raise ValueError("callback/challenge identity differs")
        p = proposal(challenge["proposal"], now)
        if (receipt["observed_at"] < p["issued_at"]
                or challenge["text_sha256"] != hashlib.sha256(
                    prompt_text(p, challenge["nonce"]).encode("utf-8")).hexdigest()):
            raise ValueError("callback prompt not proven")
        return receipt["decision"]
    except (KeyError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("Telegram release confirmation unproven") from None


def confirm(wire, *, challenge, callback_public, owner_id, bot_id, approval_key,
            diagnostic_issuer_public, diagnostic_responder_public, audience,
            ledger, installed_sha, consume, clock, submit=None):
    """Consume the protected challenge before the canonical one-use dispatch.

    The caller must hold the protected challenge lifecycle lock and persist
    consume() before returning. Never treat an untrusted relay as consent.
    """
    grants._key(approval_key, True)
    keys = (callback_public, approval_key.public_key(),
            diagnostic_issuer_public, diagnostic_responder_public)
    for key in keys:
        grants._key(key, False)
    if any(left == right for i, left in enumerate(keys) for right in keys[i+1:]):
        raise ValueError("release and diagnostic keys must be independent")
    now = clock()
    decision = verify_callback(wire, challenge=challenge, callback_public=callback_public,
                               owner_id=owner_id, bot_id=bot_id, now=now)
    p = challenge["proposal"]
    if installed_sha() != p["expected_installed_sha"]:
        raise ValueError("installed release changed before confirmation")
    if consume() is not True:
        raise ValueError("challenge already consumed or persistence unproven")
    if decision == "no":
        return "DECLINED", None
    now = clock()
    proposal(p, now)
    approved = {k: p[k] for k in ("version", "operation", "owner_request_id",
                                  "expected_installed_sha", "target_sha")}
    approved.update(audience=audience, approved_at=now,
                    expires_at=min(p["expires_at"], now + grants.MAX_TTL))
    grant = grants.sign_grant(approved, approval_key=approval_key, audience=audience, now=now)
    rc = grants.submit_granted_update(
        grant, enabled=True, approval_public=approval_key.public_key(),
        diagnostic_issuer_public=diagnostic_issuer_public,
        diagnostic_responder_public=diagnostic_responder_public,
        audience=audience, ledger=ledger, installed_sha=installed_sha,
        clock=clock, submit=submit)
    return "SUBMITTED" if rc == 0 else "SUBMISSION_UNPROVEN", rc
