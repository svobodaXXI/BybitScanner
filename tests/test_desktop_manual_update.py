"""Offline owner-clicked desktop update contracts; no network or VPS."""
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from research.local_replay_viewer import desktop_update as updates
from research.local_replay_viewer.simulator_self_update import (
    _copy_state, _unpack_release,
)
from tools import manager_self_update as manager

SHA = "a" * 40
ASSET = b"fake manager binary for digest contract"
DIGEST = hashlib.sha256(ASSET).hexdigest()


class Reply(io.BytesIO):
    pass


def opener(request, timeout=0):
    url = request.full_url
    tag = "desktop-" + SHA
    metadata = {
        updates.API + "/branches/" + updates.BRANCH: {"commit": {"sha": SHA}},
        updates.API + "/git/ref/tags/" + tag: {"object": {"type": "commit", "sha": SHA}},
        updates.API + "/releases/tags/" + tag: {
            "tag_name": tag, "draft": False, "prerelease": False, "assets": [{
                "name": updates.ASSETS["manager"], "state": "uploaded", "size": len(ASSET),
                "digest": "sha256:" + DIGEST,
                "browser_download_url": (
                    "https://github.com/svobodaXXI/BybitScanner/releases/download/"
                    + tag + "/" + updates.ASSETS["manager"]
                ),
            }],
        },
    }
    if url in metadata:
        return Reply(json.dumps(metadata[url]).encode())
    if url.endswith("/" + updates.ASSETS["manager"]):
        return Reply(ASSET)
    raise AssertionError("unexpected network target " + url)


def test_exact_stable_tag_and_github_digest_protect_download(tmp_path):
    asset = updates.find_asset("manager", opener=opener)
    assert asset.sha == SHA
    destination = tmp_path / "staged.exe"
    updates.fetch_verified(asset, destination, opener=opener)
    assert destination.read_bytes() == ASSET


def test_untrusted_release_ref_fails_without_download():
    def tampered(request, timeout=0):
        if "/git/ref/tags/" in request.full_url:
            return Reply(json.dumps({"object": {"type": "commit", "sha": "b" * 40}}).encode())
        return opener(request, timeout=timeout)
    with pytest.raises(updates.UpdateBlocked, match="release_tag_commit_mismatch"):
        updates.find_asset("manager", opener=tampered)


def test_untrusted_asset_hash_is_rejected_and_staging_removed(tmp_path):
    asset = updates.find_asset("manager", opener=opener)
    changed = updates.ReleaseAsset(asset.sha, asset.name, asset.url, asset.size, "f" * 64)
    out = tmp_path / "staged.exe"
    with pytest.raises(updates.UpdateBlocked, match="download_hash_mismatch"):
        updates.fetch_verified(changed, out, opener=opener)
    assert not out.exists()


def test_never_replace_existing_user_download(tmp_path):
    asset = updates.find_asset("manager", opener=opener)
    existing = tmp_path / "staged.exe"
    existing.write_bytes(b"owner file")
    with pytest.raises(FileExistsError):
        updates.fetch_verified(asset, existing, opener=opener)
    # A failed download must NEVER unlink an existing file.
    assert existing.read_bytes() == b"owner file"


def _zip(tmp_path, entries):
    archive = tmp_path / "viewer.zip"
    with ZipFile(archive, "w") as output:
        for name, body in entries.items():
            output.writestr(name, body)
    return archive


def test_simulator_archive_validates_exact_marker(tmp_path):
    archive = _zip(tmp_path, {
        "MachineTime/desktop-build-sha.txt": SHA + "\n",
        "MachineTime/server.py": "# server",
        "MachineTime/START_LOCAL.cmd": "@echo off",
        "MachineTime/dist/replay.html": "<html/>",
    })
    dest = tmp_path / "release"
    dest.mkdir()
    _unpack_release(archive, dest, sha=SHA)
    assert (dest / "desktop-build-sha.txt").read_text().strip() == SHA


@pytest.mark.parametrize("name", [
    "MachineTime/../sensitive.txt",
    "MachineTime/simulator-v2-data/manifest.json",
    "MachineTime/paper-episode-facts/episode.json",
])
def test_simulator_rejects_user_state_overwrite_and_traversal(tmp_path, name):
    archive = _zip(tmp_path, {name: "untrusted"})
    dest = tmp_path / "target"
    dest.mkdir()
    with pytest.raises(updates.UpdateBlocked):
        _unpack_release(archive, dest, sha=SHA)
    assert not (tmp_path / "sensitive.txt").exists()


def test_simulator_copy_preserves_exact_user_data(tmp_path):
    source = tmp_path / "state"
    source.mkdir()
    (source / "owner-facts.json").write_bytes(b'{"episode":"original"}')
    target = tmp_path / "new-state"
    _copy_state(source, target)
    assert (target / "owner-facts.json").read_bytes() == b'{"episode":"original"}'
    assert (source / "owner-facts.json").read_bytes() == b'{"episode":"original"}'


def test_simulator_rejects_symlinked_owner_data(tmp_path):
    source = tmp_path / "state"
    source.mkdir()
    other = tmp_path / "other"
    other.write_bytes(b"owner")
    (source / "alias").symlink_to(other)
    with pytest.raises(updates.UpdateBlocked, match="local_data_symlink"):
        _copy_state(source, tmp_path / "copy")
    assert other.read_bytes() == b"owner"


def test_manager_update_is_not_a_vps_operation():
    assert "gh release" not in manager.HELPER.lower()
    assert "systemctl" not in manager.HELPER.lower()
    assert "ssh " not in manager.HELPER.lower()
    assert "Get-FileHash" in manager.HELPER
    assert "Wait-Process" in manager.HELPER
