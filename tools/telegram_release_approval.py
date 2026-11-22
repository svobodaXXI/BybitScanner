"""Offline narrow contract: Telegram owner consent for one canonical UPDATE.

An issuer can propose, never approve. Gateway proof is independently keyed.
No network, service startup or trading action occurs in this module.
"""
import hashlib
import hmac
import json
import re

from tools import github_diagnostic_protocol as diagnostic

MARKER = "BYBITSCANNER_RELEASE_PROPOSAL_V1\n"
PROPOSAL_FIELDS = {"version", "operation", "audience", "request_id", "target_sha",
                   "expected_installed_sha", "issued_at", "expires_at"}
APPROVAL_FIELDS = {"request_id", "target_sha", "message_id", "update_id", "decision", "observed_at"}
MAX_AGE = 900
HEX32 = re.compile(r"[0-9a-f]{32}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SHA = re.compile(r"[0-9a-f]{40}")


def proposal_valid(p, audience, now):
    if (type(p) is not dict or set(p) != PROPOSAL_FIELDS
            or type(p["version"]) is not int or p["version"] != 1
            or p["operation"] != "propose_update" or p["audience"] != audience
            or type(audience) is not str or not HEX32.fullmatch(audience)
            or type(p["request_id"]) is not str or not HEX32.fullmatch(p["request_id"])
            or any(type(p[k]) is not str or not SHA.fullmatch(p[k])
                   for k in ("target_sha", "expected_installed_sha"))
            or p["target_sha"] == p["expected_installed_sha"]
            or any(type(p[k]) is not int for k in ("issued_at", "expires_at"))
            or type(now) is not int or not 0 <= p["issued_at"] <= now < p["expires_at"]
            or not 0 < p["expires_at"] - p["issued_at"] <= MAX_AGE):
        raise ValueError("invalid or expired release proposal")
    return p


def sign_proposal(p, *, issuer_key, audience, now):
    proposal_valid(p, audience, now)
    # A distinct signature domain prevents diagnostic requests from being
    # reinterpreted as release requests. This grants notification only.
    return diagnostic._sign("release-proposal", p, issuer_key)


def verify_proposal(wire, *, issuer_public, audience, now):
    return proposal_valid(diagnostic._verify("release-proposal", wire, issuer_public),
                          audience, now)


def approval_message(sha):
    if type(sha) is not str or not SHA.fullmatch(sha):
        raise ValueError("invalid release SHA")
    return ("BybitScanner: обновление VPS\nSHA: " + sha
            + "\nШтатный UPDATE. Торговля останется выключенной.")


def approval_payload(p):
    return (type(p) is dict and set(p) == APPROVAL_FIELDS
            and type(p["request_id"]) is str and HEX32.fullmatch(p["request_id"])
            and type(p["target_sha"]) is str and SHA.fullmatch(p["target_sha"])
            and type(p["decision"]) is str and p["decision"] in ("approve", "reject")
            and all(type(p[k]) is int and 0 < p[k] <= 2**53-1
                    for k in ("message_id", "update_id", "observed_at")))


def verify_approval(envelope, *, key, proposal, message_id, now):
    if (type(key) is not bytes or len(key) != 32 or type(envelope) is not dict
            or set(envelope) != {"payload", "tag"} or not approval_payload(envelope["payload"])
            or type(envelope["tag"]) is not str or not HEX64.fullmatch(envelope["tag"])):
        raise ValueError("invalid approval envelope")
    p = envelope["payload"]
    # ASCII-only fixed-schema fields, sorted identically by Gateway.
    tag = hmac.new(key, b"BybitScanner-Release-Approval-v1\x00" +
                   diagnostic._canonical(p), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tag, envelope["tag"]):
        raise ValueError("approval authentication failed")
    if (p["request_id"] != proposal["request_id"] or p["target_sha"] != proposal["target_sha"]
            or type(message_id) is not int or p["message_id"] != message_id
            or not proposal["issued_at"] <= p["observed_at"] <= now < proposal["expires_at"]):
        raise ValueError("approval identity or freshness unproven")
    return p["decision"]


def consume_approval(envelope, *, key, proposal, message_id, now, reserve,
                     installed, stable, submit):
    """Host must reserve durably before calling the sole canonical submit.

    A lost submission ACK is terminal UNKNOWN for this approval. Never retry.
    """
    proposal_valid(proposal, proposal["audience"], now)
    decision = verify_approval(envelope, key=key, proposal=proposal,
                               message_id=message_id, now=now)
    if decision == "reject":
        if reserve("REJECTED") is not True:
            return "UNPROVEN"
        return "REJECTED"
    # Independent exact current/stable checks, not claims from the issuer.
    if installed() != proposal["expected_installed_sha"] or stable() != proposal["target_sha"]:
        if reserve("BLOCKED_SHA") is not True:
            return "UNPROVEN"
        return "BLOCKED_SHA"
    if reserve("SUBMIT_UNPROVEN") is not True:
        return "UNPROVEN"
    try:
        return "SUBMITTED" if submit("update", proposal["target_sha"],
                                     proposal["request_id"], "telegram-owner") == 0 else "SUBMIT_UNPROVEN"
    except Exception:
        return "SUBMIT_UNPROVEN"
