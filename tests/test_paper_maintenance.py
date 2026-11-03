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
    def get(url, _timeout):
        if url.endswith("/api/health"):
            data = {"mode": "paper", "paper_live_safe": True}
        elif url.endswith("/api/robot/protection-health"):
            data = {"healthy": True}
        elif url.endswith("/api/scanner/status"):
            data = {"mode": "SCANNER_RUNNING"}
        else:
            data = {"mode": "PAPER_AUTO"}
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
        transactions=tmp_path / "transactions",
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
        transactions=tmp_path / "transactions",
    )
    assert result.startswith("BLOCKED: canonical_safe_stop_unproven")
    assert steps == ["preflight", "stop"]


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
