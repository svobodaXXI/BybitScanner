"""Lightweight, opt-in local version/update discovery for Machine Time.

Only a direct click causes one bounded GitHub GET. No polling, installers,
background agents, private credentials, PAPER API or file mutation.
A release download/install is intentionally not advertised before the
separate signed/verified release and user-data-preserving switch exist.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BUILD_MANIFEST = "machine-time-build.json"
BUILD_SCHEMA = "MACHINE_TIME_BUILD_V1"
ASSET_NAME = "machine-time-windows.zip"
GITHUB_RELEASES = "https://api.github.com/repos/svobodaXXI/BybitScanner/releases?per_page=10"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TAG = re.compile(r"machine-time-([0-9a-f]{40})\Z")
MAX_META_BYTES = 128 * 1024
MAX_ASSET_SIZE = 300 * 1024 * 1024


def installed_build(folder: Path) -> dict[str, object]:
    """Report evidence honestly; do not infer a version from a folder name."""
    manifest = folder / BUILD_MANIFEST
    server = folder / "server.py"
    unknown: dict[str, object] = {
        "installed_sha": None, "build_status": "UNVERIFIED",
    }
    if manifest.is_symlink() or server.is_symlink() or not manifest.is_file() or not server.is_file():
        return unknown
    try:
        if manifest.stat().st_size > 4096:
            return unknown
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if (not isinstance(data, dict) or data.get("schema") != BUILD_SCHEMA
            or not isinstance(data.get("source_sha"), str)
            or not _SHA.fullmatch(data["source_sha"])
            or not isinstance(data.get("server_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", data["server_sha256"])):
            return unknown
        digest = hashlib.sha256(server.read_bytes()).hexdigest()
        if digest != data["server_sha256"]:
            return unknown
        return {"installed_sha": data["source_sha"], "build_status": "MANIFEST_HASH_MATCH"}
    except (OSError, ValueError, TypeError):
        return unknown


def _parse_releases(raw: object, installed_sha: str | None) -> dict[str, object]:
    if not isinstance(raw, list):
        raise ValueError("invalid_github_release_response")
    # Only the dedicated local-Windows track; never the main VPS release.
    for release in raw:
        if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
            continue
        tag = release.get("tag_name")
        match = _TAG.fullmatch(tag) if isinstance(tag, str) else None
        if not match:
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        usable = []
        for asset in assets:
            if not isinstance(asset, dict) or asset.get("name") != ASSET_NAME or asset.get("state") != "uploaded":
                continue
            digest = asset.get("digest")
            size = asset.get("size")
            if (not isinstance(digest, str) or not _DIGEST.fullmatch(digest)
                or type(size) is not int or not 1 <= size <= MAX_ASSET_SIZE):
                continue
            usable.append(asset)
        if len(usable) != 1:
            continue
        release_sha = match.group(1)
        if release_sha == installed_sha:
            return {"status": "CURRENT", "available_sha": release_sha}
        # Do not claim a newer version based on a different SHA alone.
        return {"status": "PUBLISHED_CANDIDATE", "available_sha": release_sha,
                "message": "Опубликован пакет. Автоустановка пока недоступна: проверка и переключение версий ещё не реализованы."}
    return {"status": "NO_COMPATIBLE_RELEASE"}


def check_github_release(installed_sha: str | None, *, open_url=urlopen) -> dict[str, object]:
    """Opt-in metadata only, 8-second timeout and strict response-size bound."""
    request = Request(
        GITHUB_RELEASES,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "BybitScanner-MachineTime-UpdateCheck/1.0",
        },
        method="GET",
    )
    try:
        with open_url(request, timeout=8) as response:
            body = response.read(MAX_META_BYTES + 1)
        if len(body) > MAX_META_BYTES:
            raise ValueError("github_metadata_too_large")
        return _parse_releases(json.loads(body), installed_sha)
    except HTTPError as exc:
        if exc.code == 404:
            return {"status": "NO_COMPATIBLE_RELEASE"}
        return {"status": "CHECK_UNAVAILABLE"}
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        return {"status": "CHECK_UNAVAILABLE"}
