"""Offline release switch tests: real git manifests, isolated files and stopped fake units.

No VPS access, runtime process, trading DB, systemctl, or network mutations.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

import tools.vps_gitless_release_activate as activation
from tools.vps_release_identity import git_blob_hash
from tools.vps_systemd_unit_prepare import UNITS


def _git(root: Path, *argv: str) -> str:
    return subprocess.check_output(
        ["git", *argv], cwd=root, text=True, stderr=subprocess.DEVNULL,
    ).strip()


def _write(root: Path, name: str, content: bytes) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _fixture(tmp_path: Path, monkeypatch):
    stage = tmp_path / "staging"
    stage.mkdir()
    _git(stage, "init", "-q")
    _git(stage, "config", "user.email", "test@example.invalid")
    _git(stage, "config", "user.name", "Test")
    paths = ["terminal/runtime/paper_http_server.py",
             "tools/vps_release_identity.py",
             "tracked/user.txt"]
    paths += ["deploy/systemd/" + x for x in UNITS]
    for name in paths:
        _write(stage, name, ("old:" + name).encode())
    _git(stage, "add", ".")
    _git(stage, "commit", "-qm", "old")
    from tools.vps_release_identity import create_manifest
    old_sha = _git(stage, "rev-parse", "HEAD")
    old_manifest = create_manifest(stage, old_sha)
    root = tmp_path / "installed"
    shutil.copytree(stage, root, ignore=shutil.ignore_patterns(".git"))
    (root / "untracked-secret.conf").write_text("owner must keep")
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    for unit in UNITS:
        shutil.copy2(root / "deploy/systemd" / unit, unit_dir / unit)
    manifest_path = tmp_path / "paper-release-manifest.json"
    manifest_path.write_text(json.dumps(old_manifest))
    manifest_path.chmod(0o600)
    for name in paths:
        _write(stage, name, ("new:" + name).encode())
    _write(stage, "new_feature.py", b"new feature")
    _git(stage, "add", ".")
    _git(stage, "commit", "-qm", "new")
    sha = _git(stage, "rev-parse", "HEAD")
    transactions = tmp_path / "transactions"
    transactions.mkdir(mode=0o700)
    transactions.chmod(0o700)

    # Production verifier requires a root-owned manifest. The fixture instead
    # validates exact manifest file digests as an ordinary CI account.
    def verify(root, manifest, require_protected_manifest=True):
        obj = json.loads(manifest.read_text())
        for name, digest in obj["blobs"].items():
            assert git_blob_hash((root / name).read_bytes()) == digest
        return obj["build_sha"]
    monkeypatch.setattr(activation, "verify_release", verify)

    return dict(
        sha=sha, stage=stage, root=root, manifest=manifest_path,
        unit_dir=unit_dir, transactions=transactions, uid=os.geteuid(),
        states=lambda name: {"ActiveState": "inactive", "MainPID": "0"},
        listeners=lambda: None,
    )


def _activate(kw, *, proof=True):
    return activation.activate_staged_release(
        **kw,
        stopped_proof=SimpleNamespace(ok=True, runtime_stopped=True) if proof else None,
    )


def test_stopped_verified_gitless_release_preserves_owner_files_and_units(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    original = kw["root"] / "untracked-secret.conf"
    assert activation.inspect_staged_release(
        kw["sha"], stage=kw["stage"], root=kw["root"],
        manifest=kw["manifest"], unit_dir=kw["unit_dir"], uid=kw["uid"],
    )["old"]["build_sha"] != kw["sha"]
    assert _activate(kw).startswith("INSTALLED_STOPPED:")
    assert original.read_text() == "owner must keep"
    assert json.loads(kw["manifest"].read_text())["build_sha"] == kw["sha"]
    for unit in UNITS:
        assert (kw["unit_dir"] / unit).read_bytes() == (
            kw["stage"] / "deploy/systemd" / unit).read_bytes()
    assert (kw["root"] / "new_feature.py").read_bytes() == b"new feature"
    checkpoint = kw["transactions"] / kw["sha"]
    assert (checkpoint / "rollback/tracked/user.txt").read_bytes() == b"old:tracked/user.txt"


def test_switch_refuses_unproven_stop_without_installing(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    before = kw["manifest"].read_bytes()
    with pytest.raises(activation.ActivationBlocked, match="canonical_safe_stop_unproven"):
        _activate(kw, proof=False)
    assert kw["manifest"].read_bytes() == before
    assert not (kw["transactions"] / kw["sha"]).exists()


def test_stopped_unit_or_live_port_never_mutates_files(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    before = kw["manifest"].read_bytes()
    kw["states"] = lambda _: {"ActiveState": "active", "MainPID": "99"}
    with pytest.raises(activation.ActivationBlocked, match="PAPER_unit_not_stopped"):
        _activate(kw)
    kw["states"] = lambda _: {"ActiveState": "inactive", "MainPID": "0"}
    kw["listeners"] = lambda: (_ for _ in ()).throw(
        activation.ActivationBlocked("PAPER_port_owned"))
    with pytest.raises(activation.ActivationBlocked, match="PAPER_port_owned"):
        _activate(kw)
    assert kw["manifest"].read_bytes() == before


def test_untracked_collision_refuses_before_backup_or_mutation(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    (kw["root"] / "new_feature.py").write_text("private owner source")
    with pytest.raises(activation.ActivationBlocked, match="tracked_or_untracked_collision"):
        _activate(kw)
    assert (kw["root"] / "new_feature.py").read_text() == "private owner source"
    assert not (kw["transactions"] / kw["sha"]).exists()


def test_interrupted_file_copy_resumes_without_second_stop(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    saved = activation._atomic_file
    attempt = [0]
    def fail_once(path, data, mode=0o644):
        if path.name == "tracked" or (path.name == "user.txt" and attempt[0] == 0):
            attempt[0] += 1
            raise OSError("simulated disk interruption")
        return saved(path, data, mode)
    monkeypatch.setattr(activation, "_atomic_file", fail_once)
    with pytest.raises(OSError, match="simulated disk interruption"):
        _activate(kw)
    assert json.loads(kw["manifest"].read_text())["build_sha"] != kw["sha"]
    assert (kw["transactions"] / kw["sha"] / "old.json").is_file()
    monkeypatch.setattr(activation, "_atomic_file", saved)
    assert _activate(kw, proof=False).startswith("INSTALLED_STOPPED:")
    assert json.loads(kw["manifest"].read_text())["build_sha"] == kw["sha"]


def test_previous_transaction_blocks_tampered_staged_target(tmp_path, monkeypatch):
    kw = _fixture(tmp_path, monkeypatch)
    saved = activation._atomic_file
    def interrupt(path, data, mode=0o644):
        if path.name == "user.txt":
            raise OSError("crash")
        return saved(path, data, mode)
    monkeypatch.setattr(activation, "_atomic_file", interrupt)
    with pytest.raises(OSError):
        _activate(kw)
    monkeypatch.setattr(activation, "_atomic_file", saved)
    (kw["stage"] / "new_feature.py").write_text("tamper")
    with pytest.raises(activation.ActivationBlocked):
        _activate(kw, proof=False)
    assert json.loads(kw["manifest"].read_text())["build_sha"] != kw["sha"]
