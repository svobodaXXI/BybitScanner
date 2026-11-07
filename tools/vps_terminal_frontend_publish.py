"""Publish a version-pinned Vite bundle to the existing Nginx static root.

Frontend-only: never calls STOP, systemd, PAPER APIs, SQL or trading routes.
Assets are installed before the atomically switched index; old assets survive
to serve open browser tabs. The first adoption needs a separately observed
SHA-256 for the current index, so unrelated owner files cannot be overwritten.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat

from tools.vps_gitless_release_activate import _atomic_file, _atomic_new_file, _sync_directory
from tools.vps_release_identity import verify_release

WEBROOT = Path("/var/www/bybitscanner")
TRANSACTIONS = Path("/var/lib/bybitscanner-release-transactions")
RECEIPT = ".bybitscanner-frontend-release.json"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ASSET_REF = re.compile(r"""(?:src|href)=["']/?(assets/[^"'?#]+)["']""")
MAX_TOTAL_BYTES = 100 * 1024 * 1024


class FrontendPublishBlocked(ValueError):
    pass


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise FrontendPublishBlocked(reason)


def _trusted_directory(path: Path, uid: int) -> None:
    _require(path.is_dir() and not path.is_symlink(), "unsafe_frontend_directory")
    info = path.stat()
    _require(info.st_uid == uid and not info.st_mode & 0o022, "untrusted_frontend_directory")


def _content(path: Path) -> bytes:
    _require(path.is_file() and not path.is_symlink(), "frontend_file_not_regular")
    _require(path.stat().st_size <= MAX_TOTAL_BYTES, "frontend_file_too_large")
    return path.read_bytes()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _paths(bundle: Path) -> dict[str, bytes]:
    _require(bundle.is_dir() and not bundle.is_symlink(), "frontend_bundle_missing")
    files: dict[str, bytes] = {}
    for path in bundle.rglob("*"):
        relative = path.relative_to(bundle).as_posix()
        parts = PurePosixPath(relative).parts
        _require(all(re.fullmatch(r"[A-Za-z0-9_.-]+", p) for p in parts),
                 "unsafe_frontend_filename")
        if path.is_dir():
            _require(not path.is_symlink(), "frontend_bundle_symlink")
            continue
        _require(not path.is_symlink() and path.is_file(), "frontend_bundle_symlink")
        if relative == "frontend-release.json":
            continue
        _require(relative == "index.html" or
                 (len(parts) == 2 and parts[0] == "assets" and parts[1] not in (".", "..")),
                 "unexpected_frontend_file")
        files[relative] = _content(path)
    _require("index.html" in files and any(p.endswith(".js") for p in files),
             "frontend_entry_or_javascript_missing")
    _require(sum(len(data) for data in files.values()) <= MAX_TOTAL_BYTES,
             "frontend_bundle_too_large")
    html = files["index.html"].decode("utf-8")
    references = ASSET_REF.findall(html)
    _require(any(x.endswith(".js") for x in references), "frontend_index_without_script")
    _require(all(name in files for name in references), "frontend_index_asset_missing")
    return files


def inspect_bundle(bundle: Path, sha: str) -> dict[str, bytes]:
    _require(bool(SHA40.fullmatch(sha)), "invalid_frontend_target_sha")
    files = _paths(bundle)
    manifest = json.loads(_content(bundle / "frontend-release.json"))
    _require(isinstance(manifest, dict) and set(manifest) == {"source_sha", "files"},
             "invalid_frontend_build_manifest")
    _require(manifest["source_sha"] == sha, "frontend_source_sha_mismatch")
    actual = {name: _digest(raw) for name, raw in files.items()}
    _require(manifest["files"] == actual, "frontend_bundle_content_mismatch")
    return files


def publish_frontend(
    sha: str, *, bundle: Path, root: Path = Path("/opt/BybitScanner"),
    webroot: Path = WEBROOT, expected_index_sha256: str | None = None,
    uid: int = 0, release_verifier=verify_release,
    transactions: Path = TRANSACTIONS,
) -> str:
    """An owner-authorized static-only switch for an already-installed release.

    The release SHA must be exact; this command does not install a release or
    infer the build's provenance from filenames. Caller supplies a checked
    build artifact from that exact source SHA.
    """
    _require(os.geteuid() == uid, "frontend_publish_requires_owner")
    _require(release_verifier(root) == sha, "frontend_backend_release_mismatch")
    _trusted_directory(webroot.parent, uid)
    _trusted_directory(webroot, uid)
    _trusted_directory(transactions, uid)
    journal = transactions / sha
    _trusted_directory(journal, uid)
    _require(not (webroot / "assets").is_symlink(), "unsafe_frontend_assets_path")
    files = inspect_bundle(bundle, sha)
    index = webroot / "index.html"
    _require(index.is_file() and not index.is_symlink(), "existing_frontend_index_missing")
    original = _content(index)
    old_digest = _digest(original)
    new_digest = _digest(files["index.html"])
    receipt_path = webroot / RECEIPT
    if receipt_path.exists() or receipt_path.is_symlink():
        _require(receipt_path.stat().st_uid == uid and
                 not receipt_path.stat().st_mode & 0o022,
                 "frontend_receipt_owner_unproven")
        receipt = json.loads(_content(receipt_path))
        _require(set(receipt) == {"source_sha", "index_sha256", "previous_index_sha256"},
                 "frontend_receipt_invalid")
        _require(bool(SHA40.fullmatch(receipt["source_sha"])) and
                 bool(SHA256.fullmatch(receipt["index_sha256"])) and
                 bool(SHA256.fullmatch(receipt["previous_index_sha256"])),
                 "frontend_receipt_untrusted")
        prior_digest = receipt["index_sha256"]
    else:
        _require(isinstance(expected_index_sha256, str)
                 and SHA256.fullmatch(expected_index_sha256) is not None,
                 "first_frontend_adoption_requires_observed_index_sha256")
        prior_digest = expected_index_sha256
    _require(old_digest in (prior_digest, new_digest),
             "frontend_index_changed_since_preflight")

    # An existing asset is never overwritten, even if an unrelated owner wrote
    # that filename. Hashed old assets are deliberately not deleted.
    for name, data in sorted(files.items()):
        if name == "index.html":
            continue
        target = webroot / name
        _require(not target.parent.is_symlink(), "unsafe_frontend_asset_parent")
        if target.exists() or target.is_symlink():
            _require(_content(target) == data, "frontend_asset_collision:" + name)

    backup = journal / "frontend-previous-index.html"
    if backup.exists() or backup.is_symlink():
        _require(_digest(_content(backup)) == prior_digest,
                 "frontend_previous_index_backup_mismatch")
    else:
        _require(old_digest == prior_digest, "frontend_initial_index_not_pinned")
        _atomic_new_file(backup, original, 0o600)

    assets = webroot / "assets"
    if not assets.exists():
        assets.mkdir(mode=0o755)
        _sync_directory(webroot)
    _trusted_directory(assets, uid)
    for name, data in sorted(files.items()):
        if name == "index.html":
            continue
        destination = webroot / name
        if not destination.exists():
            _atomic_new_file(destination, data, 0o644)

    if old_digest != new_digest:
        _atomic_file(index, files["index.html"], 0o644)
    _require(_digest(_content(index)) == new_digest, "frontend_index_write_unproven")
    payload = json.dumps({
        "source_sha": sha, "index_sha256": new_digest,
        "previous_index_sha256": prior_digest,
    }, sort_keys=True).encode("utf-8")
    _atomic_file(receipt_path, payload, 0o644)
    _sync_directory(webroot)
    return "FRONTEND_READY: exact static bundle installed; no PAPER runtime change"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static-only authenticated Terminal UI publication")
    parser.add_argument("sha")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-index-sha256")
    args = parser.parse_args(argv)
    try:
        print(publish_frontend(args.sha, bundle=args.bundle,
                               expected_index_sha256=args.expected_index_sha256))
        return 0
    except (FrontendPublishBlocked, OSError, ValueError, UnicodeError) as exc:
        print("BLOCKED: frontend_publish:" + type(exc).__name__ + ":" + str(exc)[:180])
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
