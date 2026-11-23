"""Offline owner-clicked desktop update contracts; no network or VPS."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import subprocess
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
        updates.API + "/compare/" + SHA + "..." + SHA + updates.COMPARE_SUMMARY_PAGE: {
            "status": "identical", "behind_by": 0, "ahead_by": 0,
        },
        updates.API + "/releases?per_page=5&page=1": [{
            "tag_name": tag, "draft": False, "prerelease": False,
            "published_at": "2026-11-22T06:02:43Z", "assets": [{
                "name": updates.ASSETS["manager"], "state": "uploaded", "size": len(ASSET),
                "digest": "sha256:" + DIGEST,
                "browser_download_url": (
                    "https://github.com/svobodaXXI/BybitScanner/releases/download/"
                    + tag + "/" + updates.ASSETS["manager"]
                ),
            }],
        }],
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


def test_manager_bootstrap_probe_is_local_before_replacement(tmp_path):
    """Existing invalid UUID contract returns 2 before any SSH or GUI window."""
    exe = tmp_path / "BybitScanner-VPS-Manager.exe"
    exe.write_bytes(ASSET)
    run = Mock(return_value=SimpleNamespace(returncode=2))
    manager.probe_manager_bootstrap(exe, run=run)
    command = run.call_args.args[0]
    assert command == [str(exe), "--operation", "status", "--request-id",
                       "invalid", "--host", "127.0.0.1", "--user", "root"]
    assert run.call_args.kwargs["timeout"] == 30
    assert run.call_args.kwargs["stdin"] is subprocess.DEVNULL
    assert run.call_args.kwargs["check"] is False
    assert not any("submit" in part for part in command)


@pytest.mark.parametrize("outcome", [
    SimpleNamespace(returncode=1), SimpleNamespace(returncode=255),
    SimpleNamespace(returncode=0),
    OSError("missing DLL"), subprocess.TimeoutExpired("manager", 30),
])
def test_manager_bootstrap_unknown_never_advances_to_replacement(tmp_path, outcome):
    exe = tmp_path / "BybitScanner-VPS-Manager.exe"
    exe.write_bytes(ASSET)
    if isinstance(outcome, Exception):
        run = Mock(side_effect=outcome)
    else:
        run = Mock(return_value=outcome)
    with pytest.raises(updates.UpdateBlocked, match="manager_new_exe_bootstrap_unproven"):
        manager.probe_manager_bootstrap(exe, run=run)
    assert exe.read_bytes() == ASSET
    run.assert_called_once()


def test_local_update_requires_explicit_same_origin_browser_click(tmp_path):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from research.local_replay_viewer.server import handler_factory, UPDATE_STATE

    host = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(tmp_path))
    worker = Thread(target=host.serve_forever, daemon=True)
    worker.start()
    base = f"http://127.0.0.1:{host.server_address[1]}"
    try:
        status = Request(base + "/local-replay/desktop-update/status")
        with urlopen(status, timeout=5) as reply:
            assert json.loads(reply.read())["status"] in ("idle", "blocked", "checking")
        request = Request(
            base + "/local-replay/desktop-update",
            data=b"{}", method="POST", headers={
                "Content-Type": "application/json",
                "X-Local-Desktop-Update": "explicit-click",
                "Origin": "https://attacker.example",
            },
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=5)
        assert error.value.code == 403
        assert UPDATE_STATE["status"] != "restarting"
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=5)


def test_later_unrelated_stable_commits_do_not_invalidate_desktop_release():
    newer = "b" * 40

    def advanced(request, timeout=0):
        url = request.full_url
        if url == updates.API + "/branches/" + updates.BRANCH:
            return Reply(json.dumps({"commit": {"sha": newer}}).encode())
        if url == updates.API + "/compare/" + SHA + "..." + newer + updates.COMPARE_SUMMARY_PAGE:
            return Reply(json.dumps({"status": "ahead", "behind_by": 0, "ahead_by": 1}).encode())
        return opener(request, timeout=timeout)

    assert updates.find_asset("manager", opener=advanced).sha == SHA


def test_divergent_releases_fail_closed():
    newer = "b" * 40

    def diverged(request, timeout=0):
        url = request.full_url
        if url == updates.API + "/branches/" + updates.BRANCH:
            return Reply(json.dumps({"commit": {"sha": newer}}).encode())
        if url == updates.API + "/compare/" + SHA + "..." + newer + updates.COMPARE_SUMMARY_PAGE:
            return Reply(json.dumps({"status": "diverged", "behind_by": 1,
                                     "ahead_by": 1}).encode())
        return opener(request, timeout=timeout)

    with pytest.raises(updates.UpdateBlocked, match="desktop_release_not_ancestor_of_stable"):
        updates.find_asset("manager", opener=diverged)




def test_large_historical_compare_uses_summary_page_without_files():
    """A large Compare response must never block an otherwise valid update."""
    old = "0" * 40
    expected = (updates.API + "/compare/" + old + "..." + SHA
                + updates.COMPARE_SUMMARY_PAGE)
    requested = []

    def comparison(request, timeout=0):
        url = request.full_url
        requested.append(url)
        if url != expected:
            # GitHub's normal first Compare page may exceed the 256 KB limit.
            return Reply(b"x" * 256_001)
        return Reply(json.dumps({
            "status": "ahead", "ahead_by": 400, "behind_by": 0,
            "total_commits": 400,
        }).encode())

    updates.require_forward_update(old, SHA, opener=comparison)
    assert requested == [expected]


def test_known_installed_version_cannot_downgrade():
    old = "b" * 40
    def compare(request, timeout=0):
        if request.full_url == updates.API + "/compare/" + old + "..." + SHA + updates.COMPARE_SUMMARY_PAGE:
            return Reply(json.dumps({"status": "behind", "behind_by": 1,
                                     "ahead_by": 0}).encode())
        return opener(request, timeout=timeout)
    with pytest.raises(updates.UpdateBlocked, match="desktop_downgrade_or_diverged"):
        updates.require_forward_update(old, SHA, opener=compare)


def test_known_installed_version_can_advance():
    old = "0" * 40
    def compare(request, timeout=0):
        if request.full_url == updates.API + "/compare/" + old + "..." + SHA + updates.COMPARE_SUMMARY_PAGE:
            return Reply(json.dumps({"status": "ahead", "behind_by": 0,
                                     "ahead_by": 5}).encode())
        return opener(request, timeout=timeout)
    updates.require_forward_update(old, SHA, opener=compare)

def test_desktop_publication_owner_request_is_exact_and_one_shot():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "desktop-release-packages.yml").read_text(encoding="utf-8")
    assert "  workflow_dispatch:\n  push:" in workflow
    assert "- 'desktop-publish/*'" in workflow
    assert "- '.github/desktop-publish-request.txt'" in workflow
    assert "github.actor == 'svobodaXXI'" in workflow
    assert "DESKTOP_REQUEST_SHA_MISMATCH" in workflow
    assert "DESKTOP_REQUEST_UNEXPECTED_CHANGES" in workflow
    assert "DESKTOP_REQUEST_CONTENT_MISMATCH" in workflow
    assert "STABLE_MOVED_BEFORE_PUBLISH" in workflow
    assert "DESKTOP_TAG_ALREADY_EXISTS" in workflow
    assert workflow.count("gh release create") == 1


def test_desktop_release_publication_uses_scoped_app_workflows_permission():
    """An exact stable workflow-delta release requires workflows:write.

    The ordinary GITHUB_TOKEN stays read-only for validation; only the
    release creation step receives the short-lived repository-scoped token.
    """
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows"
                / "desktop-release-packages.yml").read_text(encoding="utf-8")
    assert "DESKTOP_RELEASE_APP_NOT_CONFIGURED" in workflow
    gate = workflow.index("Verify repository-scoped release identity is configured")
    build = workflow.index("Build local replay static UI")
    smoke = workflow.index("Smoke-test packaged Manager Python DLL")
    token_step = workflow.index("Mint short-lived repository-scoped release token")
    release = workflow.index("Publish owner-approved desktop release")
    assert gate < build < smoke < token_step < release

    scoped = workflow[token_step:release]
    assert "uses: actions/create-github-app-token@v3" in scoped
    assert "client-id: ${{ vars.DESKTOP_RELEASE_APP_CLIENT_ID }}" in scoped
    assert "private-key: ${{ secrets.DESKTOP_RELEASE_APP_PRIVATE_KEY }}" in scoped
    assert "permission-contents: write" in scoped
    assert "permission-workflows: write" in scoped
    assert not any(line.strip().startswith(("owner:", "repositories:"))
                   for line in scoped.splitlines())

    publication = workflow[release:]
    assert "GH_TOKEN: ${{ steps.desktop_release_token.outputs.token }}" in publication
    assert "GH_TOKEN: ${{ github.token }}" not in publication
    assert publication.count("gh release create") == 1
    assert "--target $env:DESKTOP_SHA" in publication
    assert "STABLE_MOVED_BEFORE_PUBLISH" in publication


def test_publication_order_not_api_list_order():
    def reordered(request, timeout=0):
        if request.full_url == updates.API + "/releases?per_page=5&page=1":
            latest = json.loads(opener(request, timeout=timeout).read())[0]
            older = {**latest, "tag_name": "desktop-" + "b" * 40,
                     "published_at": "2026-11-22T04:41:16Z"}
            draft = {**latest, "tag_name": "desktop-" + "c" * 40,
                     "draft": True, "published_at": None}
            return Reply(json.dumps([older, draft, latest]).encode())
        return opener(request, timeout=timeout)

    assert updates.find_asset("manager", opener=reordered).sha == SHA


@pytest.mark.parametrize("stamp", [None, "bad-date", "2026-02-30T01:00:00Z",
                                  "2026-11-22T06:02:43Z"])
def test_ambiguous_or_invalid_publication_never_selects_older_release(stamp):
    def unordered(request, timeout=0):
        if request.full_url == updates.API + "/releases?per_page=5&page=1":
            latest = json.loads(opener(request, timeout=timeout).read())[0]
            other = {**latest, "tag_name": "desktop-" + "b" * 40,
                     "published_at": stamp}
            return Reply(json.dumps([other, latest]).encode())
        return opener(request, timeout=timeout)

    with pytest.raises(updates.UpdateBlocked, match="desktop_release_publication_"):
        updates.find_asset("manager", opener=unordered)


def test_large_release_catalog_paginates_without_losing_newest_publication():
    """Aggregate >256 KB must not force reinstall, rollback or older selection."""
    latest = json.loads(opener(
        SimpleNamespace(full_url=updates.API + "/releases?per_page=5&page=1"),
    ).read())[0]
    older = [{**latest, "tag_name": "desktop-" + format(i + 1, "040x"),
              "published_at": "2026-11-21T06:02:43Z",
              "body": "x" * 30000} for i in range(10)]
    # 11 metadata entries exceed the old single-response 256 KB limit.
    assert len(json.dumps(older + [latest]).encode()) > 256000
    requested = []

    def paged(request, timeout=0):
        url = request.full_url
        if "/releases?per_page=5&page=" in url:
            requested.append(url)
            page = int(url.rsplit("=", 1)[-1])
            rows = {1: older[:5], 2: older[5:10], 3: [latest]}.get(page, [])
            return Reply(json.dumps(rows).encode())
        return opener(request, timeout=timeout)

    assert updates.find_asset("manager", opener=paged).sha == SHA
    assert requested == [updates.API + f"/releases?per_page=5&page={i}" for i in (1, 2, 3)]


def test_unavailable_later_release_page_blocks_instead_of_downgrading():
    """No release is trusted when the remaining catalog cannot be inspected."""
    latest = json.loads(opener(
        SimpleNamespace(full_url=updates.API + "/releases?per_page=5&page=1"),
    ).read())[0]

    def truncated(request, timeout=0):
        if request.full_url == updates.API + "/releases?per_page=5&page=1":
            return Reply(json.dumps([latest] * 5).encode())
        if request.full_url == updates.API + "/releases?per_page=5&page=2":
            raise OSError("offline")
        return opener(request, timeout=timeout)

    with pytest.raises(updates.UpdateBlocked, match="release_metadata_unavailable"):
        updates.find_asset("manager", opener=truncated)


def test_desktop_zip_imports_scoring_without_production_config(tmp_path, monkeypatch):
    """Regression for owner-PC HTTP 500: the release must bundle analyzer.scoring."""
    import subprocess
    import sys
    from zipfile import ZipFile
    from tools import build_machine_time_package as builder

    root = tmp_path / "source"
    viewer = root / "research" / "local_replay_viewer"
    (viewer / "dist").mkdir(parents=True)
    (viewer / "dist" / "replay.html").write_text("<!doctype html>", encoding="utf-8")
    (viewer / "trusted-statistics-origin.txt").write_text(
        "https://example.invalid\n", encoding="utf-8"
    )
    tracked = [
        "analyzer/__init__.py", "analyzer/scoring.py", "analyzer.py",
        "research/local_replay_viewer/trusted-statistics-origin.txt",
    ]
    for relative in tracked[:3]:
        dest = root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((builder.ROOT / relative).read_bytes())
    for name in (
        "server.py", "public_m5_cache.py", "protocol_launcher.py",
        "launch_bridge_agent.py", "desktop_update.py",
        "simulator_self_update.py", "paper_episode_local_store.py",
    ):
        (viewer / name).write_text("# entrypoint fixture\n", encoding="utf-8")

    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "VIEWER", viewer)
    monkeypatch.setattr(
        builder.subprocess, "check_output",
        lambda cmd: b"\0".join(path.encode() for path in tracked) + b"\0",
    )
    archive = tmp_path / "machine-time.zip"
    builder.package(archive, "a" * 40)
    with ZipFile(archive) as zf:
        names = set(zf.namelist())
        assert "MachineTime/analyzer/__init__.py" in names
        assert "MachineTime/analyzer/scoring.py" in names
        assert "MachineTime/analyzer.py" not in names
        assert "MachineTime/config.py" not in names
        zf.extractall(tmp_path / "unpacked")

    extracted = tmp_path / "unpacked" / "MachineTime"
    script = (
        "import sys; sys.path.insert(0, " + repr(str(extracted)) + "); "
        "from analyzer.scoring import calculate_final_score; "
        "assert calculate_final_score({'score': 60}, "
        "{'confirmation_score': 15}) == 75"
    )
    subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        check=True, capture_output=True, text=True, timeout=15,
    )
