"""Owner-clicked, fail-closed desktop release acquisition (no VPS/trading).

This module is bundled in both local applications.  No background polling.
A desktop release is eligible only for the exact stable branch SHA, with a
GitHub release tag naming that SHA and GitHub's own SHA-256 asset digest.
No arbitrary URL, branch archive, Git command, token or unverified overwrite.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

API = "https://api.github.com/repos/svobodaXXI/BybitScanner"
BRANCH = "stable/adfb50b-forward"
ASSETS = {
    "manager": "BybitScanner-VPS-Manager.exe",
    "simulator": "BybitScanner-MachineTime.zip",
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")
MAX_DOWNLOAD = 180_000_000
# GitHub Compare includes the full files/patches array on page 1, which can
# exceed the bounded 256 KB metadata reader for older installed releases.
# Page 2 with one commit/page still returns status/ahead_by/behind_by, even
# when the comparison has zero or one commit, without the files array.
COMPARE_SUMMARY_PAGE = "?per_page=1&page=2"


class UpdateBlocked(ValueError):
    pass


@dataclass(frozen=True)
class ReleaseAsset:
    sha: str
    name: str
    url: str
    size: int
    digest: str


def _json(url: str, *, opener=urlopen) -> dict:
    if not url.startswith(API + "/"):
        raise UpdateBlocked("untrusted_release_metadata")
    request = Request(url, headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "BybitScanner-Desktop-Updater"})
    try:
        with opener(request, timeout=12) as response:
            payload = response.read(256_001)
    except (OSError, TimeoutError) as exc:
        raise UpdateBlocked("release_metadata_unavailable") from exc
    if len(payload) > 256_000:
        raise UpdateBlocked("release_metadata_too_large")
    try:
        result = json.loads(payload)
    except (TypeError, ValueError) as exc:
        raise UpdateBlocked("invalid_release_metadata") from exc
    if not isinstance(result, (dict, list)):
        raise UpdateBlocked("invalid_release_metadata")
    return result


def find_asset(kind: str, *, opener=urlopen) -> ReleaseAsset:
    if kind not in ASSETS:
        raise UpdateBlocked("invalid_application")
    branch = _json(API + "/branches/" + BRANCH, opener=opener)
    if not isinstance(branch, dict):
        raise UpdateBlocked("stable_head_unproven")
    head = branch.get("commit", {}).get("sha") if isinstance(branch.get("commit"), dict) else None
    if not isinstance(head, str) or not SHA.fullmatch(head):
        raise UpdateBlocked("stable_head_unproven")
    # Robot/docs merges move stable frequently. The latest *desktop* release
    # remains eligible if its exact commit is still an ancestor of stable.
    published = _json(API + "/releases?per_page=30", opener=opener)
    if not isinstance(published, list) or len(published) > 30:
        raise UpdateBlocked("desktop_release_list_untrusted")
    candidates = [r for r in published if isinstance(r, dict) and
                  isinstance(r.get("tag_name"), str) and
                  re.fullmatch(r"desktop-[0-9a-f]{40}", r["tag_name"])]
    if not candidates:
        raise UpdateBlocked("desktop_release_not_published")
    release = candidates[0]
    tag = release["tag_name"]
    sha = tag.removeprefix("desktop-")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        raise UpdateBlocked("release_tag_untrusted")
    tag_ref = _json(API + "/git/ref/tags/" + tag, opener=opener)
    if not isinstance(tag_ref, dict):
        raise UpdateBlocked("release_tag_commit_mismatch")
    ref_object = tag_ref.get("object")
    if (not isinstance(ref_object, dict) or ref_object.get("type") != "commit"
            or ref_object.get("sha") != sha):
        raise UpdateBlocked("release_tag_commit_mismatch")
    comparison = _json(API + "/compare/" + sha + "..." + head
                       + COMPARE_SUMMARY_PAGE, opener=opener)
    if (not isinstance(comparison, dict)
            or comparison.get("status") not in ("ahead", "identical")
            or comparison.get("behind_by") != 0):
        raise UpdateBlocked("desktop_release_not_ancestor_of_stable")
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > 30:
        raise UpdateBlocked("release_assets_invalid")
    matches = [a for a in assets if isinstance(a, dict) and a.get("name") == ASSETS[kind]]
    if len(matches) != 1:
        raise UpdateBlocked("desktop_asset_not_published")
    a = matches[0]
    url = f"https://github.com/svobodaXXI/BybitScanner/releases/download/{tag}/{ASSETS[kind]}"
    digest = a.get("digest")
    size = a.get("size")
    if (a.get("browser_download_url") != url or not isinstance(digest, str)
            or not DIGEST.fullmatch(digest) or type(size) is not int
            or not 1 <= size <= MAX_DOWNLOAD or a.get("state") != "uploaded"):
        raise UpdateBlocked("desktop_asset_attestation_unproven")
    return ReleaseAsset(sha, ASSETS[kind], url, size, digest.removeprefix("sha256:"))


def fetch_verified(asset: ReleaseAsset, destination: Path, *, opener=urlopen) -> None:
    """Bounded download to an *absent* staging file. No target replacement."""
    expected = f"https://github.com/svobodaXXI/BybitScanner/releases/download/desktop-{asset.sha}/{asset.name}"
    if (asset.url != expected or not SHA.fullmatch(asset.sha)
            or asset.name not in ASSETS.values()
            or not re.fullmatch("[0-9a-f]{64}", asset.digest)
            or not 1 <= asset.size <= MAX_DOWNLOAD):
        raise UpdateBlocked("invalid_download_attestation")
    created = False
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as out:
            created = True
            stream = opener(Request(asset.url, headers={"User-Agent": "BybitScanner-Desktop-Updater"}),
                            timeout=30)
            with stream:
                digest = hashlib.sha256()
                size = 0
                while True:
                    piece = stream.read(1024 * 1024)
                    if not piece:
                        break
                    size += len(piece)
                    if size > asset.size or size > MAX_DOWNLOAD:
                        raise UpdateBlocked("download_exceeds_manifest")
                    digest.update(piece)
                    out.write(piece)
            out.flush()
        if size != asset.size or digest.hexdigest() != asset.digest:
            raise UpdateBlocked("download_hash_mismatch")
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise



def require_forward_update(installed_sha: str, release_sha: str, *, opener=urlopen) -> None:
    """Known installed releases may advance only to descendants, not downgrade."""
    if not SHA.fullmatch(installed_sha) or not SHA.fullmatch(release_sha):
        raise UpdateBlocked("installed_desktop_version_untrusted")
    if installed_sha == release_sha:
        raise UpdateBlocked("desktop_already_current")
    comparison = _json(API + "/compare/" + installed_sha + "..." + release_sha
                       + COMPARE_SUMMARY_PAGE, opener=opener)
    if (not isinstance(comparison, dict)
            or comparison.get("status") != "ahead"
            or comparison.get("behind_by") != 0):
        raise UpdateBlocked("desktop_downgrade_or_diverged")
