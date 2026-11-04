"""Regression for the one incident-only STOP continuation: never replay owner actions."""
import os
from pathlib import Path

import pytest

from tools import paper_interrupted_stop_recovery as recovery


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
