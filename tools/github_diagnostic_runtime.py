"""Owner-protected host wiring. Fixed read-only GitHub diagnostic only."""
import argparse
import json
import os
from pathlib import Path
import stat
import time

from Crypto.Signature import eddsa
import requests

from tools import github_diagnostic_protocol as protocol
from tools.github_diagnostic_journal import DiagnosticJournal
from tools.github_diagnostic_transport import GitHubDiagnosticTransport
from tools.github_status_reporter import TOKEN_FILE, _get, _token
from tools.vps_release_identity import MANIFEST, ROOT, SHA40, git_blob_hash, _safe_file
from tools.vps_gitless_release_activate import _manifest, _trusted_file

CONFIG_DIR = Path("/etc/bybitscanner/github-diagnostic")
STATE_DIR = Path("/var/lib/bybitscanner-github-diagnostic")
NAMES = ("bybitscanner-github-diagnostic.service", "bybitscanner-github-diagnostic.timer")
SOURCES = ("tools/github_diagnostic_runtime.py", "tools/github_diagnostic_journal.py",
           "tools/github_diagnostic_protocol.py", "tools/github_diagnostic_transport.py",
           "tools/github_status_reporter.py", "tools/vps_release_identity.py",
           "tools/vps_gitless_release_activate.py")
PINNED = SOURCES + tuple("deploy/systemd/" + name for name in NAMES)


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
    with session_factory() as session:
        session.trust_env = False
        transport = GitHubDiagnosticTransport(request=session.request, token=token)
        return DiagnosticJournal(state_dir).run_once(
            enabled=True, issuer_public=issuer, responder_key=responder,
            audience=config["audience"], clock=clock, fetch=fetch, transport=transport)


def main():
    parser = argparse.ArgumentParser(description="Isolated owner diagnostics")
    parser.add_argument("--initialize", action="store_true",
                        help="explicit first-time durable journal creation; no polling")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError("root required")
        if args.initialize:
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
