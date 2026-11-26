"""Offline proof of the pinned read-only refusal and its durable retirement."""
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import paper_readonly_stop_refusal_recovery as recovery


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    directory = tmp_path / "transactions"
    directory.mkdir(mode=0o700)
    lock = directory / ".release.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    marker, receipt = recovery._paths(directory)
    marker.write_bytes(recovery.MARKER)
    marker.chmod(0o600)
    os.utime(marker, ns=(recovery.MARKER_MS * 1000000,) * 2)
    identity = "d" * 64
    state = {"ok": True, "trading_account_id": {"value": "paper"},
             "mode": "PAPER_AUTO", "version": recovery.AUTOPILOT_VERSION,
             "updated_at_ms": recovery.AUTOPILOT_UPDATED_MS}
    health = {"ok": True, "component": "paper_backend", "mode": "paper",
              "paper_live_safe": True, "build_sha": recovery.OLD,
              "database_identity": identity, "process_instance_id": "same-owner"}
    calls = []
    monkeypatch.setattr("tools.vps_release_identity.verify_release", lambda *_: recovery.OLD)
    monkeypatch.setattr("tools.paper_maintenance._legacy_paused_backend_predates_stop",
                        lambda *_: True)
    monkeypatch.setattr("tools.runtime_intent.expected_database_identity", lambda *_: identity)
    monkeypatch.setattr("tools.stop_robot_runtime._environment", lambda *_: {})

    def get(url, timeout):
        calls.append(url)
        return 200, dict(health if url.endswith("/health") else state)

    monkeypatch.setattr("tools.stop_robot_runtime._http_get", get)
    monkeypatch.setattr(recovery, "_failed_unit_proof", lambda: None)
    return SimpleNamespace(root=root, directory=directory, marker=marker, receipt=receipt,
                           state=state, health=health, calls=calls,
                           seal=lambda: recovery.seal_readonly_refusal(
                               root=root, env_file=None, directory=directory, uid=os.geteuid()))


def test_exact_refusal_is_retired_without_forging_stop_or_install(evidence):
    assert not recovery.proven_readonly_refusal(
        evidence.directory, recovery.PRIOR, uid=os.geteuid())
    evidence.seal()
    assert evidence.marker.read_bytes() == recovery.MARKER
    assert evidence.receipt.read_bytes() == recovery.RECEIPT
    assert not (evidence.directory / (".stop-confirmed-" + recovery.PRIOR)).exists()
    assert not (evidence.directory / recovery.PRIOR).exists()
    assert recovery.proven_readonly_refusal(
        evidence.directory, recovery.PRIOR, uid=os.geteuid())
    assert not recovery.proven_readonly_refusal(
        evidence.directory, "f" * 40, uid=os.geteuid())
    # The durable proof is historical. A repeated proof never performs STOP.
    before = list(evidence.calls)
    evidence.seal()
    assert evidence.calls == before


def test_historical_refusal_requires_fresh_successor_stop_intent(evidence):
    from tools.paper_maintenance import _record_one_shot_stop_intent
    successor = "c" * 40
    fresh = evidence.directory / (".stop-invoked-" + successor)
    assert not _record_one_shot_stop_intent(
        evidence.directory, successor, uid=os.geteuid(), root=evidence.root)
    assert not fresh.exists()
    evidence.seal()
    assert _record_one_shot_stop_intent(
        evidence.directory, successor, uid=os.geteuid(), root=evidence.root)
    assert fresh.is_file() and evidence.marker.is_file()
    assert not _record_one_shot_stop_intent(
        evidence.directory, successor, uid=os.geteuid(), root=evidence.root)


@pytest.mark.parametrize("key,value", [
    ("mode", "OFF"), ("version", recovery.AUTOPILOT_VERSION + 1),
    ("updated_at_ms", recovery.MARKER_MS + 1),
    ("trading_account_id", {"value": "live"}), ("ok", False),
])
def test_autopilot_mutation_or_wrong_account_keeps_fence(evidence, key, value):
    evidence.state[key] = value
    with pytest.raises(ValueError, match="autopilot_mutation_not_excluded"):
        evidence.seal()
    assert evidence.marker.is_file()
    assert not evidence.receipt.exists()


@pytest.mark.parametrize("failure", ["owner", "db", "sha", "success", "install", "log"])
def test_incomplete_proof_never_retires_fence(evidence, monkeypatch, failure):
    if failure == "owner":
        monkeypatch.setattr("tools.paper_maintenance._legacy_paused_backend_predates_stop",
                            lambda *_: False)
    elif failure == "db":
        evidence.health["database_identity"] = "foreign"
    elif failure == "sha":
        monkeypatch.setattr("tools.vps_release_identity.verify_release", lambda *_: "f" * 40)
    elif failure == "success":
        (evidence.directory / (".stop-confirmed-" + recovery.PRIOR)).write_bytes(b"receipt")
    elif failure == "install":
        (evidence.directory / recovery.PRIOR).mkdir()
    else:
        def wrong_log():
            raise ValueError("wrong log")
        monkeypatch.setattr(recovery, "_failed_unit_proof", wrong_log)
    with pytest.raises(ValueError):
        evidence.seal()
    assert evidence.marker.is_file()
    assert not evidence.receipt.exists()


@pytest.mark.parametrize("changed", [None, "message", "invocation", "unit", "uid", "time", "boot"])
def test_exact_failed_unit_journal_identity(changed, monkeypatch):
    invocation, boot = "a" * 32, "b" * 32
    original_read = Path.read_text

    def read(path, *args, **kwargs):
        if str(path) == "/proc/sys/kernel/random/boot_id":
            return boot
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    fields = {"LoadState": "loaded", "ActiveState": "failed", "SubState": "failed",
              "Result": "exit-code", "ExecMainStatus": "2",
              "Description": recovery.DESCRIPTION, "InvocationID": invocation}
    row = {"MESSAGE": recovery.REFUSAL, "_UID": "0", "_SYSTEMD_UNIT": recovery.UNIT,
           "_SYSTEMD_INVOCATION_ID": invocation, "_BOOT_ID": boot,
           "__REALTIME_TIMESTAMP": str((recovery.MARKER_MS + 5000) * 1000)}
    if changed == "message":
        row["MESSAGE"] = "BLOCKED: Autopilot OFF outcome unknown"
    elif changed == "invocation":
        row["_SYSTEMD_INVOCATION_ID"] = "c" * 32
    elif changed == "unit":
        row["_SYSTEMD_UNIT"] = "different.service"
    elif changed == "uid":
        row["_UID"] = "1000"
    elif changed == "time":
        row["__REALTIME_TIMESTAMP"] = str((recovery.MARKER_MS - 1) * 1000)
    elif changed == "boot":
        row["_BOOT_ID"] = "c" * 32

    def run(cmd, **kwargs):
        if cmd[0] == "systemctl":
            return SimpleNamespace(returncode=0, stdout="\n".join(
                key + "=" + value for key, value in fields.items()))
        assert "_SYSTEMD_INVOCATION_ID=" + invocation in cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps(row))

    if changed is None:
        recovery._failed_unit_proof(run=run)
    else:
        with pytest.raises(ValueError):
            recovery._failed_unit_proof(run=run)
