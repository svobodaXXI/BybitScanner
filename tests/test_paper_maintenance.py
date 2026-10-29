from pathlib import Path
from types import SimpleNamespace

from tools.paper_maintenance import run_maintenance


def fake_runner(calls, *, fail=None):
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        return SimpleNamespace(returncode=1 if tuple(argv) == fail else 0,
                               stdout="a" * 40 if tuple(argv) == ("git", "rev-parse", "--verify", "HEAD") else "")
    return run


def test_rejects_bad_sha_without_stop_or_mutation():
    calls = []
    assert run_maintenance("bad", stop=lambda _: calls.append("stop")) .startswith("BLOCKED:")
    assert calls == []

def test_protected_open_exposure_never_fetches_or_restarts():
    calls = []
    blocked = SimpleNamespace(ok=False, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: blocked, runner=fake_runner(calls))
    assert result.startswith("BLOCKED:")
    assert all(cmd != ("sudo", "-n", "systemctl", "start", "bybitscanner-paper-start.service") for cmd in calls)


def test_safe_stop_required_even_if_result_ok():
    calls = []
    incomplete = SimpleNamespace(ok=True, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: incomplete, runner=fake_runner(calls))
    assert result.startswith("BLOCKED:")
    assert not any("systemctl" in cmd or cmd[:2] == ("git", "merge") for cmd in calls)


def test_approved_target_only_after_safe_stop():
    calls = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    target = "a" * 40
    result = run_maintenance(target, stop=lambda _: stopped,
        runner=fake_runner(calls), root=Path("/opt/BybitScanner"))
    assert result.startswith("CORE_STARTED:")
    assert ("git", "merge-base", "--is-ancestor", target, "origin/stable/adfb50b-forward") in calls
    assert calls[-1] == ("sudo", "-n", "systemctl", "start", "bybitscanner-paper-start.service")


def test_unapproved_target_never_updates_or_starts():
    calls = []
    stopped = SimpleNamespace(ok=True, runtime_stopped=True)
    fail = ("git", "merge-base", "--is-ancestor", "a" * 40, "origin/stable/adfb50b-forward")
    result = run_maintenance("a" * 40, stop=lambda _: stopped,
        runner=fake_runner(calls, fail=fail))
    assert result.startswith("BLOCKED:")
    assert not any(cmd[:2] == ("git", "merge") or "systemctl" in cmd for cmd in calls)


def test_waits_for_canonical_safe_stop_before_mutating_runtime():
    calls = []
    attempts = []
    def stop(_scope):
        attempts.append(len(attempts))
        return SimpleNamespace(ok=len(attempts) >= 2, runtime_stopped=len(attempts) >= 2)
    now = [0.]
    def sleep(seconds):
        now[0] += seconds
    result = run_maintenance("a" * 40, stop=stop,
        runner=fake_runner(calls), wait_seconds=60, poll_seconds=10,
        clock=lambda: now[0], sleep=sleep)
    assert result.startswith("CORE_STARTED:")
    assert len(attempts) == 2


def test_expired_safe_stop_leaves_code_and_service_untouched():
    calls = []
    now = [0.]
    def sleep(seconds):
        now[0] += seconds
    blocked = SimpleNamespace(ok=False, runtime_stopped=False)
    result = run_maintenance("a" * 40, stop=lambda _: blocked,
        runner=fake_runner(calls), wait_seconds=20, poll_seconds=10,
        clock=lambda: now[0], sleep=sleep)
    assert result.startswith("BLOCKED:")
    assert not any(cmd[:2] == ("git", "merge") or "systemctl" in cmd for cmd in calls)
