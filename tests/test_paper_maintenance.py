import os
import sqlite3
import subprocess
import pytest
from pathlib import Path
from types import SimpleNamespace

from tools.paper_maintenance import run_maintenance


@pytest.fixture(autouse=True)
def fake_git_checkout(monkeypatch):
    # Existing legacy Git-checkout tests intentionally exercise the
    # pre-verified checkout path with a fake command runner.
    original = Path.is_dir
    monkeypatch.setattr(
        Path, "is_dir",
        lambda path: True if path.name == ".git" else original(path),
    )


@pytest.fixture(autouse=True)
def fake_ready_api(monkeypatch):
    from tools.runtime_intent import expected_database_identity
    from tools.stop_robot_runtime import _environment

    identity = expected_database_identity(Path("/opt/BybitScanner"), _environment(None))

    def get(url, _timeout):
        if url.endswith("/api/health"):
            data = {"ok": True, "component": "paper_backend", "mode": "paper",
                    "paper_live_safe": True, "robot_admission_ready": True,
                    "scanner_acceptance_ready": True,
                    "database_identity": identity, "build_sha": "a" * 40}
        elif url.endswith("/api/robot/protection-health"):
            data = {"ok": True, "healthy": True}
        elif url.endswith("/api/scanner/status"):
            data = {"ok": True, "mode": "SCANNER_RUNNING"}
        else:
            data = {"ok": True, "mode": "PAPER_AUTO",
                    "trading_account_id": {"value": "paper"}}
        return SimpleNamespace(status=200, json=lambda: data)
    monkeypatch.setattr("tools.runtime_intent.http_get", get)


def fake_runner(calls, *, fail=None):
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=1 if tuple(argv) == fail else 0,
                               stdout=("a" * 40 if tuple(argv) == ("git", "rev-parse", "--verify", "HEAD") else "stable/adfb50b-forward\n" if tuple(argv) == ("git", "branch", "--show-current") else ""))
    return run


def test_rejects_bad_sha_without_stop_or_mutation():
    calls = []
    assert run_maintenance("bad", stop=lambda _: calls.append("stop")) .startswith("BLOCKED:")
    assert calls == []

def test_protected_open_exposure_never_fetches_or_restarts():
    calls = []
    blocked = SimpleNamespace(ok=False, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: blocked, runner=fake_runner(calls), readiness=lambda: True)
    assert result.startswith("BLOCKED:")
    assert all(cmd != ("sudo", "-n", "systemctl", "start", "bybitscanner-paper-start.service") for cmd in calls)


def test_safe_stop_required_even_if_result_ok():
    calls = []
    incomplete = SimpleNamespace(ok=True, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: incomplete, runner=fake_runner(calls), readiness=lambda: True)
    assert result.startswith("BLOCKED:")
    assert not any("systemctl" in cmd or cmd[:2] == ("git", "merge") for cmd in calls)


def test_approved_target_only_after_safe_stop():
    calls = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    target = "a" * 40
    result = run_maintenance(target, stop=lambda _: stopped,
        runner=fake_runner(calls), readiness=lambda: True, root=Path("/opt/BybitScanner"))
    assert result.startswith("READY:")
    assert ("git", "merge-base", "--is-ancestor", target, "origin/stable/adfb50b-forward") in calls
    assert calls[-1] == ("sudo", "-n", "systemctl", "start", "bybitscanner-paper-start.service")


def test_unit_prepare_failure_blocks_paper_start_after_safe_stop():
    calls = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    failure = ("sudo", "-n", "/opt/BybitScanner/venv/bin/python",
               "-m", "tools.vps_systemd_unit_prepare")
    result = run_maintenance(
        "a" * 40, stop=lambda _: stopped,
        runner=fake_runner(calls, fail=failure), readiness=lambda: True,
        root=Path("/opt/BybitScanner"),
    )
    assert result.startswith("BLOCKED: PAPER systemd units")
    assert failure in calls
    assert not any(cmd == ("sudo", "-n", "systemctl", "start",
                           "bybitscanner-paper-start.service") for cmd in calls)


def test_unapproved_target_never_updates_or_starts():
    calls = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    fail = ("git", "merge-base", "--is-ancestor", "a" * 40, "origin/stable/adfb50b-forward")
    result = run_maintenance("a" * 40, stop=lambda _: stopped,
        runner=fake_runner(calls, fail=fail), readiness=lambda: True)
    assert result.startswith("BLOCKED:")
    assert not any(cmd[:2] == ("git", "merge") or "systemctl" in cmd for cmd in calls)


def test_canonical_stop_ambiguous_result_is_never_retried_even_with_wait():
    calls = []
    attempts = []
    def stop(_scope):
        attempts.append(len(attempts))
        return SimpleNamespace(ok=False, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=stop,
        runner=fake_runner(calls), readiness=lambda: True, wait_seconds=60, poll_seconds=10,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("no retry sleep")))
    assert result.startswith("BLOCKED: canonical safe-stop unproven")
    assert len(attempts) == 1
    assert not any(cmd[:2] == ("git", "merge") or "systemctl" in cmd for cmd in calls)


def test_gitless_vps_rejected_before_stop_and_before_any_git_or_systemd(monkeypatch):
    monkeypatch.setattr(Path, "is_dir", lambda path: False if path.name == ".git" else True)
    calls = []
    result = run_maintenance(
        "a" * 40, root=Path("/opt/BybitScanner"),
        runner=lambda argv, **_: calls.append(argv),
        stop=lambda _: (_ for _ in ()).throw(AssertionError("stop must not be called")),
    )
    assert result.startswith("BLOCKED: gitless_install_requires_verified_immutable_release_switch")
    assert calls == []


def test_expired_safe_stop_leaves_code_and_service_untouched():
    calls = []
    now = [0.]
    def sleep(seconds):
        now[0] += seconds
    blocked = SimpleNamespace(ok=False, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: blocked,
        runner=fake_runner(calls), readiness=lambda: True, wait_seconds=20, poll_seconds=10,
        clock=lambda: now[0], sleep=sleep)
    assert result.startswith("BLOCKED:")
    assert not any(cmd[:2] == ("git", "merge") or "systemctl" in cmd for cmd in calls)


def test_wrong_branch_blocks_before_safe_stop():
    calls = []
    def runner(argv, **kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=0, stdout="feature/other\n" if argv == ["git", "branch", "--show-current"] else "")
    result = run_maintenance("a" * 40, runner=runner,
        stop=lambda _: (_ for _ in ()).throw(AssertionError("stop must not run")))
    assert result.startswith("BLOCKED:")
    assert not any("systemctl" in cmd for cmd in calls)


def test_resume_installed_editor_only_from_verified_stopped_release_no_stop_or_git():
    from tools.paper_maintenance import resume_installed_release
    calls = []
    probes = []
    def ready(sha, identity):
        probes.append((sha, identity))
        return len(probes) == 2
    result = resume_installed_release(
        "a" * 40, root=Path("/opt/BybitScanner"), env_file=None,
        runner=lambda argv, **_: (
            calls.append(tuple(argv)),
            SimpleNamespace(returncode=0)
        )[1],
        resume_proof=lambda sha, **_: "RESUME_READY: installed release verified",
        freeze_proof=lambda *_: "b" * 64,
        runtime_ready=ready,
    )
    assert result.startswith("READY:")
    assert len(probes) == 2
    assert calls == [
        ("sudo", "-n", "/opt/BybitScanner/venv/bin/python",
         "-m", "tools.vps_systemd_unit_prepare"),
        ("sudo", "-n", "systemctl", "start", "bybitscanner-paper-backend.service"),
        ("sudo", "-n", "systemctl", "start", "bybitscanner-telegram.service"),
    ]
    assert not any("paper-start" in " ".join(call) or "merge" in call for call in calls)


def test_resume_installed_editor_only_already_ready_never_mutates():
    from tools.paper_maintenance import resume_installed_release
    result = resume_installed_release(
        "a" * 40, root=Path("/opt/BybitScanner"), env_file=None,
        runner=lambda *_args, **_kwargs: pytest.fail("no command"),
        resume_proof=lambda *_args, **_kwargs: pytest.fail("no stopped proof"),
        freeze_proof=lambda *_: "b" * 64,
        runtime_ready=lambda *_: True,
    )
    assert result.startswith("READY:")
    assert "no mutation" in result


def test_resume_installed_live_or_wrong_release_never_starts():
    from tools.paper_maintenance import resume_installed_release
    from tools.vps_release_resume import ResumeBlocked
    calls = []
    result = resume_installed_release(
        "a" * 40, root=Path("/opt/BybitScanner"), env_file=None,
        runner=lambda argv, **_: calls.append(tuple(argv)),
        resume_proof=lambda *_args, **_kwargs: (
            _ for _ in ()
        ).throw(ResumeBlocked("PAPER_unit_not_stopped")),
        freeze_proof=lambda *_: "b" * 64,
        runtime_ready=lambda *_: False,
    )
    assert result.startswith("BLOCKED: installed_release_not_stopped")
    assert not calls


def test_resume_installed_unfrozen_paper_never_attempts_start():
    from tools.paper_maintenance import resume_installed_release
    calls = []
    result = resume_installed_release(
        "a" * 40, root=Path("/opt/BybitScanner"), env_file=None,
        runner=lambda argv, **_: calls.append(tuple(argv)),
        freeze_proof=lambda *_: (_ for _ in ()).throw(
            ValueError("Scanner is running")
        ),
    )
    assert result.startswith("BLOCKED: editor_only_freeze_unproven")
    assert not calls


def test_resume_installed_service_failure_preserves_backend_and_never_requests_paper_auto():
    from tools.paper_maintenance import resume_installed_release
    calls = []
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=1 if "bybitscanner-telegram.service" in argv else 0)
    result = resume_installed_release(
        "a" * 40, root=Path("/opt/BybitScanner"), env_file=None,
        runner=run,
        resume_proof=lambda *_args, **_kwargs: "RESUME_READY: installed",
        freeze_proof=lambda *_: "b" * 64,
        runtime_ready=lambda *_: False,
    )
    assert result.startswith("BLOCKED: telegram_start_failed_or_unknown")
    assert len(calls) == 3
    assert not any("bybitscanner-paper-start.service" in c for c in calls)


def test_partial_editor_resume_only_starts_absent_telegram(monkeypatch, tmp_path):
    from tools.paper_maintenance import resume_installed_release
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as identity
    import tools.vps_release_resume as resume
    import tools.legacy_runtime_process as legacy

    root = tmp_path / "release"
    original = root / "deploy/systemd/bybitscanner-telegram.service"
    original.parent.mkdir(parents=True)
    original.write_text("[Service]\nExecStart=/bin/true\n")
    units = tmp_path / "systemd"
    units.mkdir()
    (units / original.name).write_bytes(original.read_bytes())
    monkeypatch.setattr(resume, "UNIT_DIR", units)
    monkeypatch.setattr(resume, "_systemd_state",
                        lambda unit: {"ActiveState": "inactive", "MainPID": "0"})
    monkeypatch.setattr(identity, "verify_release", lambda path: "a" * 40)
    monkeypatch.setattr(legacy, "probe_listener_pids", lambda host, port: ())
    monkeypatch.setattr(maintenance, "_editor_backend_ready",
                        lambda target, db_identity: True)
    calls = []
    monkeypatch.setattr(maintenance, "_editor_telegram_ready",
                        lambda identity: len(calls) != 0)
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=0)
    result = resume_installed_release(
        "a" * 40, root=root, env_file=None, runner=run,
        freeze_proof=lambda *_: "b" * 64,
    )
    assert result.startswith("READY: Telegram recovered")
    assert calls == [
        ("sudo", "-n", "systemctl", "start", "bybitscanner-telegram.service"),
    ]


def test_partial_editor_resume_blocked_if_telegram_port_still_owned(monkeypatch, tmp_path):
    from tools.paper_maintenance import resume_installed_release
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as identity
    import tools.vps_release_resume as resume
    import tools.legacy_runtime_process as legacy

    root = tmp_path / "release"
    original = root / "deploy/systemd/bybitscanner-telegram.service"
    original.parent.mkdir(parents=True)
    original.write_text("[Service]\nExecStart=/bin/true\n")
    units = tmp_path / "systemd"
    units.mkdir()
    (units / original.name).write_bytes(original.read_bytes())
    monkeypatch.setattr(resume, "UNIT_DIR", units)
    monkeypatch.setattr(resume, "_systemd_state",
                        lambda unit: {"ActiveState": "inactive", "MainPID": "0"})
    monkeypatch.setattr(identity, "verify_release", lambda path: "a" * 40)
    monkeypatch.setattr(legacy, "probe_listener_pids", lambda host, port: (-1,))
    monkeypatch.setattr(maintenance, "_editor_backend_ready", lambda *args: True)
    monkeypatch.setattr(maintenance, "_editor_telegram_ready", lambda *_: False)
    calls = []
    result = resume_installed_release(
        "a" * 40, root=root, env_file=None,
        runner=lambda argv, **_: calls.append(argv),
        freeze_proof=lambda *_: "b" * 64,
    )
    assert result.startswith("BLOCKED: Telegram_owner_or_release_not_proven")
    assert not calls


def test_partial_editor_resume_rejects_active_telegram_unit_without_restarting(monkeypatch, tmp_path):
    from tools.paper_maintenance import resume_installed_release
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as identity
    import tools.vps_release_resume as resume
    import tools.legacy_runtime_process as legacy

    root = tmp_path / "release"
    source = root / "deploy/systemd/bybitscanner-telegram.service"
    source.parent.mkdir(parents=True)
    source.write_text("[Service]\\nExecStart=/bin/true\\n")
    units = tmp_path / "systemd"
    units.mkdir()
    (units / source.name).write_bytes(source.read_bytes())
    monkeypatch.setattr(resume, "UNIT_DIR", units)
    monkeypatch.setattr(resume, "_systemd_state",
                        lambda _: {"ActiveState": "active", "MainPID": "1234"})
    monkeypatch.setattr(identity, "verify_release", lambda _: "a" * 40)
    monkeypatch.setattr(legacy, "probe_listener_pids", lambda *_: ())
    monkeypatch.setattr(maintenance, "_editor_backend_ready", lambda *_: True)
    monkeypatch.setattr(maintenance, "_editor_telegram_ready", lambda *_: False)
    calls = []
    result = resume_installed_release(
        "a" * 40, root=root, env_file=None,
        runner=lambda argv, **_: calls.append(tuple(argv)),
        freeze_proof=lambda *_: "b" * 64,
    )
    assert result.startswith("BLOCKED: Telegram_owner_or_release_not_proven")
    assert not calls


def test_staged_gitless_editor_executes_one_stop_then_install_and_resume(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    steps = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    result = deploy_staged_editor_only(
        "a" * 40, stage=stage, root=root, env_file=None,
        preflight=lambda *_args, **_kw: steps.append("preflight"),
        stop=lambda scope: (steps.append("stop"), stopped)[1],
        installer=lambda *_args, **kw: (
            steps.append(("install", kw["stopped_proof"] is stopped)),
            "INSTALLED_STOPPED: exact"
        )[1],
        resume=lambda *_args, **_kw: (steps.append("resume"), "READY: EDITOR_ONLY")[1],
        transactions=tmp_path / "transactions", trusted_uid=os.geteuid(),
    )
    assert result == "READY: EDITOR_ONLY"
    assert steps == ["preflight", "stop", ("install", True), "resume"]


def test_staged_gitless_editor_rejected_stop_never_installs(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    steps = []
    result = deploy_staged_editor_only(
        "a" * 40, stage=stage, root=root,
        preflight=lambda *_args, **_kw: steps.append("preflight"),
        stop=lambda scope: (
            steps.append("stop"),
            SimpleNamespace(ok=False, runtime_stopped=False)
        )[1],
        installer=lambda *_args, **_kw: pytest.fail("no install after refused stop"),
        resume=lambda *_args, **_kw: pytest.fail("no resume after refused stop"),
        transactions=tmp_path / "transactions", trusted_uid=os.geteuid(),
    )
    assert result.startswith("BLOCKED: canonical_safe_stop_unproven")
    assert steps == ["preflight", "stop"]



def test_staged_gitless_unknown_stop_never_replayed_without_install_journal(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    target = "a" * 40
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    calls = []
    def stop(_scope):
        calls.append("stop")
        raise OSError("stop outcome lost after dispatch")
    def blocked_installer(*_args, **_kwargs):
        pytest.fail("never install without successful STOP receipt")
    kwargs = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kwargs: None,
        stop=stop, installer=blocked_installer,
        resume=lambda *_args, **_kwargs: pytest.fail("must not resume"),
    )
    first = deploy_staged_editor_only(target, **kwargs)
    assert first.startswith("BLOCKED:")
    assert calls == ["stop"]
    assert (transactions / (".stop-invoked-" + target)).is_file()
    second = deploy_staged_editor_only(target, **kwargs)
    assert second.startswith("BLOCKED: prior_STOP_outcome_unproven_without_install_journal")
    assert calls == ["stop"]
    assert not (transactions / target).exists()



def test_staged_gitless_confirmed_stop_crash_window_resumes_without_stop(
    monkeypatch, tmp_path,
):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    target = "a" * 40
    root = tmp_path / "installed"
    stage = tmp_path / "stage"
    transactions = tmp_path / "transactions"
    root.mkdir()
    stage.mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    events = []
    fail = [True]

    def stop(scope):
        events.append(("stop", scope))
        return SimpleNamespace(ok=True, runtime_stopped=True)

    def install(_sha, **kwargs):
        events.append(("install", kwargs["stopped_proof"].runtime_stopped))
        if fail[0]:
            raise OSError("crash before journal creation")
        return "INSTALLED_STOPPED: verified"

    def preflight(*_args, **_kw):
        events.append(("preflight", True))

    args = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=preflight,
        stop=stop, installer=install,
        resume=lambda *_args, **_kw: "READY: EDITOR_ONLY",
    )
    assert deploy_staged_editor_only(target, **args).startswith(
        "BLOCKED: Gitless_switch_unproven:OSError"
    )
    assert (transactions / (".stop-confirmed-" + target)).is_file()
    assert not (transactions / target).exists()
    fail[0] = False
    assert deploy_staged_editor_only(target, **args) == "READY: EDITOR_ONLY"
    assert events == [
        ("preflight", True), ("stop", "all"), ("install", True),
        ("preflight", True), ("install", True),
    ]


def test_staged_gitless_old_sha_change_blocks_stop_receipt_reuse(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    stage = tmp_path / "stage"
    transactions = tmp_path / "transactions"
    root.mkdir()
    stage.mkdir()
    old = ["b" * 40]
    monkeypatch.setattr(release, "verify_release", lambda *_: old[0])
    events = []

    def stop(_scope):
        events.append("stop")
        return SimpleNamespace(ok=True, runtime_stopped=True)

    def install(*_args, **_kw):
        events.append("install")
        raise OSError("crash before journal")

    args = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kw: None,
        stop=stop, installer=install,
    )
    assert deploy_staged_editor_only("a" * 40, **args).startswith("BLOCKED:")
    old[0] = "c" * 40
    assert "stop_completed_receipt_mismatch" in deploy_staged_editor_only(
        "a" * 40, **args
    )
    assert events == ["stop", "install"]


def test_staged_gitless_corrupted_stop_confirmation_blocks_without_mutation(
    monkeypatch, tmp_path,
):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    stage = tmp_path / "stage"
    transactions = tmp_path / "transactions"
    root.mkdir()
    stage.mkdir()
    transactions.mkdir(mode=0o700)
    target = "a" * 40
    (transactions / (".stop-invoked-" + target)).write_bytes(
        b"STOP_INVOKED; not install authorization\\n"
    )
    (transactions / (".stop-confirmed-" + target)).write_text("tampered")
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    result = deploy_staged_editor_only(
        target, stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(),
        preflight=lambda *_a, **_kw: pytest.fail("no preflight for corrupt receipt"),
        stop=lambda *_a: pytest.fail("no STOP replay"),
        installer=lambda *_a, **_kw: pytest.fail("no install"),
    )
    assert "stop_completed_receipt_mismatch" in result


def test_staged_gitless_unwritten_stop_confirmation_never_authorizes_install(
    monkeypatch, tmp_path,
):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    stage = tmp_path / "stage"
    transactions = tmp_path / "transactions"
    root.mkdir()
    stage.mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    actual = maintenance._confirmed_stop_receipt
    def failed_record(*args, **kwargs):
        if kwargs.get("record"):
            raise OSError("write failed")
        return actual(*args, **kwargs)
    monkeypatch.setattr(maintenance, "_confirmed_stop_receipt", failed_record)
    calls = []
    kwargs = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_a, **_kw: None,
        stop=lambda *_: (calls.append("stop"),
                         SimpleNamespace(ok=True, runtime_stopped=True))[1],
        installer=lambda *_a, **_kw: pytest.fail("no install"),
    )
    assert deploy_staged_editor_only("a" * 40, **kwargs).startswith("BLOCKED:")
    assert deploy_staged_editor_only("a" * 40, **kwargs).startswith(
        "BLOCKED: prior_STOP_outcome_unproven_without_install_journal"
    )
    assert calls == ["stop"]


def test_staged_gitless_rejects_symlink_release_lock_before_stop(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    transactions.mkdir(mode=0o700)
    other = tmp_path / "owner-file"
    other.write_text("preserve")
    (transactions / ".release.lock").symlink_to(other)
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    result = deploy_staged_editor_only(
        "a" * 40, stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(),
        preflight=lambda *_args, **_kw: None,
        stop=lambda *_: pytest.fail("no STOP with untrusted lock"),
        installer=lambda *_args, **_kw: pytest.fail("no installation"),
    )
    assert result.startswith("BLOCKED: Gitless_switch_unproven")
    assert other.read_text() == "preserve"
    assert not (transactions / (".stop-invoked-" + "a" * 40)).exists()


def test_staged_gitless_unknown_stop_exception_is_bounded_and_not_replayed(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    calls = []
    def stop(_scope):
        calls.append("stop")
        raise RuntimeError("owner transport failed after dispatch")
    kwargs = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kw: None,
        stop=stop,
        installer=lambda *_args, **_kw: pytest.fail("no install on unknown stop"),
        resume=lambda *_args, **_kw: pytest.fail("no resume"),
    )
    first = deploy_staged_editor_only("a" * 40, **kwargs)
    assert first.startswith("BLOCKED: canonical_safe_stop_outcome_unknown:RuntimeError")
    second = deploy_staged_editor_only("a" * 40, **kwargs)
    assert second.startswith("BLOCKED: prior_STOP_outcome_unproven_without_install_journal")
    assert calls == ["stop"]
    assert not (transactions / ("a" * 40)).exists()


def test_staged_gitless_different_target_cannot_replay_unresolved_stop(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    monkeypatch.setattr(release, "verify_release", lambda *_: "c" * 40)
    calls = []
    def stop(_scope):
        calls.append("stop")
        raise OSError("unknown stop outcome")
    args = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kw: None,
        stop=stop,
        installer=lambda *_args, **_kw: pytest.fail("no installer"),
        resume=lambda *_args, **_kw: pytest.fail("no resume"),
    )
    assert deploy_staged_editor_only("a" * 40, **args).startswith("BLOCKED:")
    result = deploy_staged_editor_only("b" * 40, **args)
    assert result.startswith("BLOCKED: prior_STOP_outcome_unproven_without_install_journal")
    assert calls == ["stop"]


def test_staged_gitless_completed_release_allows_later_target_without_stop_replay(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    old = "a" * 40
    new = "b" * 40
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    current = ["c" * 40]
    monkeypatch.setattr(release, "verify_release", lambda *_: current[0])
    calls = []

    def install(target, **_kw):
        (transactions / target).mkdir(mode=0o700, exist_ok=True)
        return "INSTALLED_STOPPED: exact"

    def resume(target, **_kw):
        current[0] = target
        return "READY: EDITOR_ONLY"

    def stop(_scope):
        calls.append("stop")
        return SimpleNamespace(ok=True, runtime_stopped=True)

    args = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kw: None,
        stop=stop, installer=install, resume=resume,
    )
    assert deploy_staged_editor_only(old, **args) == "READY: EDITOR_ONLY"
    assert (transactions / old / "editor-ready").read_bytes() == old.encode()
    assert deploy_staged_editor_only(new, **args) == "READY: EDITOR_ONLY"
    assert calls == ["stop", "stop"]
    assert (transactions / new / "editor-ready").read_bytes() == new.encode()


def test_staged_gitless_failed_resume_never_marks_prior_release_complete(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    monkeypatch.setattr(release, "verify_release", lambda *_: "c" * 40)
    calls = []

    def stop(_scope):
        calls.append("stop")
        return SimpleNamespace(ok=True, runtime_stopped=True)

    def install(target, **_kw):
        (transactions / target).mkdir(mode=0o700, exist_ok=True)
        return "INSTALLED_STOPPED: exact"

    args = dict(
        stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kw: None,
        stop=stop, installer=install,
        resume=lambda *_args, **_kw: "BLOCKED: editor_postconditions_unproven",
    )
    assert deploy_staged_editor_only("a" * 40, **args).startswith("BLOCKED:")
    assert not (transactions / ("a" * 40) / "editor-ready").exists()
    assert deploy_staged_editor_only("b" * 40, **args).startswith("BLOCKED:")
    assert calls == ["stop"]


def test_staged_gitless_corrupt_completed_receipt_blocks_next_stop(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    transactions.mkdir(mode=0o700)
    previous = "a" * 40
    intent = transactions / (".stop-invoked-" + previous)
    intent.write_bytes(b"STOP_INVOKED")
    intent.chmod(0o600)
    prior_journal = transactions / previous
    prior_journal.mkdir(mode=0o700)
    (prior_journal / "editor-ready").write_bytes(b"wrong-target")
    monkeypatch.setattr(release, "verify_release", lambda *_: "c" * 40)
    result = deploy_staged_editor_only(
        "b" * 40, stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kwargs: None,
        stop=lambda *_: pytest.fail("corrupt receipt must not authorize STOP"),
        installer=lambda *_args, **_kwargs: pytest.fail("no install"),
    )
    assert result.startswith("BLOCKED: Gitless_switch_unproven:ActivationBlocked:")
    assert "completed_release_receipt_mismatch" in result
    assert not (transactions / (".stop-invoked-" + "b" * 40)).exists()


def test_staged_gitless_other_target_pending_transaction_blocks_new_stop(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    transactions.mkdir(mode=0o700)
    previous = "a" * 40
    (transactions / (".stop-invoked-" + previous)).write_text("STOP_INVOKED")
    (transactions / previous).mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "c" * 40)
    result = deploy_staged_editor_only(
        "b" * 40, stage=stage, root=root, transactions=transactions,
        trusted_uid=os.geteuid(), preflight=lambda *_args, **_kwargs: None,
        stop=lambda *_: pytest.fail("do not stop when another release owns transaction"),
        installer=lambda *_args, **_kw: pytest.fail("do not install"),
    )
    assert result.startswith("BLOCKED:")
    assert not (transactions / (".stop-invoked-" + "b" * 40)).exists()


def test_staged_gitless_editor_recovery_of_partial_install_never_replays_stop(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    from tools.vps_release_identity import ReleaseIdentityBlocked
    import tools.vps_release_identity as release
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    (transactions / ("a" * 40)).mkdir(parents=True)
    monkeypatch.setattr(
        release, "verify_release",
        lambda *_: (_ for _ in ()).throw(ReleaseIdentityBlocked("partial copy")),
    )
    steps = []
    result = deploy_staged_editor_only(
        "a" * 40, stage=stage, root=root, transactions=transactions,
        stop=lambda *_: pytest.fail("a partial-install resume cannot stop again"),
        preflight=lambda *_args, **_kw: pytest.fail("old files may be partially copied"),
        installer=lambda *_args, **kw: (
            steps.append(("resumed_install", kw["stopped_proof"] is None)),
            "INSTALLED_STOPPED: exact"
        )[1],
        resume=lambda *_args, **_kw: (steps.append("editor"), "READY: EDITOR_ONLY")[1],
    )
    assert result == "READY: EDITOR_ONLY"
    assert steps == [("resumed_install", True), "editor"]


def test_staged_gitless_editor_existing_target_only_resumes(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(release, "verify_release", lambda *_: "a" * 40)
    assert deploy_staged_editor_only(
        "a" * 40, stage=stage, root=root,
        preflight=lambda *_args, **_kw: pytest.fail("no preflight after install"),
        stop=lambda *_: pytest.fail("no repeated stop"),
        installer=lambda *_args, **_kw: pytest.fail("no repeated install"),
        resume=lambda *_args, **_kw: "READY: existing install",
    ) == "READY: existing install"


def test_staged_gitless_manifest_committed_but_units_incomplete_replays_only_install(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    target = "a" * 40
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    (transactions / target).mkdir(parents=True)
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    steps = []
    def resume(*_args, **_kw):
        steps.append("resume")
        return ("BLOCKED: installed_unit_mismatch" if steps.count("resume") == 1
                else "READY: EDITOR_ONLY")
    result = deploy_staged_editor_only(
        target, stage=stage, root=root, transactions=transactions,
        preflight=lambda *_args, **_kw: pytest.fail("no preflight replay"),
        stop=lambda *_: pytest.fail("no STOP replay"),
        installer=lambda *_args, **kw: (
            steps.append(("install", kw["stopped_proof"] is None)),
            "INSTALLED_STOPPED: recovered"
        )[1],
        resume=resume,
    )
    assert result == "READY: EDITOR_ONLY"
    assert steps == ["resume", ("install", True), "resume"]


def test_staged_gitless_manifest_committed_and_ready_never_reopens_journal(monkeypatch, tmp_path):
    from tools.paper_maintenance import deploy_staged_editor_only
    import tools.vps_release_identity as release

    target = "a" * 40
    root = tmp_path / "installed"
    root.mkdir()
    stage = tmp_path / "stage"
    stage.mkdir()
    transactions = tmp_path / "transactions"
    (transactions / target).mkdir(parents=True)
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    assert deploy_staged_editor_only(
        target, stage=stage, root=root, transactions=transactions,
        stop=lambda *_: pytest.fail("no STOP after already-ready"),
        installer=lambda *_args, **_kw: pytest.fail("no installer against live units"),
        resume=lambda *_args, **_kw: "READY: already installed and running",
    ) == "READY: already installed and running"


def test_standalone_gitless_editor_resume_records_completion_only_after_ready(monkeypatch):
    import tools.paper_maintenance as maintenance

    target = "a" * 40
    calls = []
    monkeypatch.setattr(maintenance, "resume_installed_release",
                        lambda *_args, **_kw: "READY: EDITOR_ONLY")
    monkeypatch.setattr(maintenance, "_complete_stop_intent",
                        lambda *args, **kw: calls.append((args, kw)))
    assert maintenance.main([target, "--resume-installed-editor-only"]) == 0
    assert len(calls) == 1
    assert calls[0][0][1] == target
    assert calls[0][1] == {"uid": 0}

    monkeypatch.setattr(maintenance, "resume_installed_release",
                        lambda *_args, **_kw: "BLOCKED: editor_not_ready")
    assert maintenance.main([target, "--resume-installed-editor-only"]) == 2
    assert len(calls) == 1


def test_standalone_gitless_editor_resume_requires_durable_completion_receipt(monkeypatch):
    import tools.paper_maintenance as maintenance
    from tools.vps_gitless_release_activate import ActivationBlocked

    target = "a" * 40
    monkeypatch.setattr(maintenance, "resume_installed_release",
                        lambda *_args, **_kw: "READY: EDITOR_ONLY")
    def reject_receipt(*_args, **_kw):
        raise ActivationBlocked("untrusted_completed_release_transaction")
    monkeypatch.setattr(maintenance, "_complete_stop_intent", reject_receipt)
    assert maintenance.main([target, "--resume-installed-editor-only"]) == 2


def test_gitless_editor_to_full_paper_reuses_owner_oneshot(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    calls = []
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    monkeypatch.setattr(maintenance, "_durable_editor_freeze",
                        lambda *_: "d" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready",
                        lambda *_: True)
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *_: True)
    monkeypatch.setattr(maintenance, "_paper_full_readiness",
                        lambda **_kw: "READY: full PAPER verified")

    def runner(args, **_kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)

    result = maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY", runner=runner,
    )
    assert result == "READY: full PAPER verified"
    assert calls == [["sudo", "-n", "systemctl", "start",
                      "bybitscanner-paper-start.service"]]


def test_gitless_full_paper_start_refuses_unproven_editor_and_sha(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    calls = []
    runner = lambda *_args, **_kw: calls.append("start")
    assert maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="BLOCKED: editor",
        runner=runner,
    ).startswith("BLOCKED:")
    monkeypatch.setattr(release, "verify_release", lambda *_: "b" * 40)
    assert maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY",
        runner=runner,
    ) == "BLOCKED: installed_release_differs_from_approved_target"
    assert calls == []


def test_gitless_full_paper_start_unknown_systemd_outcome_never_replays(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    calls = []
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    monkeypatch.setattr(maintenance, "_durable_editor_freeze", lambda *_: "d" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready", lambda *_: True)
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *_: True)

    def runner(*_args, **_kwargs):
        calls.append("start")
        raise subprocess.TimeoutExpired("systemctl", 300)

    result = maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY", runner=runner,
    )
    assert result == "BLOCKED: PAPER_core_start_outcome_unknown; no replay"
    assert calls == ["start"]


def test_editor_only_never_starts_paper_with_frozen_orphan_or_approvals(
    monkeypatch, tmp_path,
):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    calls = []
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    monkeypatch.setattr(maintenance, "_durable_editor_freeze", lambda *_: "d" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready", lambda *_: True)
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *_: False)
    monkeypatch.setattr(
        maintenance, "_editor_reconcile_once",
        lambda *_a, **_kw: "BLOCKED: Editor_Robot_reconcile_preflight_unproven; PAPER_START_not_attempted",
    )
    result = maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY",
        runner=lambda *_a, **_kw: calls.append("start"),
    )
    assert result == "BLOCKED: Editor_Robot_reconcile_preflight_unproven; PAPER_START_not_attempted"
    assert calls == []


def test_editor_only_reconciles_once_then_starts_only_after_full_postproof(
    monkeypatch, tmp_path,
):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    events = []
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    monkeypatch.setattr(maintenance, "_durable_editor_freeze",
                        lambda *_: "d" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready", lambda *_: True)
    proofs = iter([False, True])
    monkeypatch.setattr(maintenance, "_paper_start_quiescent",
                        lambda *_: next(proofs))
    monkeypatch.setattr(maintenance, "_editor_reconcile_once",
                        lambda *_a, **_kw: events.append("reconcile"))
    monkeypatch.setattr(maintenance, "_paper_full_readiness",
                        lambda **_kw: "READY: full PAPER proven")

    def runner(args, **_kwargs):
        events.append("start")
        return SimpleNamespace(returncode=0)

    assert maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY",
        runner=runner,
    ) == "READY: full PAPER proven"
    assert events == ["reconcile", "start"]


def test_editor_only_does_not_start_on_failed_reconcile_postproof(
    monkeypatch, tmp_path,
):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    events = []
    monkeypatch.setattr(release, "verify_release", lambda *_: target)
    monkeypatch.setattr(maintenance, "_durable_editor_freeze",
                        lambda *_: "d" * 64)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready", lambda *_: True)
    monkeypatch.setattr(maintenance, "_paper_start_quiescent", lambda *_: False)
    monkeypatch.setattr(maintenance, "_editor_reconcile_once",
                        lambda *_a, **_kw: events.append("reconcile"))
    assert maintenance.start_installed_paper_from_editor(
        target, root=tmp_path, editor_status="READY: EDITOR_ONLY",
        runner=lambda *_a, **_kw: events.append("start"),
    ) == "BLOCKED: PAPER_stale_owners_after_reconcile; START_not_attempted"
    assert events == ["reconcile"]


def test_editor_reconcile_never_retries_unknown_owner_outcome(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as http

    calls = []
    proofs = iter([True, True])
    intents = iter([True, False])
    monkeypatch.setattr(maintenance, "_editor_flat_reconcile_preflight",
                        lambda *_: next(proofs))
    monkeypatch.setattr(maintenance, "_record_editor_reconcile_once",
                        lambda *_a, **_kw: next(intents))

    def ambiguous(*_args):
        calls.append("post")
        raise http.Unreachable("timed out after the owner may have committed")

    monkeypatch.setattr(http, "http_post_json", ambiguous)
    assert maintenance._editor_reconcile_once(
        "a" * 40, "d" * 64, root=tmp_path, env_file=None,
    ) == "BLOCKED: Editor_Robot_reconcile_outcome_unknown; no_replay"
    assert maintenance._editor_reconcile_once(
        "a" * 40, "d" * 64, root=tmp_path, env_file=None,
    ) == "BLOCKED: prior_Editor_Robot_reconcile_outcome_unknown; no_replay"
    assert calls == ["post"]


def test_editor_reconcile_http_success_not_enough_without_durable_postproof(
    monkeypatch, tmp_path,
):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as http

    monkeypatch.setattr(maintenance, "_editor_flat_reconcile_preflight",
                        lambda *_: True)
    monkeypatch.setattr(maintenance, "_record_editor_reconcile_once",
                        lambda *_a, **_kw: True)
    calls = []
    monkeypatch.setattr(
        http, "http_post_json",
        lambda url, payload, timeout: (
            calls.append((url, payload, timeout)) or
            SimpleNamespace(status=200, json=lambda: {"ok": True, "success": True})
        ),
    )
    assert maintenance._editor_reconcile_once(
        "a" * 40, "d" * 64, root=tmp_path, env_file=None,
    ) is None
    assert len(calls) == 1
    assert calls[0][0].endswith("/api/robot/reconcile")
    assert calls[0][1] == {}


def test_editor_reconcile_one_shot_receipt_cannot_replay(tmp_path):
    import tools.paper_maintenance as maintenance

    sha = "a" * 40
    identity = "d" * 64
    journal = tmp_path / sha
    journal.mkdir(mode=0o700)
    ready = journal / "editor-ready"
    ready.write_text(sha)
    ready.chmod(0o600)
    assert maintenance._record_editor_reconcile_once(
        sha, identity, journal_root=tmp_path, trusted_uid=os.getuid(),
    )
    assert (journal / "robot-reconcile-invoked").read_text() == sha + "\n" + identity + "\n"
    assert not maintenance._record_editor_reconcile_once(
        sha, identity, journal_root=tmp_path, trusted_uid=os.getuid(),
    )


def test_editor_flat_reconcile_preflight_refuses_exposure_or_unexpected_owner(
    monkeypatch, tmp_path,
):
    import tools.paper_maintenance as maintenance
    import tools.stop_robot_runtime as shutdown
    from tools.paper_incident_approvals import (
        IDLE_APPROVALS, JASMY_CANDIDATE_ID, JASMY_TRADE_ID,
    )

    db = tmp_path / "paper.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(f"""
            CREATE TABLE robot_runtime_state (
                trading_account_id TEXT, mode TEXT, recovery_status TEXT);
            CREATE TABLE scanner_runtime_state (
                trading_account_id TEXT, mode TEXT);
            CREATE TABLE robot_autopilot_state (
                trading_account_id TEXT, mode TEXT);
            CREATE TABLE position_projections (
                trading_account_id TEXT, symbol TEXT, side TEXT,
                quantity TEXT, sync_state TEXT);
            CREATE TABLE robot_trades (
                trading_account_id TEXT, trade_id TEXT, candidate_id TEXT,
                symbol TEXT, exit_time_ms INTEGER);
            CREATE TABLE robot_candidates (
                trading_account_id TEXT, candidate_id TEXT, symbol TEXT, status TEXT,
                approved_at_ms INTEGER, state_revision INTEGER, robot_state_json TEXT);
            CREATE TABLE paper_limit_orders (
                trading_account_id TEXT, status TEXT, order_id TEXT,
                symbol TEXT, created_at_ms INTEGER);
            CREATE TABLE trading_commands (
                trading_account_id TEXT, current_state TEXT, symbol TEXT,
                created_at_ms INTEGER);
            CREATE TABLE executions (
                trading_account_id TEXT, symbol TEXT, exchange_timestamp_ms INTEGER);
            CREATE TABLE robot_entry_orders (
                trading_account_id TEXT, order_id TEXT);
            CREATE TABLE box_attempt_ownership (
                trading_account_id TEXT, candidate_id TEXT);
            CREATE TABLE paper_protection_obligations (
                trading_account_id TEXT, status TEXT);
            CREATE TABLE reconciliation_checkpoints (
                trading_account_id TEXT, completed_at_ms INTEGER);
            INSERT INTO robot_runtime_state VALUES
                ('paper','ROBOT_RUNNING','RECONCILIATION_REQUIRED');
            INSERT INTO scanner_runtime_state VALUES ('paper','SCANNER_STOPPED');
            INSERT INTO robot_autopilot_state VALUES ('paper','OFF');
            INSERT INTO position_projections VALUES
                ('paper','JASMYUSDT','Flat','0','synced');
            INSERT INTO position_projections VALUES
                ('paper','FLOWUSDT','Flat','0','synced');
            INSERT INTO robot_trades VALUES
                ('paper','{JASMY_TRADE_ID}','{JASMY_CANDIDATE_ID}','JASMYUSDT',NULL);
            INSERT INTO robot_trades VALUES
                ('paper','unattested-flow-trade','flow','FLOWUSDT',NULL);
            INSERT INTO robot_candidates VALUES
                ('paper','{JASMY_CANDIDATE_ID}','JASMYUSDT','OPEN',100,0,NULL);
            INSERT INTO robot_candidates VALUES
                ('paper','flow','FLOWUSDT','OPEN',100,0,NULL);
        """)
        for symbol, (prefix, suffix) in IDLE_APPROVALS.items():
            cid = prefix if not suffix else prefix + ("0" * 32) + suffix
            conn.execute(
                "INSERT INTO robot_candidates VALUES ('paper',?,?, 'APPROVED',200,0,NULL)",
                (cid, symbol),
            )

    monkeypatch.setattr(shutdown, "_database_path", lambda *_: db)
    preflight = lambda: maintenance._editor_flat_reconcile_preflight(tmp_path, None)
    assert preflight()

    # One or zero OPEN lots are not the exact historic two-orphan incident.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE robot_trades SET exit_time_ms=200 WHERE symbol='FLOWUSDT'")
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE robot_trades SET exit_time_ms=200 WHERE symbol='JASMYUSDT'")
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE robot_trades SET exit_time_ms=NULL")
    assert preflight()

    # A new JASMY trade may be Flat and use the same symbol; it must not
    # inherit permission to invoke the historical owner reconciliation.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE robot_trades SET trade_id='foreign-jasmy-trade' "
            "WHERE symbol='JASMYUSDT'"
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE robot_trades SET trade_id=? WHERE symbol='JASMYUSDT'",
            (JASMY_TRADE_ID,),
        )
        conn.execute(
            "UPDATE robot_trades SET candidate_id='foreign-jasmy-candidate' "
            "WHERE symbol='JASMYUSDT'"
        )
        conn.execute(
            "UPDATE robot_candidates SET candidate_id='foreign-jasmy-candidate' "
            "WHERE symbol='JASMYUSDT' AND status='OPEN'"
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE robot_trades SET candidate_id=? WHERE symbol='JASMYUSDT'",
            (JASMY_CANDIDATE_ID,),
        )
        conn.execute(
            "UPDATE robot_candidates SET candidate_id=? "
            "WHERE symbol='JASMYUSDT' AND status='OPEN'",
            (JASMY_CANDIDATE_ID,),
        )
    assert preflight()

    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE position_projections SET side='Long', quantity='1' "
            "WHERE symbol='FLOWUSDT'"
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE position_projections SET side='Flat', quantity='0' "
            "WHERE symbol='FLOWUSDT'"
        )
        conn.execute(
            "INSERT INTO robot_candidates VALUES "
            "('paper','alien','DOGEUSDT','APPROVED',200,0,NULL)"
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM robot_candidates WHERE candidate_id='alien'")
        conn.execute(
            "INSERT INTO paper_limit_orders (trading_account_id,status) "
            "VALUES ('paper','open')"
        )
    assert not preflight()


    # Neither a familiar symbol nor Flat is identity/admission evidence.
    bnc = IDLE_APPROVALS["BNCUSDT"][0]
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM paper_limit_orders")
        conn.execute(
            "UPDATE robot_candidates SET candidate_id='spoofed' WHERE candidate_id=?",
            (bnc,),
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE robot_candidates SET candidate_id=?, state_revision=1 "
            "WHERE candidate_id='spoofed'", (bnc,),
        )
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE robot_candidates SET state_revision=0 WHERE candidate_id=?", (bnc,)
        )
        conn.execute("INSERT INTO executions VALUES ('paper','BNCUSDT',200)")
    assert not preflight()
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM executions")
        conn.execute("INSERT INTO box_attempt_ownership VALUES ('paper',?)", (bnc,))
    assert not preflight()


def test_paper_start_quiescence_checks_durable_frozen_ledgers(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.stop_robot_runtime as shutdown

    db = tmp_path / "paper.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript("""
            CREATE TABLE robot_runtime_state (
                trading_account_id TEXT, mode TEXT, recovery_status TEXT
            );
            CREATE TABLE position_projections (
                trading_account_id TEXT, symbol TEXT, side TEXT,
                quantity TEXT, sync_state TEXT
            );
            CREATE TABLE robot_trades (trading_account_id TEXT, exit_time_ms INTEGER);
            CREATE TABLE robot_candidates (trading_account_id TEXT, status TEXT);
            CREATE TABLE paper_limit_orders (trading_account_id TEXT, status TEXT);
            CREATE TABLE trading_commands (trading_account_id TEXT, current_state TEXT);
            CREATE TABLE paper_protection_obligations (trading_account_id TEXT, status TEXT);
            CREATE TABLE reconciliation_checkpoints (
                trading_account_id TEXT, completed_at_ms INTEGER
            );
            INSERT INTO robot_runtime_state VALUES
                ('paper','ROBOT_STOPPED','ROBOT_STOPPED');
        """)
    monkeypatch.setattr(shutdown, "_database_path", lambda *_: db)
    assert maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO robot_candidates VALUES ('paper','APPROVED')")
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    # Only proven terminal Robot candidate states can coexist with a restart.
    # Unknown/corrupt future states must block instead of silently passing.
    for status in ("OPEN", "UNKNOWN_FUTURE_STATE", None):
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE robot_candidates SET status=?", (status,))
        assert not maintenance._paper_start_quiescent(tmp_path, None)
    for status in ("BOX_PLAN_ONLY", "CLOSED", "EXPIRED", "INVALIDATED"):
        with sqlite3.connect(db) as conn:
            conn.execute("UPDATE robot_candidates SET status=?", (status,))
        assert maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM robot_candidates")
        conn.execute("UPDATE robot_runtime_state "
                     "SET mode='ROBOT_RUNNING', recovery_status='RECONCILIATION_REQUIRED'")
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    # Canonical Robot reconcile commits PAUSED, not READY. Starting the
    # owner oneshot from proven PAUSED is the legitimate PAUSED -> READY path.
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE robot_runtime_state SET recovery_status='PAUSED'")
    assert maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO robot_candidates VALUES ('paper','APPROVED')")
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM robot_candidates")
        conn.execute("INSERT INTO robot_trades VALUES ('paper',NULL)")
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("DELETE FROM robot_trades")
        conn.execute("UPDATE robot_runtime_state SET recovery_status='READY'")
    assert maintenance._paper_start_quiescent(tmp_path, None)

    # Manual PAPER exposure has no Robot-owned trade or approval. It must
    # still forbid the systemd oneshot from re-enabling entry admission.
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO position_projections VALUES "
            "('paper','TESTUSDT','Long','2','synced')"
        )
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE position_projections SET side='Flat', quantity='0'"
        )
    assert maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE position_projections SET sync_state='unknown'")
    assert not maintenance._paper_start_quiescent(tmp_path, None)
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE position_projections SET sync_state='synced', quantity='NaN'")
    assert not maintenance._paper_start_quiescent(tmp_path, None)


def test_gitless_repeated_full_start_is_read_only(monkeypatch):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    monkeypatch.setattr(release, "verify_release", lambda *_args, **_kw: target)
    calls = []
    monkeypatch.setattr(maintenance, "_paper_full_readiness",
                        lambda **_kw: "READY: full PAPER proven")
    monkeypatch.setattr(maintenance, "deploy_staged_editor_only",
                        lambda *_args, **_kw: calls.append("deploy"))
    monkeypatch.setattr(maintenance, "resume_installed_release",
                        lambda *_args, **_kw: calls.append("resume"))
    monkeypatch.setattr(maintenance, "start_installed_paper_from_editor",
                        lambda *_args, **_kw: calls.append("start"))
    assert maintenance.main([
        target, "--staged-gitless-editor-only", "/staged/release",
        "--start-paper-after-editor",
    ]) == 0
    assert maintenance.main([
        target, "--resume-installed-editor-only", "--start-paper-after-editor",
    ]) == 0
    assert calls == []


def test_gitless_full_start_unproven_runtime_does_not_skip_recovery(monkeypatch):
    import tools.paper_maintenance as maintenance
    import tools.vps_release_identity as release

    target = "a" * 40
    monkeypatch.setattr(release, "verify_release", lambda *_args, **_kw: target)
    monkeypatch.setattr(maintenance, "_paper_full_readiness",
                        lambda **_kw: "BLOCKED: PAPER not proven")
    monkeypatch.setattr(maintenance, "resume_installed_release",
                        lambda *_args, **_kw: "BLOCKED: EDITOR_ONLY freeze unproven")
    monkeypatch.setattr(maintenance, "start_installed_paper_from_editor",
                        lambda *_args, **_kw: pytest.fail("must not start"))
    assert maintenance.main([
        target, "--resume-installed-editor-only", "--start-paper-after-editor",
    ]) == 2


@pytest.mark.parametrize("endpoint", (
    "/api/health",
    "/api/robot/protection-health",
    "/api/scanner/status",
    "/api/robot/autopilot",
))
def test_paper_readiness_unreachable_endpoint_blocks(monkeypatch, tmp_path, endpoint):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    payloads = {
        "/api/health": {"ok": True, "component": "paper_backend",
                        "mode": "paper", "paper_live_safe": True,
                        "scanner_acceptance_ready": True,
                        "robot_admission_ready": True},
        "/api/robot/protection-health": {"healthy": True},
        "/api/scanner/status": {"mode": "SCANNER_RUNNING"},
        "/api/robot/autopilot": {"ok": True, "mode": "PAPER_AUTO",
                                 "trading_account_id": {"value": "paper"}},
    }

    def api(url, _timeout):
        path = next(path for path in payloads if url.endswith(path))
        if path == endpoint:
            raise runtime_intent.Unreachable("connection refused")
        return SimpleNamespace(status=200, json=lambda: payloads[path])

    monkeypatch.setattr(runtime_intent, "http_get", api)
    result = maintenance._paper_full_readiness(
        root=tmp_path, env_file=None, readiness=lambda: True,
    )
    assert result.startswith("BLOCKED: PAPER core started but")


@pytest.mark.parametrize("endpoint", (
    "/api/health",
    "/api/robot/protection-health",
    "/api/scanner/status",
    "/api/robot/autopilot",
))
@pytest.mark.parametrize("malformed", (None, [], "not-an-object"))
def test_paper_readiness_rejects_malformed_http_json(monkeypatch, tmp_path, endpoint, malformed):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    payloads = {
        "/api/health": {"ok": True, "component": "paper_backend",
                        "mode": "paper", "paper_live_safe": True,
                        "scanner_acceptance_ready": True,
                        "robot_admission_ready": True, "build_sha": "a" * 40},
        "/api/robot/protection-health": {"healthy": True},
        "/api/scanner/status": {"mode": "SCANNER_RUNNING"},
        "/api/robot/autopilot": {"ok": True, "mode": "PAPER_AUTO",
                                 "trading_account_id": {"value": "paper"}},
    }

    def api(url, _timeout):
        path = next(path for path in payloads if url.endswith(path))
        body = malformed if path == endpoint else payloads[path]
        return SimpleNamespace(status=200, json=lambda: body)

    monkeypatch.setattr(runtime_intent, "http_get", api)
    result = maintenance._paper_full_readiness(
        root=tmp_path, env_file=None, target="a" * 40, readiness=lambda: True,
    )
    assert result.startswith("BLOCKED: PAPER core started but")


@pytest.mark.parametrize("admission", (False, None, 0, "true"))
def test_full_paper_readiness_requires_canonical_robot_admission(monkeypatch, tmp_path, admission):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    payloads = {
        "/api/health": {
            "ok": True, "component": "paper_backend",
            "mode": "paper", "paper_live_safe": True,
            "scanner_acceptance_ready": True,
            "robot_admission_ready": admission, "build_sha": "a" * 40,
        },
        "/api/robot/protection-health": {"healthy": True},
        "/api/scanner/status": {"mode": "SCANNER_RUNNING"},
        "/api/robot/autopilot": {"ok": True, "mode": "PAPER_AUTO",
                                 "trading_account_id": {"value": "paper"}},
    }

    def api(url, _timeout):
        path = next(path for path in payloads if url.endswith(path))
        return SimpleNamespace(status=200, json=lambda: payloads[path])

    monkeypatch.setattr(runtime_intent, "http_get", api)
    result = maintenance._paper_full_readiness(
        root=tmp_path, env_file=None, target="a" * 40, readiness=lambda: True,
    )
    assert result.startswith("BLOCKED: PAPER core started but")
    assert "readiness not proven" in result



@pytest.mark.parametrize("endpoint,field,invalid", (
    ("/api/health", "ok", False),
    ("/api/health", "component", "unrelated_backend"),
    ("/api/robot/protection-health", "ok", False),
    ("/api/scanner/status", "ok", False),
    ("/api/robot/autopilot", "ok", False),
    ("/api/health", "database_identity", "e" * 64),
    ("/api/health", "database_identity", None),
))
def test_paper_readiness_rejects_unattributed_or_foreign_owner(
    monkeypatch, tmp_path, endpoint, field, invalid,
):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    identity = "d" * 64
    monkeypatch.setattr(runtime_intent, "expected_database_identity",
                        lambda *_a, **_kw: identity)
    payloads = {
        "/api/health": {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "paper_live_safe": True, "robot_admission_ready": True,
            "scanner_acceptance_ready": True,
            "build_sha": "a" * 40, "database_identity": identity,
        },
        "/api/robot/protection-health": {"ok": True, "healthy": True},
        "/api/scanner/status": {"ok": True, "mode": "SCANNER_RUNNING"},
        "/api/robot/autopilot": {"ok": True, "mode": "PAPER_AUTO",
                                 "trading_account_id": {"value": "paper"}},
    }
    def api(url, _timeout):
        path = next(path for path in payloads if url.endswith(path))
        return SimpleNamespace(status=200, json=lambda: payloads[path])

    monkeypatch.setattr(runtime_intent, "http_get", api)
    args = dict(root=tmp_path, env_file=None, target="a" * 40,
                readiness=lambda: True)
    assert maintenance._paper_full_readiness(**args).startswith("READY:")
    payloads[endpoint][field] = invalid
    result = maintenance._paper_full_readiness(**args)
    assert result.startswith("BLOCKED:")
    if field == "database_identity":
        assert "database_identity_unproven" in result
    else:
        assert "readiness not proven" in result



@pytest.mark.parametrize("endpoint,field,bad", (
    ("/api/health", "scanner_acceptance_ready", False),
    ("/api/health", "scanner_acceptance_ready", None),
    ("/api/robot/autopilot", "trading_account_id", {"value": "live"}),
    ("/api/robot/autopilot", "trading_account_id", None),
))
def test_paper_readiness_matches_authorized_start_acceptance(
    monkeypatch, tmp_path, endpoint, field, bad,
):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    identity = "d" * 64
    monkeypatch.setattr(runtime_intent, "expected_database_identity",
                        lambda *_a, **_kw: identity)
    payloads = {
        "/api/health": {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "paper_live_safe": True, "robot_admission_ready": True,
            "scanner_acceptance_ready": True,
            "build_sha": "a" * 40, "database_identity": identity,
        },
        "/api/robot/protection-health": {"ok": True, "healthy": True},
        "/api/scanner/status": {"ok": True, "mode": "SCANNER_RUNNING"},
        "/api/robot/autopilot": {
            "ok": True, "mode": "PAPER_AUTO",
            "trading_account_id": {"value": "paper"},
        },
    }

    def get(url, _timeout):
        key = next(key for key in payloads if url.endswith(key))
        return SimpleNamespace(status=200, json=lambda: payloads[key])

    monkeypatch.setattr(runtime_intent, "http_get", get)
    args = dict(root=tmp_path, env_file=None, readiness=lambda: True,
                target="a" * 40)
    assert maintenance._paper_full_readiness(**args).startswith("READY:")
    payloads[endpoint][field] = bad
    assert maintenance._paper_full_readiness(**args).startswith(
        "BLOCKED: PAPER core started but"
    )


@pytest.mark.parametrize("endpoint,field,bad", (
    ("/api/scanner/status", "ok", False),
    ("/api/robot/autopilot", "ok", False),
    ("/api/robot/autopilot", "trading_account_id", {"value": "live"}),
))
def test_editor_only_probe_requires_proven_frozen_owner(
    monkeypatch, endpoint, field, bad,
):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    target = "a" * 40
    identity = "d" * 64
    payloads = {
        "/api/health": {
            "ok": True, "component": "paper_backend", "mode": "paper",
            "paper_live_safe": True, "build_sha": target,
            "database_identity": identity,
        },
        "/api/scanner/status": {"ok": True, "mode": "SCANNER_STOPPED"},
        "/api/robot/autopilot": {
            "ok": True, "mode": "OFF",
            "trading_account_id": {"value": "paper"},
        },
    }

    def get(url, _timeout):
        key = next(key for key in payloads if url.endswith(key))
        return SimpleNamespace(status=200, json=lambda: payloads[key])

    monkeypatch.setattr(runtime_intent, "http_get", get)
    assert maintenance._editor_backend_ready(target, identity)
    payloads[endpoint][field] = bad
    assert not maintenance._editor_backend_ready(target, identity)


def test_full_gitless_readiness_requires_same_db_telegram(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    target = "a" * 40
    identity = "d" * 64
    monkeypatch.setattr(runtime_intent, "expected_database_identity",
                        lambda *_args, **_kw: identity)

    def api(url, _timeout):
        if url.endswith("/api/health"):
            payload = dict(ok=True, component="paper_backend", mode="paper",
                           paper_live_safe=True, robot_admission_ready=True,
                           scanner_acceptance_ready=True,
                           build_sha=target, database_identity=identity)
        elif url.endswith("/api/robot/protection-health"):
            payload = {"ok": True, "healthy": True}
        elif url.endswith("/api/scanner/status"):
            payload = {"ok": True, "mode": "SCANNER_RUNNING"}
        else:
            payload = {"ok": True, "mode": "PAPER_AUTO",
                       "trading_account_id": {"value": "paper"}}
        return SimpleNamespace(status=200, json=lambda: payload)

    monkeypatch.setattr(runtime_intent, "http_get", api)
    telegram_ready = [False]
    monkeypatch.setattr(maintenance, "_editor_telegram_ready",
                        lambda observed: telegram_ready[0] and observed == identity)
    args = dict(root=tmp_path, env_file=None, target=target,
                readiness=lambda: True, require_gitless_telegram=True)
    assert maintenance._paper_full_readiness(**args).startswith(
        "BLOCKED: Gitless_PAPER_Telegram_or_database_identity_unproven"
    )
    telegram_ready[0] = True
    assert maintenance._paper_full_readiness(**args).startswith("READY:")


def test_full_gitless_readiness_rejects_wrong_backend_db_even_with_telegram(monkeypatch, tmp_path):
    import tools.paper_maintenance as maintenance
    import tools.runtime_intent as runtime_intent

    target = "a" * 40
    monkeypatch.setattr(runtime_intent, "expected_database_identity",
                        lambda *_args, **_kw: "d" * 64)
    def api(url, _timeout):
        payload = (
            {"ok": True, "component": "paper_backend", "mode": "paper",
             "paper_live_safe": True, "robot_admission_ready": True,
             "scanner_acceptance_ready": True,
             "build_sha": target, "database_identity": "e" * 64}
            if url.endswith("/api/health") else
            {"ok": True, "healthy": True} if url.endswith("/api/robot/protection-health") else
            {"ok": True, "mode": "SCANNER_RUNNING"} if url.endswith("/api/scanner/status") else
            {"ok": True, "mode": "PAPER_AUTO",
             "trading_account_id": {"value": "paper"}}
        )
        return SimpleNamespace(status=200, json=lambda: payload)
    monkeypatch.setattr(runtime_intent, "http_get", api)
    monkeypatch.setattr(maintenance, "_editor_telegram_ready",
                        lambda *_: pytest.fail("wrong backend DB must block before Telegram"))
    result = maintenance._paper_full_readiness(
        root=tmp_path, env_file=None, target=target,
        readiness=lambda: True, require_gitless_telegram=True,
    )
    assert result.startswith("BLOCKED: Gitless_PAPER_Telegram_or_database_identity_unproven")


def test_exceptional_gitless_receipt_reuses_original_protected_handoff(
    monkeypatch, tmp_path,
):
    import json
    import tools.paper_maintenance as maintenance
    import tools.paper_interrupted_stop_recovery as recovery
    import tools.vps_release_identity as release
    from tools.vps_gitless_release_activate import ActivationBlocked

    target, old = "a" * 40, "b" * 40
    journal_root = tmp_path / "transactions"
    journal = journal_root / target
    journal.mkdir(parents=True, mode=0o700)
    journal_root.chmod(0o700)
    journal.chmod(0o700)
    blobs = {
        "terminal/runtime/paper_http_server.py": "c" * 40,
        "tools/vps_release_identity.py": "d" * 40,
    }
    for filename, sha in (("old.json", old), ("target.json", target)):
        path = journal / filename
        path.write_text(json.dumps({"build_sha": sha, "blobs": blobs}))
        path.chmod(0o600)
    units = journal / "units.json"
    units.write_text("{}")
    units.chmod(0o600)
    stop = journal_root / (".stop-invoked-" + recovery.PRIOR_TARGET)
    stop.write_bytes(b"STOP_INVOKED; not install authorization\\\\n")
    stop.chmod(0o600)
    for phase in ("handoff-proven", "backend-exited"):
        receipt = journal_root / (
            recovery.MARKER_PREFIX + phase + "-" + recovery.PRIOR_TARGET
        )
        receipt.write_text(target + "\\n")
        receipt.chmod(0o600)
    monkeypatch.setattr(release, "verify_release", lambda *_args: target)

    maintenance._complete_stop_intent(journal_root, target, uid=os.getuid())
    ready = journal / "editor-ready"
    assert ready.read_bytes() == target.encode()
    assert ready.stat().st_mode & 0o777 == 0o600
    maintenance._complete_stop_intent(journal_root, target, uid=os.getuid())
    assert ready.read_bytes() == target.encode()

    ready.unlink()
    monkeypatch.setattr(release, "verify_release", lambda *_args: old)
    with pytest.raises(ActivationBlocked, match="exceptional_editor_receipt_proof_unproven"):
        maintenance._complete_stop_intent(journal_root, target, uid=os.getuid())
    assert not ready.exists()

    monkeypatch.setattr(release, "verify_release", lambda *_args: target)
    handoff = journal_root / (
        recovery.MARKER_PREFIX + "handoff-proven-" + recovery.PRIOR_TARGET
    )
    handoff.unlink()
    with pytest.raises(ActivationBlocked, match="exceptional_editor_receipt_proof_unproven"):
        maintenance._complete_stop_intent(journal_root, target, uid=os.getuid())
    assert not ready.exists()


