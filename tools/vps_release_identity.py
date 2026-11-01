"""PAPER backend release provenance for Gitless VPS installs.

Generate an exact tracked-file manifest from a verified Git release checkout
during immutable staging. On systemd startup, recheck installed file contents
against that manifest before exec'ing the PAPER backend in the *same* PID.
The manifest is only as trusted as its protected installation by the deployer;
an arbitrary, unverified marker is not evidence of Git commit ancestry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("/etc/bybitscanner/paper-release-manifest.json")
BACKEND = ("-m", "terminal.runtime.paper_http_server")
SHA40 = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseIdentityBlocked(ValueError):
    pass


def git_blob_hash(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def _safe_file(root: Path, name: str) -> Path:
    part = PurePosixPath(name)
    if (not name or part.is_absolute() or "\\" in name
            or any(piece in ("", ".", "..") for piece in name.split("/"))):
        raise ReleaseIdentityBlocked("invalid_manifest_path")
    path = root
    for piece in part.parts:
        path = path / piece
        if path.is_symlink():
            raise ReleaseIdentityBlocked("tracked_symlink_not_supported")
    if not path.is_file():
        raise ReleaseIdentityBlocked("tracked_file_missing")
    return path


def _validate_manifest(manifest: dict) -> tuple[str, dict[str, str]]:
    if not isinstance(manifest, dict) or set(manifest) != {"build_sha", "blobs"}:
        raise ReleaseIdentityBlocked("invalid_release_manifest")
    commit, blobs = manifest["build_sha"], manifest["blobs"]
    if not isinstance(commit, str) or SHA40.fullmatch(commit) is None:
        raise ReleaseIdentityBlocked("invalid_build_sha")
    if not isinstance(blobs, dict) or not blobs or len(blobs) > 100000:
        raise ReleaseIdentityBlocked("invalid_tracked_file_set")
    for name, digest in blobs.items():
        if not isinstance(name, str) or not isinstance(digest, str) or not SHA40.fullmatch(digest):
            raise ReleaseIdentityBlocked("invalid_tracked_blob_entry")
    if "terminal/runtime/paper_http_server.py" not in blobs or "tools/vps_release_identity.py" not in blobs:
        raise ReleaseIdentityBlocked("backend_or_verifier_not_tracked")
    return commit, blobs


def verify_release(root: Path = ROOT, manifest_path: Path = MANIFEST) -> str:
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ReleaseIdentityBlocked("release_manifest_missing_or_symlink")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        commit, blobs = _validate_manifest(manifest)
        for name, digest in blobs.items():
            if git_blob_hash(_safe_file(root, name).read_bytes()) != digest:
                raise ReleaseIdentityBlocked("tracked_content_mismatch")
        return commit
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseIdentityBlocked("release_manifest_or_source_unreadable") from exc


def create_manifest(root: Path, expected_sha: str) -> dict:
    """Used only in a deployment staging checkout with .git and fixed HEAD."""
    if SHA40.fullmatch(expected_sha) is None:
        raise ReleaseIdentityBlocked("invalid_expected_sha")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=root,
            capture_output=True, check=True, timeout=15,
        ).stdout.decode("ascii").strip()
        if head != expected_sha:
            raise ReleaseIdentityBlocked("staging_commit_mismatch")
        tree = subprocess.run(
            ["git", "ls-tree", "-rz", "--full-tree", "HEAD"], cwd=root,
            capture_output=True, check=True, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
        raise ReleaseIdentityBlocked("staging_git_unavailable") from exc
    blobs = {}
    for row in tree.split(b"\0"):
        if not row:
            continue
        try:
            metadata, name_bytes = row.split(b"\t", 1)
            mode, kind, sha = metadata.split(b" ")
            name = name_bytes.decode("utf-8")
            digest = sha.decode("ascii")
        except (ValueError, UnicodeError) as exc:
            raise ReleaseIdentityBlocked("invalid_git_tree") from exc
        if mode not in (b"100644", b"100755") or kind != b"blob":
            raise ReleaseIdentityBlocked("non_regular_tracked_file")
        if not SHA40.fullmatch(digest):
            raise ReleaseIdentityBlocked("invalid_git_blob_sha")
        if name in blobs:
            raise ReleaseIdentityBlocked("duplicate_git_tree_path")
        if git_blob_hash(_safe_file(root, name).read_bytes()) != digest:
            raise ReleaseIdentityBlocked("staging_tracked_content_mismatch")
        blobs[name] = digest
    _validate_manifest({"build_sha": head, "blobs": blobs})
    return {"build_sha": head, "blobs": blobs}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed PAPER release identity")
    sub = parser.add_subparsers(dest="mode", required=True)
    generate = sub.add_parser("generate", help="staging checkout only; print verified manifest")
    generate.add_argument("--expected-sha", required=True)
    sub.add_parser("verify", help="verify installed root against root-owned manifest")
    sub.add_parser("exec-backend", help="verify and replace this process with PAPER backend")
    args = parser.parse_args(argv)
    try:
        if args.mode == "generate":
            print(json.dumps(create_manifest(ROOT, args.expected_sha), sort_keys=True))
            return 0
        sha = verify_release()
        if args.mode == "verify":
            print("VERIFIED: tracked release contents and approved manifest match " + sha)
            return 0
        # An inherited SHA is not authority; replace it only after verifying
        # the exact installed files against the manifest in this process.
        env = os.environ.copy()
        env["BYBITSCANNER_BUILD_SHA"] = sha
        os.execve(sys.executable, [sys.executable, *BACKEND], env)
        return 3
    except ReleaseIdentityBlocked as exc:
        print("BLOCKED: " + str(exc) + "; PAPER backend not started", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
