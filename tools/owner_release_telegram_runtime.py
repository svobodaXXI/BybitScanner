"""Protected, opt-in owner release authorization adapter.

This is not a release executor: only the existing vps_owner_control receives
an authenticated, exact, one-use approval. No automatic provisioning or enable.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
import time

from Crypto.Signature import eddsa
import requests

from tools import owner_release_telegram as approvals
from tools import owner_update_grant as grants
from tools import telegram_release_inbox as relay
from tools.github_diagnostic_runtime import _config as diagnostic_config
from tools.vps_gitless_release_activate import _atomic_file, _manifest, _trusted_file
from tools.vps_release_identity import ROOT, MANIFEST, _safe_file, git_blob_hash, verify_release
import telegram_gateway_client

CONFIG = Path("/etc/bybitscanner/owner-release/config.json")
STATE = Path("/var/lib/bybitscanner-owner-release")
PROPOSAL_URL = ("https://raw.githubusercontent.com/svobodaXXI/BybitScanner/"
                "owner-release-proposals/.github/owner-release-request.json")
CONFIG_FIELDS = {"enabled", "owner_id", "bot_id", "audience",
                 "callback_public", "approval_seed"}
PINNED = ("tools/owner_release_telegram_runtime.py", "tools/owner_release_telegram.py",
          "tools/owner_release_telegram_provision.py",
          "tools/owner_update_grant.py", "tools/telegram_release_inbox.py",
          "tools/vps_owner_control.py", "tools/paper_maintenance.py",
          "tools/vps_release_identity.py", "tools/vps_gitless_release_activate.py",
          "tools/github_diagnostic_runtime.py", "tools/github_diagnostic_protocol.py",
          "telegram_gateway_client.py")
OWNER_UNIT_NAMES = ("bybitscanner-owner-release-approval.service",
                    "bybitscanner-owner-release-approval.timer")


def _private_dir(directory):
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError("unprotected approval directory")
    parent = directory.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_mode & 0o022:
        raise ValueError("unprotected approval parent")


def _private_json(path, limit=4096):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("unprotected approval file")
        raw = stream.read(limit + 1)
    if not 0 < len(raw) <= limit:
        raise ValueError("approval file size")
    return json.loads(raw, object_pairs_hook=grants._unique_pairs)


def _read_config(path):
    _private_dir(path.parent)
    c = _private_json(path)
    if (type(c) is not dict or set(c) != CONFIG_FIELDS or type(c["enabled"]) is not bool
            or not grants._hex(c["owner_id"], approvals.ID)
            or not grants._hex(c["bot_id"], approvals.ID)
            or c["owner_id"] == c["bot_id"]
            or not grants._hex(c["audience"], grants.HEX32)
            or not grants._hex(c["callback_public"], approvals.HEX64)
            or not grants._hex(c["approval_seed"], approvals.HEX64)):
        raise ValueError("invalid approval configuration")
    return c


def _check_sources(root, manifest_path, installed):
    manifest = _manifest(_trusted_file(manifest_path, 0))
    if manifest["build_sha"] != installed:
        raise ValueError("approval release changed")
    for name in PINNED:
        if manifest["blobs"].get(name) != git_blob_hash(
                _trusted_file(_safe_file(root, name), 0)):
            raise ValueError("approval source not pinned")


def _check_units(root, manifest_path, unit_dir, *, uid=0):
    """Read-only exact-byte check; never install, enable or reload systemd."""
    manifest = _manifest(_trusted_file(manifest_path, uid))
    for name in OWNER_UNIT_NAMES:
        rel = "deploy/systemd/" + name
        blob = manifest["blobs"].get(rel)
        if (blob is None
                or blob != git_blob_hash(_trusted_file(_safe_file(root, rel), uid))
                or blob != git_blob_hash(_trusted_file(unit_dir / name, uid))):
            raise ValueError("approval systemd unit not pinned")


def _check_ledger(directory, *, uid=0):
    """Check durable one-use receipts without creating or consuming any."""
    info = directory.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != uid
            or info.st_mode & 0o077 or directory.is_symlink()):
        raise ValueError("approval ledger unprotected")
    fd = os.open(directory / "initialized", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid
                or info.st_mode & 0o077 or info.st_nlink != 1
                or stream.read(64) != b"owner-update-v1\n"):
            raise ValueError("approval ledger not initialized")


def _check_relay_inbox(inbox, relay_uid):
    """The Telegram worker owns a courier directory, never owner credentials."""
    parent = inbox.parent.lstat()
    info = inbox.lstat()
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0
            or parent.st_mode & 0o022
            or not stat.S_ISDIR(info.st_mode) or info.st_uid != relay_uid
            or info.st_mode & 0o077 or inbox.is_symlink()):
        raise ValueError("approval relay inbox untrusted")


def preflight(*, config=CONFIG, state=STATE, root=ROOT, manifest_path=MANIFEST,
              unit_dir=Path("/etc/systemd/system"),
              relay_inbox=relay.INBOX):
    """No mutations, network calls, Telegram messages, STOP or START.

    Host-only proof. It cannot prove the Cloudflare signing key has been
    deployed or that a real owner callback has ever been received.
    """
    if os.geteuid() != 0:
        raise ValueError("owner required")
    c = _read_config(config)
    installed = verify_release(root, manifest_path)
    _check_sources(root, manifest_path, installed)
    _check_units(root, manifest_path, unit_dir)
    _private_dir(state)
    pending = _private_json(state / "pending.json")
    if type(pending) is not dict or set(pending) != {"pending"} or pending["pending"] is not None:
        raise ValueError("approval not in initial idle state")
    for name in ("prompts", "grants"):
        _check_ledger(state / name)
    relay_uid = pwd.getpwnam("bybitscanner").pw_uid
    _check_relay_inbox(relay_inbox, relay_uid)
    diag, diag_issuer, diag_responder = diagnostic_config()
    if not diag["enabled"] or diag["release_sha"] != installed:
        raise ValueError("signed diagnostic bridge not prepared for exact release")
    callback = eddsa.import_public_key(bytes.fromhex(c["callback_public"]))
    approval = eddsa.import_private_key(bytes.fromhex(c["approval_seed"]))
    keys = (callback, approval.public_key(), diag_issuer, diag_responder.public_key())
    if any(left == right for i, left in enumerate(keys) for right in keys[i+1:]):
        raise ValueError("approval key separation unproven")
    if os.getenv("TELEGRAM_CHAT_ID", "").strip() != c["owner_id"]:
        raise ValueError("approval owner route differs")
    if not telegram_gateway_client.configured():
        raise ValueError("approved gateway not configured")
    # Proof of protected local prerequisites, never remote activation.
    return "HOST_PRECHECK_OK_DISABLED" if not c["enabled"] else "HOST_PRECHECK_OK_ENABLED"


@contextmanager
def _lock(state):
    _private_dir(state)
    fd = os.open(state / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+b") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o077 or info.st_nlink != 1):
            raise ValueError("unprotected approval lock")
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def fetch_proposal():
    # Fixed, public, untrusted input. A proposal has no execution authority.
    with requests.Session() as session:
        session.trust_env = False
        with session.get(PROPOSAL_URL, timeout=(3, 8), allow_redirects=False,
                         stream=True, headers={"Cache-Control": "no-cache"}) as response:
            if response.status_code == 404:
                return None
            if response.status_code != 200:
                raise ValueError("proposal transport unavailable")
            raw = bytearray()
            for chunk in response.iter_content(1024):
                raw.extend(chunk)
                if len(raw) > 4096:
                    raise ValueError("proposal too large")
            return json.loads(raw, object_pairs_hook=grants._unique_pairs)


def cycle(*, load, save, prompts, ledger, fetch, send, receive, installed_sha,
          callback_public, owner_id, bot_id, approval_key, diagnostic_issuer_public,
          diagnostic_responder_public, audience, clock, submit=None):
    """One bounded cycle. load/save/ledgers are root-protected under one lock."""
    state = load()
    if type(state) is not dict or set(state) != {"pending"}:
        raise ValueError("invalid protected pending state")
    pending = state["pending"]
    now = clock()
    if pending is not None:
        if (type(pending) is not dict
                or set(pending) != {"proposal", "nonce", "text_sha256", "message_id"}
                or not grants._hex(pending["nonce"], grants.HEX32)):
            raise ValueError("invalid protected challenge")
        if now >= pending["proposal"]["expires_at"]:
            save({"pending": None})
            return "EXPIRED"
        approvals.proposal(pending["proposal"], now)
        if pending["message_id"] is None:
            # A send may have succeeded before response persistence. Do not
            # send again, do not accept an unbound message, wait for expiry.
            return "PROMPT_UNPROVEN"
        wire = receive(pending["nonce"])
        if wire is None:
            return "AWAITING_OWNER"
        def consume():
            save({"pending": None})
            return True
        outcome, _ = approvals.confirm(
            wire, challenge=pending, callback_public=callback_public,
            owner_id=owner_id, bot_id=bot_id, approval_key=approval_key,
            diagnostic_issuer_public=diagnostic_issuer_public,
            diagnostic_responder_public=diagnostic_responder_public,
            audience=audience, ledger=ledger, installed_sha=installed_sha,
            consume=consume, clock=clock, submit=submit)
        return outcome

    value = fetch()
    if value is None:
        return "IDLE"
    now = clock()
    # Already expired proposals are not authority and need no repeated alarms.
    if (isinstance(value, dict) and type(value.get("expires_at")) is int
            and value["expires_at"] <= now):
        return "IDLE"
    challenge = approvals.new_challenge(value, now, installed_sha())
    digest = hashlib.sha256(grants._canonical(value)).hexdigest()
    if not prompts.reserve(value["owner_request_id"], digest):
        return "ALREADY_SEEN"
    # Persist the one-time prompt before any external send.
    save({"pending": challenge})
    message_id = send(approvals.prompt_text(value, challenge["nonce"]),
                      approvals.keyboard(challenge["nonce"]))
    if type(message_id) is not int or message_id <= 0:
        return "PROMPT_UNPROVEN"
    challenge["message_id"] = message_id
    save({"pending": challenge})
    return "AWAITING_OWNER"


def run_once(*, config=CONFIG, state=STATE, root=ROOT, manifest_path=MANIFEST,
             clock=lambda: int(time.time())):
    if os.geteuid() != 0:
        raise ValueError("owner required")
    if not os.path.lexists(config):
        return "DISABLED"
    c = _read_config(config)
    if not c["enabled"]:
        return "DISABLED"
    with _lock(state):
        if _read_config(config) != c:
            raise ValueError("approval configuration changed")
        installed = verify_release(root, manifest_path)
        _check_sources(root, manifest_path, installed)
        _check_units(root, manifest_path, Path("/etc/systemd/system"))
        _, diag_issuer, diag_responder = diagnostic_config()
        callback = eddsa.import_public_key(bytes.fromhex(c["callback_public"]))
        approval = eddsa.import_private_key(bytes.fromhex(c["approval_seed"]))
        keys = (callback, approval.public_key(), diag_issuer, diag_responder.public_key())
        if any(left == right for i, left in enumerate(keys) for right in keys[i+1:]):
            raise ValueError("approval key separation unproven")
        if os.getenv("TELEGRAM_CHAT_ID", "").strip() != c["owner_id"]:
            raise ValueError("approval owner route differs")
        if not telegram_gateway_client.configured():
            raise ValueError("approved gateway not configured")
        relay_uid = pwd.getpwnam("bybitscanner").pw_uid
        def current():
            if _read_config(config) != c:
                raise ValueError("approval configuration changed")
            return verify_release(root, manifest_path)
        def send(text, keyboard):
            result = telegram_gateway_client.send_text(c["owner_id"], text, reply_markup=keyboard,
                                                       retry=False)
            return result["result"]["message_id"] if result.get("ok") is True else None
        def save(value):
            _atomic_file(state / "pending.json", grants._canonical(value), 0o600)
        return cycle(load=lambda: _private_json(state / "pending.json"),
                     save=save, prompts=grants.GrantLedger(state / "prompts"),
                     ledger=grants.GrantLedger(state / "grants"),
                     fetch=fetch_proposal, send=send,
                     receive=lambda nonce: relay.read_receipt(nonce, relay_uid=relay_uid),
                     installed_sha=current, callback_public=callback,
                     owner_id=c["owner_id"], bot_id=c["bot_id"],
                     approval_key=approval, diagnostic_issuer_public=diag_issuer,
                     diagnostic_responder_public=diag_responder.public_key(),
                     audience=c["audience"], clock=clock)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Protected owner release confirmation")
    parser.add_argument("--preflight", action="store_true",
                        help="read-only exact-release/local configuration proof")
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            print("OWNER_RELEASE_PREFLIGHT=" + preflight())
            return 0
        result = run_once()
        print("OWNER_RELEASE_APPROVAL=" + result)
        return 2 if result in ("SUBMISSION_UNPROVEN", "PROMPT_UNPROVEN") else 0
    except Exception:
        # Never expose keys, chat IDs, raw Telegram/GitHub bodies or host env.
        print("OWNER_RELEASE_PREFLIGHT=BLOCKED" if args.preflight
              else "OWNER_RELEASE_APPROVAL=BLOCKED_OR_DEFERRED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
