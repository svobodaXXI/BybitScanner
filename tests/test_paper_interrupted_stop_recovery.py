"""Regression for the one incident-only STOP continuation: never replay owner actions."""
import os
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from tools import paper_interrupted_stop_recovery as recovery
from tools import paper_readonly_stop_refusal_recovery as readonly_refusal


def _fixture(monkeypatch, tmp_path):
    root = tmp_path / "installed"
    stage = tmp_path / "stage"
    root.mkdir()
    stage.mkdir()
    journal = tmp_path / "transactions"
    journal.mkdir(mode=0o700)
    (journal / (".chatops-invoked-" + recovery.PRIOR_TARGET)).write_bytes(
        (recovery.PRIOR_TARGET + "\n").encode()
    )
    (journal / (".stop-invoked-" + recovery.PRIOR_TARGET)).write_bytes(
        b"STOP_INVOKED; not install authorization\\n"
    )
    for path in journal.iterdir():
        path.chmod(0o600)
    monkeypatch.setattr(recovery, "_environment", lambda _: {"BYBITSCANNER_PAPER_DB": str(tmp_path / "paper.sqlite")})
    monkeypatch.setattr(recovery, "expected_database_identity", lambda *_: "d" * 64)
    monkeypatch.setattr(recovery, "verify_release", lambda *_: recovery.OLD_BACKEND)
    monkeypatch.setattr(recovery, "get_snapshots", lambda: {"immutable": True})

    calls = []
    class Owner:
        def __init__(self, **kwargs):
            pass
        def _probe_backend(self):
            return recovery.PRESENT
        def _require_scanner_stopped(self):
            calls.append("scanner_check")
        def _require_autopilot_off(self):
            calls.append("autopilot_check")
        def _probe_telegram(self):
            return recovery.ABSENT

    monkeypatch.setattr(recovery, "RuntimeShutdown", Owner)
    defaults = dict(
        target="a" * 40,
        root=root, stage=stage, transactions=journal,
        uid=os.geteuid(), manifest=tmp_path / "manifest",
        inspect=lambda *_args, **_kw: calls.append("stage_check"),
        proof=lambda *_args, **_kw: recovery.PROOF_LABEL,
        handoff=lambda: (calls.append("SIGINT"),
                         "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed")[1],
        backend_stopped=lambda: True,
        installer=lambda *_args, **_kw: (
            calls.append("install"), "INSTALLED_STOPPED: exact")[1],
        resume=lambda *_args, **_kw: (
            calls.append("editor_resume"), "READY: EDITOR_ONLY")[1],
    )
    return journal, calls, defaults


def test_confirmed_exceptional_handoff_installs_editor_without_stop_or_paper(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    assert recovery.recover_editor_only(**options) == "READY: EDITOR_ONLY"
    assert calls == [
        "stage_check", "scanner_check", "autopilot_check", "SIGINT",
        "install", "editor_resume",
    ]
    assert recovery._receipt(journal, "handoff-attempt", os.geteuid(), target="a" * 40)
    assert recovery._receipt(journal, "backend-exited", os.geteuid(), target="a" * 40)
    assert recovery._receipt(journal, "handoff-proven", os.geteuid(), target="a" * 40)
    assert (journal / (".stop-invoked-" + recovery.PRIOR_TARGET)).exists()


def test_lost_sigint_outcome_blocks_without_retry_or_install(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    options["handoff"] = lambda: (calls.append("SIGINT"), "OUTCOME_UNKNOWN")[1]
    with pytest.raises(recovery.RecoveryBlocked, match="exceptional_handoff_outcome_unknown_no_retry"):
        recovery.recover_editor_only(**options)
    assert recovery._receipt(journal, "handoff-attempt", os.geteuid(), target="a" * 40)
    assert not recovery._receipt(journal, "backend-exited", os.geteuid(), target="a" * 40)
    with pytest.raises(recovery.RecoveryBlocked, match="prior_handoff_outcome_unknown_no_retry"):
        recovery.recover_editor_only(**options)
    assert calls.count("SIGINT") == 1
    assert "install" not in calls


def test_exact_old_release_required_before_handoff(monkeypatch, tmp_path):
    _, calls, options = _fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(recovery, "verify_release", lambda *_: "c" * 40)
    with pytest.raises(recovery.RecoveryBlocked, match="installed_release_changed"):
        recovery.recover_editor_only(**options)
    assert calls == []


def test_missing_previous_chatops_marker_cannot_grant_new_handoff(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    (journal / (".chatops-invoked-" + recovery.PRIOR_TARGET)).unlink()
    with pytest.raises(recovery.RecoveryBlocked, match="original_stop_intent_unproven"):
        recovery.recover_editor_only(**options)
    assert calls == []


def test_backend_exit_receipt_can_resume_install_without_repeating_sigint(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    for phase in ("handoff-attempt", "backend-exited", "handoff-proven"):
        recovery._record(journal, phase, os.geteuid(), target="a" * 40)
    assert recovery.recover_editor_only(**options) == "READY: EDITOR_ONLY"
    assert calls == ["stage_check", "install", "editor_resume"]


def test_corrupted_recovery_receipt_does_not_authorize_install(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    path = journal / (recovery.MARKER_PREFIX + "handoff-proven-" + recovery.PRIOR_TARGET)
    path.write_text("different target\n")
    path.chmod(0o600)
    with pytest.raises(recovery.RecoveryBlocked, match="recovery_receipt_mismatch"):
        recovery.recover_editor_only(**options)
    assert calls == ["stage_check"]


def test_unknown_telegram_shutdown_does_not_replay(monkeypatch, tmp_path):
    journal, calls, options = _fixture(monkeypatch, tmp_path)
    seen = [0]
    class TelegramOwner:
        def __init__(self, **kwargs):
            pass
        def _probe_backend(self):
            return recovery.PRESENT
        def _require_scanner_stopped(self):
            pass
        def _require_autopilot_off(self):
            pass
        def _probe_telegram(self):
            seen[0] += 1
            return recovery.PRESENT
    monkeypatch.setattr(recovery, "RuntimeShutdown", TelegramOwner)
    def telegram():
        calls.append("telegram_attempt")
        raise OSError("unknown shutdown result")
    options["telegram"] = telegram
    with pytest.raises(OSError):
        recovery.recover_editor_only(**options)
    assert recovery._receipt(journal, "backend-exited", os.geteuid(), target="a" * 40)
    assert recovery._receipt(journal, "telegram-attempt", os.geteuid(), target="a" * 40)
    with pytest.raises(recovery.RecoveryBlocked, match="telegram_shutdown_outcome_unknown_no_retry"):
        recovery.recover_editor_only(**options)
    assert calls.count("telegram_attempt") == 1
    assert calls.count("SIGINT") == 1
    assert "install" not in calls


def test_cli_bootstrap_separates_installed_gitless_root_from_staging(monkeypatch, tmp_path, capsys):
    """PR #845 regression: staging imports must not redirect release ownership."""
    stage = tmp_path / "checked-out-stage"
    stage.mkdir()
    (stage / ".git").mkdir()
    observed = []

    def fake_recover(**kwargs):
        observed.append(kwargs)
        return "READY: EDITOR_ONLY"

    monkeypatch.setattr(recovery, "recover_editor_only", fake_recover)
    code = recovery.main([
        "--stage", str(stage), "--target", "a" * 40,
        "--execute-exceptional-handoff",
    ])
    assert code == 0
    assert observed == [{
        "target": "a" * 40, "stage": stage,
        "root": Path("/opt/BybitScanner"),
    }]
    assert recovery.INSTALLED_ROOT != stage
    assert "READY: EDITOR_ONLY" in capsys.readouterr().out


def test_cli_denies_execution_without_explicit_handoff_optin(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(recovery, "recover_editor_only",
                        lambda **kwargs: called.append(kwargs))
    assert recovery.main([
        "--stage", str(tmp_path), "--target", "a" * 40,
    ]) == 2
    assert called == []


def test_recovery_default_root_is_fixed_gitless_install_not_source_tree():
    import inspect
    default = inspect.signature(recovery.recover_editor_only).parameters["root"].default
    assert default == Path("/opt/BybitScanner")
    assert default != Path(recovery.__file__).resolve().parents[1]


# 26 Nov: exact proof of a refused read before any STOP mutation.
@pytest.fixture
def readonly_evidence(tmp_path, monkeypatch):
    root = tmp_path / "installed"
    root.mkdir()
    directory = tmp_path / "transactions"
    directory.mkdir(mode=0o700)
    lock = directory / ".release.lock"
    lock.write_bytes(b"")
    lock.chmod(0o600)
    marker, receipt = readonly_refusal._paths(directory)
    marker.write_bytes(readonly_refusal.MARKER)
    marker.chmod(0o600)
    os.utime(marker, ns=(readonly_refusal.MARKER_MS * 1000000,) * 2)
    identity = "d" * 64
    state = {"ok": True, "trading_account_id": {"value": "paper"},
             "mode": "PAPER_AUTO", "version": readonly_refusal.AUTOPILOT_VERSION,
             "updated_at_ms": readonly_refusal.AUTOPILOT_UPDATED_MS}
    health = {"ok": True, "component": "paper_backend", "mode": "paper",
              "paper_live_safe": True, "build_sha": readonly_refusal.OLD,
              "database_identity": identity, "process_instance_id": "same-owner"}
    calls = []
    monkeypatch.setattr("tools.vps_release_identity.verify_release", lambda *_: readonly_refusal.OLD)
    monkeypatch.setattr("tools.paper_maintenance._legacy_paused_backend_predates_stop",
                        lambda *_: True)
    monkeypatch.setattr("tools.runtime_intent.expected_database_identity", lambda *_: identity)
    monkeypatch.setattr("tools.stop_robot_runtime._environment", lambda *_: {})

    def get(url, timeout):
        calls.append(url)
        return 200, dict(health if url.endswith("/health") else state)

    monkeypatch.setattr("tools.stop_robot_runtime._http_get", get)
    monkeypatch.setattr(readonly_refusal, "_failed_unit_proof", lambda: None)
    return SimpleNamespace(root=root, directory=directory, marker=marker, receipt=receipt,
                           state=state, health=health, calls=calls,
                           seal=lambda: readonly_refusal.seal_readonly_refusal(
                               root=root, env_file=None, directory=directory, uid=os.geteuid()))


def test_exact_refusal_is_retired_without_forging_stop_or_install(readonly_evidence):
    assert not readonly_refusal.proven_readonly_refusal(
        readonly_evidence.directory, readonly_refusal.PRIOR, uid=os.geteuid())
    readonly_evidence.seal()
    assert readonly_evidence.marker.read_bytes() == readonly_refusal.MARKER
    assert readonly_evidence.receipt.read_bytes() == readonly_refusal.RECEIPT
    assert not (readonly_evidence.directory / (".stop-confirmed-" + readonly_refusal.PRIOR)).exists()
    assert not (readonly_evidence.directory / readonly_refusal.PRIOR).exists()
    assert readonly_refusal.proven_readonly_refusal(
        readonly_evidence.directory, readonly_refusal.PRIOR, uid=os.geteuid())
    assert not readonly_refusal.proven_readonly_refusal(
        readonly_evidence.directory, "f" * 40, uid=os.geteuid())
    # The durable proof is historical. A repeated proof never performs STOP.
    before = list(readonly_evidence.calls)
    readonly_evidence.seal()
    assert readonly_evidence.calls == before


def test_historical_refusal_requires_fresh_successor_stop_intent(readonly_evidence):
    from tools.paper_maintenance import _record_one_shot_stop_intent
    successor = "c" * 40
    fresh = readonly_evidence.directory / (".stop-invoked-" + successor)
    assert not _record_one_shot_stop_intent(
        readonly_evidence.directory, successor, uid=os.geteuid(), root=readonly_evidence.root)
    assert not fresh.exists()
    readonly_evidence.seal()
    assert _record_one_shot_stop_intent(
        readonly_evidence.directory, successor, uid=os.geteuid(), root=readonly_evidence.root)
    assert fresh.is_file() and readonly_evidence.marker.is_file()
    assert not _record_one_shot_stop_intent(
        readonly_evidence.directory, successor, uid=os.geteuid(), root=readonly_evidence.root)


@pytest.mark.parametrize("key,value", [
    ("mode", "OFF"), ("version", readonly_refusal.AUTOPILOT_VERSION + 1),
    ("updated_at_ms", readonly_refusal.MARKER_MS + 1),
    ("trading_account_id", {"value": "live"}), ("ok", False),
])
def test_autopilot_mutation_or_wrong_account_keeps_fence(readonly_evidence, key, value):
    readonly_evidence.state[key] = value
    with pytest.raises(ValueError, match="autopilot_mutation_not_excluded"):
        readonly_evidence.seal()
    assert readonly_evidence.marker.is_file()
    assert not readonly_evidence.receipt.exists()


@pytest.mark.parametrize("failure", ["owner", "db", "sha", "success", "install", "log"])
def test_incomplete_proof_never_retires_fence(readonly_evidence, monkeypatch, failure):
    if failure == "owner":
        monkeypatch.setattr("tools.paper_maintenance._legacy_paused_backend_predates_stop",
                            lambda *_: False)
    elif failure == "db":
        readonly_evidence.health["database_identity"] = "foreign"
    elif failure == "sha":
        monkeypatch.setattr("tools.vps_release_identity.verify_release", lambda *_: "f" * 40)
    elif failure == "success":
        (readonly_evidence.directory / (".stop-confirmed-" + readonly_refusal.PRIOR)).write_bytes(b"receipt")
    elif failure == "install":
        (readonly_evidence.directory / readonly_refusal.PRIOR).mkdir()
    else:
        def wrong_log():
            raise ValueError("wrong log")
        monkeypatch.setattr(readonly_refusal, "_failed_unit_proof", wrong_log)
    with pytest.raises(ValueError):
        readonly_evidence.seal()
    assert readonly_evidence.marker.is_file()
    assert not readonly_evidence.receipt.exists()


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
              "Description": readonly_refusal.DESCRIPTION, "InvocationID": invocation}
    row = {"MESSAGE": readonly_refusal.REFUSAL, "_UID": "0", "_SYSTEMD_UNIT": readonly_refusal.UNIT,
           "_SYSTEMD_INVOCATION_ID": invocation, "_BOOT_ID": boot,
           "__REALTIME_TIMESTAMP": str((readonly_refusal.MARKER_MS + 5000) * 1000)}
    if changed == "message":
        row["MESSAGE"] = "BLOCKED: Autopilot OFF outcome unknown"
    elif changed == "invocation":
        row["_SYSTEMD_INVOCATION_ID"] = "c" * 32
    elif changed == "unit":
        row["_SYSTEMD_UNIT"] = "different.service"
    elif changed == "uid":
        row["_UID"] = "1000"
    elif changed == "time":
        row["__REALTIME_TIMESTAMP"] = str((readonly_refusal.MARKER_MS - 1) * 1000)
    elif changed == "boot":
        row["_BOOT_ID"] = "c" * 32

    def run(cmd, **kwargs):
        if cmd[0] == "systemctl":
            return SimpleNamespace(returncode=0, stdout="\n".join(
                key + "=" + value for key, value in fields.items()))
        assert "_SYSTEMD_INVOCATION_ID=" + invocation in cmd
        return SimpleNamespace(returncode=0, stdout=json.dumps(row))

    if changed is None:
        readonly_refusal._failed_unit_proof(run=run)
    else:
        with pytest.raises(ValueError):
            readonly_refusal._failed_unit_proof(run=run)
