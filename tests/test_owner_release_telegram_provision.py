"""Offline proof: disabled owner release setup never touches PAPER runtime."""
import json
import os
from pathlib import Path
import stat
import subprocess

import pytest

from tools import owner_release_telegram_provision as provision
from tools import owner_release_telegram_runtime as approval_runtime
from tools import paper_maintenance, vps_owner_control
from tools.vps_release_identity import git_blob_hash

SHA = "a" * 40
UUID = "b" * 32


@pytest.fixture
def host(tmp_path, monkeypatch):
    uid = os.geteuid()
    # Exact source bytes and fake tracked manifests; tests never use host units.
    root = tmp_path / "repo"
    root.mkdir(mode=0o700)
    directory = tmp_path / "etc" / "systemd" / "system"
    directory.mkdir(parents=True, mode=0o700)
    state = tmp_path / "var" / "lib" / "owner-release"
    state.parent.mkdir(parents=True, mode=0o700)
    inbox = state.parent / "owner-release-inbox"
    config = tmp_path / "config.json"
    blobs = {"terminal/runtime/paper_http_server.py": "c" * 40,
             "tools/vps_release_identity.py": "d" * 40}
    for name in approval_runtime.OWNER_UNIT_NAMES:
        rel = "deploy/systemd/" + name
        source = root / rel
        source.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        data = ("[Unit]\nDescription=" + name + "\n").encode()
        source.write_bytes(data)
        blobs[rel] = git_blob_hash(data)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"build_sha": SHA, "blobs": blobs}))
    checked = []
    def verify(*args, **kwargs):
        checked.append(("verify", args, kwargs))
        return SHA
    def pinned(*args, **kwargs):
        checked.append(("pinned", args, kwargs))
        return None
    def relay_test(path, relay_uid):
        meta = path.lstat()
        assert stat.S_ISDIR(meta.st_mode)
        assert meta.st_uid == relay_uid
        assert stat.S_IMODE(meta.st_mode) == 0o700
    monkeypatch.setattr(provision, "verify_release", verify)
    monkeypatch.setattr(provision, "_check_sources", pinned)
    monkeypatch.setattr(provision, "_check_relay_inbox", relay_test)
    args = dict(root=root, manifest_path=manifest, unit_dir=directory,
                state=state, inbox=inbox, config=config, uid=uid, relay_uid=uid)
    return args, checked


def test_provision_is_disabled_and_preserves_durable_receipts(host):
    args, checked = host
    assert "tools/owner_release_telegram_provision.py" in approval_runtime.PINNED
    result = provision.prepare(SHA, **args)
    assert result.startswith("READY: OWNER_RELEASE_PREPARED_DISABLED")
    assert not args["config"].exists()
    assert (args["state"] / "pending.json").read_text() == '{"pending":null}'
    for name in ("prompts", "grants"):
        assert (args["state"] / name / "initialized").read_bytes() == b"owner-update-v1\n"
    for name in approval_runtime.OWNER_UNIT_NAMES:
        unit = args["unit_dir"] / name
        source = args["root"] / "deploy/systemd" / name
        assert unit.read_bytes() == source.read_bytes()
        assert stat.S_IMODE(unit.stat().st_mode) == 0o644
    assert (args["inbox"]).is_dir()
    receipt = args["state"] / "grants" / (UUID + ".used")
    receipt.write_text("protected prior claim")
    assert provision.prepare(SHA, **args) == result
    assert receipt.read_text() == "protected prior claim"
    assert len([x for x in checked if x[0] == "pinned"]) == 2


def test_wrong_target_blocks_before_any_file_creation(host):
    args, _ = host
    with pytest.raises(ValueError, match="installed release changed"):
        provision.prepare("e" * 40, **args)
    assert not args["state"].exists()
    assert not args["inbox"].exists()
    assert list(args["unit_dir"].iterdir()) == []


def test_existing_foreign_unit_blocks_before_private_state_creation(host):
    args, _ = host
    first = args["unit_dir"] / approval_runtime.OWNER_UNIT_NAMES[0]
    first.write_text("unrelated owner unit")
    with pytest.raises(ValueError, match="existing owner release file differs"):
        provision.prepare(SHA, **args)
    assert not args["state"].exists()
    assert not args["inbox"].exists()
    assert first.read_text() == "unrelated owner unit"


def test_existing_config_or_inflight_challenge_is_never_overwritten(host):
    args, _ = host
    provision.prepare(SHA, **args)
    args["config"].write_text("owner-owned configuration")
    with pytest.raises(ValueError, match="already present"):
        provision.prepare(SHA, **args)
    assert args["config"].read_text() == "owner-owned configuration"
    args["config"].unlink()
    pending = args["state"] / "pending.json"
    pending.write_text('{"pending":{"unknown":"active"}}')
    with pytest.raises(ValueError, match="not idle"):
        provision.prepare(SHA, **args)
    assert pending.read_text() == '{"pending":{"unknown":"active"}}'


def test_missing_existing_ledger_is_not_recreated(host):
    args, _ = host
    provision.prepare(SHA, **args)
    (args["state"] / "grants" / "initialized").unlink()
    with pytest.raises(OSError):
        provision.prepare(SHA, **args)
    assert not (args["state"] / "grants" / "initialized").exists()


def test_canonical_owner_action_does_not_call_start_or_stop(monkeypatch, capsys):
    from contextlib import nullcontext
    monkeypatch.setattr(paper_maintenance, "_owner_action_lifecycle_guard", nullcontext)
    monkeypatch.setattr(provision, "prepare", lambda sha: "READY: OWNER_RELEASE_PREPARED_DISABLED")
    monkeypatch.setattr(paper_maintenance, "resume_installed_release",
                        lambda *_a, **_kw: pytest.fail("unexpected runtime resume"))
    assert paper_maintenance.main([SHA, "--action", "owner-release-prepare"]) == 0
    assert "OWNER_RELEASE_PREPARED_DISABLED" in capsys.readouterr().out
    monkeypatch.setattr(provision, "prepare",
                        lambda sha: (_ for _ in ()).throw(ValueError("SECRET")))
    assert paper_maintenance.main([SHA, "--action", "owner-release-prepare"]) == 2
    output = capsys.readouterr().out
    assert "owner_release_prepare_unproven" in output and "SECRET" not in output


def test_prepare_goes_via_existing_detached_uuid_owner_monolith(capsys, monkeypatch, tmp_path):
    original = vps_owner_control._owner_request_path
    monkeypatch.setattr(vps_owner_control, "_owner_request_path",
                        lambda request, *, create=False: original(
                            request, create=create, root=tmp_path / "transactions",
                            trusted_uid=os.geteuid()))
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0,
            stdout=("LoadState=not-found\n" if cmd[0] == "systemctl" else ""), stderr="")
    assert vps_owner_control.submit("owner-release-prepare", SHA, UUID,
                                    "owner-pc", run=run, uid=0) == 0
    assert calls[0][0] == "systemctl"
    assert calls[1][0] == "systemd-run"
    assert "--unit=" + vps_owner_control.unit_name(UUID) in calls[1]
    assert calls[1][-5:] == ["-m", "tools.paper_maintenance", SHA, "--action",
                            "owner-release-prepare"]
