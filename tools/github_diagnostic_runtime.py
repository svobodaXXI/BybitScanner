"""Owner-protected host wiring. Fixed read-only GitHub diagnostic only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from Crypto.Signature import eddsa
import requests

from tools import github_diagnostic_protocol as protocol
from tools.github_diagnostic_journal import DiagnosticJournal
from tools.github_diagnostic_transport import GitHubDiagnosticTransport
from tools.github_status_reporter import TOKEN_FILE, _get, _token
from tools.vps_release_identity import MANIFEST, ROOT, SHA40, git_blob_hash, _safe_file, verify_release
from tools.vps_gitless_release_activate import TRANSACTIONS, _atomic_file, _manifest, _trusted_file

CONFIG_DIR = Path("/etc/bybitscanner/github-diagnostic")
STATE_DIR = Path("/var/lib/bybitscanner-github-diagnostic")
NAMES = ("bybitscanner-github-diagnostic.service", "bybitscanner-github-diagnostic.timer")
SOURCES = ("tools/github_diagnostic_runtime.py", "tools/github_diagnostic_journal.py",
           "tools/github_diagnostic_protocol.py", "tools/github_diagnostic_transport.py",
           "tools/github_status_reporter.py", "tools/vps_release_identity.py",
           "tools/vps_gitless_release_activate.py")
PINNED = SOURCES + tuple("deploy/systemd/" + name for name in NAMES)
OWNER_SOURCES = ("tools/vps_owner_control.py", "tools/paper_maintenance.py",
                 "tools/runtime_intent.py", "tools/stop_robot_runtime.py")


def _config(directory=CONFIG_DIR, *, uid=0):
    meta = directory.lstat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != uid or meta.st_mode & 0o077:
        raise ValueError("unprotected diagnostic configuration directory")
    fd = os.open(directory / "config.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        meta = os.fstat(stream.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != uid or meta.st_mode & 0o077:
            raise ValueError("unprotected diagnostic configuration")
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("oversize diagnostic configuration")
    config = json.loads(raw, object_pairs_hook=protocol._unique_pairs)
    if (type(config) is not dict
            or set(config) != {"enabled", "release_sha", "audience", "issuer_public", "responder_seed"}
            or type(config["enabled"]) is not bool
            or type(config["release_sha"]) is not str or not SHA40.fullmatch(config["release_sha"])
            or type(config["audience"]) is not str or not protocol._HEX32.fullmatch(config["audience"])):
        raise ValueError("invalid diagnostic configuration")
    keys = []
    for name in ("issuer_public", "responder_seed"):
        value = config[name]
        if type(value) is not str or len(value) != 64:
            raise ValueError("invalid diagnostic key")
        raw = bytes.fromhex(value)
        if raw.hex() != value or len(raw) != 32:
            raise ValueError("noncanonical diagnostic key")
        keys.append(raw)
    issuer = eddsa.import_public_key(keys[0])
    responder = eddsa.import_private_key(keys[1])
    if issuer == responder.public_key():
        raise ValueError("diagnostic keys must be independent")
    return config, issuer, responder


def _pin_release(expected_sha, root=ROOT, manifest_path=MANIFEST, *, uid=0):
    manifest = _manifest(_trusted_file(manifest_path, uid))
    if manifest["build_sha"] != expected_sha:
        raise ValueError("diagnostic release pin differs")
    for name in PINNED:
        if manifest["blobs"].get(name) != git_blob_hash(_trusted_file(_safe_file(root, name), uid)):
            raise ValueError("diagnostic source not pinned")


def carry_forward_pin(*, root=ROOT, manifest_path=MANIFEST, transactions=TRANSACTIONS,
                      config_dir=CONFIG_DIR, state_dir=STATE_DIR,
                      unit_dir=Path("/etc/systemd/system"), uid=0):
    """Continue an existing opt-in across one proven ordinary owner UPDATE.

    No activation, polling, journal recreation or trading/service action.
    The canonical install lock and receipt bind the previous and new SHA.
    """
    from tools.paper_maintenance import _confirmed_stop_receipt

    if os.geteuid() != uid:
        raise ValueError("owner required")
    if not os.path.lexists(config_dir):
        return "SKIPPED_UNCONFIGURED"
    config, _, _ = _config(config_dir, uid=uid)
    if not config["enabled"]:
        return "SKIPPED_DISABLED"
    manifest = _manifest(_trusted_file(manifest_path, uid))
    old_sha, target = config["release_sha"], manifest["build_sha"]
    if old_sha == target:
        return "UNCHANGED"
    for directory, mask in ((transactions.parent, 0o022), (transactions, 0o077)):
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & mask:
            raise ValueError("unprotected release transaction directory")
    fd = os.open(transactions / ".release.lock", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077:
            raise ValueError("unprotected release lock")
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        journal = DiagnosticJournal(state_dir)
        with journal._lock():
            journal._load()
            # Never overwrite a concurrent disable or a different owner pin.
            if _config(config_dir, uid=uid)[0] != config:
                raise ValueError("diagnostic configuration changed")
            if _manifest(_trusted_file(manifest_path, uid)) != manifest:
                raise ValueError("installed manifest changed")
            transaction = transactions / target
            info = transaction.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077:
                raise ValueError("unprotected target transaction")
            previous = _manifest(_trusted_file(transaction / "old.json", uid))
            successor = _manifest(_trusted_file(transaction / "target.json", uid))
            if (previous["build_sha"] != old_sha or successor != manifest
                    or not _confirmed_stop_receipt(transactions, target, old_sha, uid=uid)):
                raise ValueError("ordinary owner transition unproven")
            if verify_release(root, manifest_path, require_protected_manifest=(uid == 0)) != target:
                raise ValueError("installed release unproven")
            _pin_release(target, root, manifest_path, uid=uid)
            info = unit_dir.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o022:
                raise ValueError("unprotected unit directory")
            for name in NAMES:
                rel = "deploy/systemd/" + name
                if (previous["blobs"].get(rel) != successor["blobs"].get(rel)
                        or git_blob_hash(_trusted_file(unit_dir / name, uid)) != successor["blobs"].get(rel)):
                    raise ValueError("diagnostic unit continuity unproven")
            # The existing root-only opt-in, independent keys and replay
            # receipts survive unchanged; only the exact release pin advances.
            if _config(config_dir, uid=uid)[0] != config:
                raise ValueError("diagnostic configuration changed")
            _atomic_file(config_dir / "config.json",
                         json.dumps({**config, "release_sha": target}).encode("ascii"), 0o600)
            return "ADVANCED"


def assert_enable_ready(expected_sha, *, root=ROOT, manifest_path=MANIFEST,
                        config_dir=CONFIG_DIR, state_dir=STATE_DIR, uid=0):
    config, _, _ = _config(config_dir, uid=uid)
    if not config["enabled"] or config["release_sha"] != expected_sha:
        raise ValueError("owner opt-in or release pin absent")
    _pin_release(expected_sha, root, manifest_path, uid=uid)
    journal = DiagnosticJournal(state_dir)
    with journal._lock():
        journal._load()


def run_once(*, config_dir=CONFIG_DIR, root=ROOT, manifest_path=MANIFEST,
             state_dir=STATE_DIR, token_file=TOKEN_FILE, clock=lambda: int(time.time()),
             fetch=_get, session_factory=requests.Session, uid=0):
    config, issuer, responder = _config(config_dir, uid=uid)
    if not config["enabled"]:
        return {"enabled": False, "observed": 0, "delivered": 0}
    _pin_release(config["release_sha"], root, manifest_path, uid=uid)
    token = _token(token_file)

    def owner_status(request, action, target):
        # An unknown or mixed release cannot produce an authoritative owner
        # outcome. Check the additional reader sources before importing them.
        unknown = dict(owner_request_id=request, owner_action=action, target_sha=target,
                       state="UNPROVEN", result="UNKNOWN", exit_code=None, postcheck="NOT_RUN")
        try:
            manifest = _manifest(_trusted_file(manifest_path, uid))
            if manifest["build_sha"] != config["release_sha"]:
                return unknown
            for rel in OWNER_SOURCES:
                if manifest["blobs"].get(rel) != git_blob_hash(_trusted_file(_safe_file(root, rel), uid)):
                    return unknown
            from tools.vps_owner_control import read_diagnostic_outcome
            return read_diagnostic_outcome(request, action, target)
        except Exception:
            return unknown

    with session_factory() as session:
        session.trust_env = False
        transport = GitHubDiagnosticTransport(request=session.request, token=token)
        return DiagnosticJournal(state_dir).run_once(
            enabled=True, issuer_public=issuer, responder_key=responder,
            audience=config["audience"], clock=clock, fetch=fetch, transport=transport,
            owner_status=owner_status)


def enable_diagnostic(expected_sha: str, *, root=ROOT, unit_dir=Path("/etc/systemd/system"),
                      manifest_path=MANIFEST, config_dir=CONFIG_DIR, state_dir=STATE_DIR,
                      token_file=TOKEN_FILE, uid=0, run=subprocess.run):
    """Explicit owner-only activation through paper_maintenance, not a request."""
    from tools.github_status_reporter import _enable_pinned_timer
    try:
        if os.geteuid() != uid:
            raise ValueError("owner required")
        _token(token_file)
        assert_enable_ready(expected_sha, root=root, manifest_path=manifest_path,
                            config_dir=config_dir, state_dir=state_dir, uid=uid)
    except Exception:
        return "BLOCKED: diagnostic_config_release_or_journal_unproven"
    return _enable_pinned_timer(expected_sha, names=NAMES, source_paths=SOURCES,
                                label="diagnostic", root=root, unit_dir=unit_dir,
                                manifest_path=manifest_path, uid=uid, run=run)


def main():
    parser = argparse.ArgumentParser(description="Isolated owner diagnostics")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--initialize", action="store_true",
                      help="explicit first-time durable journal creation; no polling")
    mode.add_argument("--carry-forward", action="store_true",
                      help="internal owner UPDATE pin continuation; no polling")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError("root required")
        if args.carry_forward:
            print("DIAGNOSTIC_PIN_CONTINUITY=" + carry_forward_pin())
        elif args.initialize:
            config, _, _ = _config()
            _pin_release(config["release_sha"])
            # Never recreate a missing receipt in an existing installation.
            STATE_DIR.mkdir(mode=0o700, exist_ok=False)
            DiagnosticJournal(STATE_DIR).initialize()
            print("DIAGNOSTIC_JOURNAL_INITIALIZED")
        else:
            report = run_once()
            print("DIAGNOSTIC_RUN=" + json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print("DIAGNOSTIC_BLOCKED_OR_DEFERRED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
