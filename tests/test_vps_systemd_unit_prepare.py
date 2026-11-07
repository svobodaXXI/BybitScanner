"""Offline, mocked systemd regression tests. No real services are touched."""
from types import SimpleNamespace

from tools.vps_systemd_unit_prepare import UNITS, prepare_units


def runner(calls, *, states=None, failures=(), reset_converges=False):
    states = dict(states or {unit: "inactive" for unit in UNITS})
    def run(argv, **kwargs):
        command = tuple(argv)
        calls.append(command)
        if command in failures:
            return SimpleNamespace(returncode=1, stdout="", stderr="failed")
        if argv[1] == "show":
            unit = argv[2]
            if unit not in states:
                return SimpleNamespace(returncode=1, stdout="")
            return SimpleNamespace(returncode=0,
                stdout=f"LoadState=loaded\nActiveState={states[unit]}\n")
        if argv[1] == "reset-failed" and (reset_converges or command not in failures):
            states[argv[2]] = "inactive"
        return SimpleNamespace(returncode=0, stdout="")
    return run


def test_daemon_reload_precedes_all_load_checks_and_reset_only_failed():
    calls = []
    states = {unit: "inactive" for unit in UNITS}
    states[UNITS[1]] = "failed"
    result = prepare_units(run=runner(calls, states=states))
    assert result.startswith("READY:")
    assert calls[0] == ("systemctl", "daemon-reload")
    assert calls[1:4] == [
        ("systemctl", "show", unit, "--property=LoadState,ActiveState", "--no-pager")
        for unit in UNITS
    ]
    assert calls[4:] == [("systemctl", "reset-failed", UNITS[1])]
    assert not any("start" in cmd or "stop" in cmd for cmd in calls)


def test_unloaded_unit_never_resets_anything():
    calls = []
    def run(argv, **kwargs):
        calls.append(tuple(argv))
        if argv[1] == "show" and argv[2] == UNITS[1]:
            return SimpleNamespace(returncode=0,
                                   stdout="LoadState=not-found\nActiveState=inactive\n")
        return SimpleNamespace(returncode=0,
                               stdout="LoadState=loaded\nActiveState=inactive\n")
    assert prepare_units(run=run).startswith("BLOCKED:")
    assert not any("reset-failed" in cmd for cmd in calls)


def test_active_unit_blocks_without_resetting():
    calls = []
    states = {unit: "inactive" for unit in UNITS}
    states[UNITS[0]] = "active"
    assert prepare_units(run=runner(calls, states=states)).startswith("BLOCKED:")
    assert not any("reset-failed" in cmd for cmd in calls)


def test_reset_failed_with_proven_inactive_unit_does_not_block():
    calls = []
    states = {unit: "inactive" for unit in UNITS}
    states[UNITS[2]] = "failed"
    failed = (("systemctl", "reset-failed", UNITS[2]),)
    def run(argv, **kwargs):
        if argv[1] == "show" and len(calls) > 4:
            states[UNITS[2]] = "inactive"
        return runner(calls, states=states, failures=failed)(argv, **kwargs)
    assert prepare_units(run=run).startswith("READY:")
    assert calls[-1] == ("systemctl", "show", UNITS[2],
                         "--property=LoadState,ActiveState", "--no-pager")


def test_reset_failure_still_failed_blocks():
    calls = []
    states = {unit: "inactive" for unit in UNITS}
    states[UNITS[2]] = "failed"
    failed = (("systemctl", "reset-failed", UNITS[2]),)
    assert prepare_units(run=runner(calls, states=states, failures=failed)).startswith("BLOCKED:")


def test_daemon_reload_failure_blocks_without_followup():
    calls = []
    assert prepare_units(run=runner(calls, failures=(("systemctl", "daemon-reload"),))).startswith("BLOCKED:")
    assert calls == [("systemctl", "daemon-reload")]
