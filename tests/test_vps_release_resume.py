"""No host side effects: synthetic Gitless release and mocked unit/port state."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

import pytest

from tools.vps_release_resume import (
    ResumeBlocked, check_resume, _systemd_state, _assert_no_listeners, UNIT_DIR,
)
from tools.vps_systemd_unit_prepare import UNITS

SHA = "a" * 40


def fixture(root):
    source = root / "deploy/systemd"
    installed = root / "systemd"
    source.mkdir(parents=True)
    installed.mkdir()
    for unit in UNITS:
        (source / unit).write_text("[Service]\nExecStart=/bin/false\n")
        (installed / unit).write_bytes((source / unit).read_bytes())
    return installed


def check(root, installed, *, target=SHA, sha=SHA, states=None, listeners=None):
    return check_resume(target, root=root, manifest=root / "manifest.json",
        unit_dir=installed,
        verify=lambda *args: sha,
        states=states or (lambda unit: {"ActiveState": "inactive", "MainPID": "0"}),
        listeners=listeners or (lambda: None))


def test_installed_exact_release_stopped_and_units_resume_without_mutation():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        calls = []
        result = check(root, installed,
            states=lambda unit: calls.append(("show", unit)),
            listeners=lambda: calls.append(("tcp",)))
        assert result.startswith("RESUME_READY:")
        assert calls == [("show", unit) for unit in UNITS] + [("tcp",)]


def test_target_mismatch_never_touches_service_or_listener():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        with pytest.raises(ResumeBlocked, match="installed_release_differs"):
            check(root, installed, sha="b" * 40,
                  states=lambda _: pytest.fail("no systemd read expected"))


def test_unit_mismatch_fails_before_systemd_probe():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        (installed / UNITS[0]).write_text("unsafe")
        with pytest.raises(ResumeBlocked, match="installed_unit_does_not_match"):
            check(root, installed, states=lambda _: pytest.fail("no systemd read"))


def test_unit_symlink_rejected():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        (installed / UNITS[0]).unlink()
        (installed / UNITS[0]).symlink_to(root / "deploy/systemd" / UNITS[0])
        with pytest.raises(ResumeBlocked, match="installed_unit_does_not_match"):
            check(root, installed)


def test_unverified_release_never_touches_units():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        from tools.vps_release_identity import ReleaseIdentityBlocked
        with pytest.raises(ResumeBlocked, match="installed_release_unproven"):
            check_resume(SHA, root=root, manifest=root / "missing",
                unit_dir=installed, verify=lambda *args: (_ for _ in ()).throw(
                    ReleaseIdentityBlocked("no protected manifest")))


def test_listener_blocks_even_with_exact_release_and_stopped_units():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        with pytest.raises(ResumeBlocked, match="PAPER_port_owned"):
            check(root, installed, listeners=lambda: (_ for _ in ()).throw(
                ResumeBlocked("PAPER_port_owned_by_another_process")))


def test_systemd_failed_or_inactive_unit_is_eligible_for_prepare():
    for mode in ("inactive", "failed"):
        output = f"LoadState=loaded\nActiveState={mode}\nMainPID=0\nFragmentPath={UNIT_DIR / UNITS[0]}\nDropInPaths=\n"
        run = lambda *args, **kw: SimpleNamespace(returncode=0, stdout=output)
        assert _systemd_state(UNITS[0], run=run)["ActiveState"] == mode


def test_systemd_active_and_wrong_origin_and_dropins_are_blocked():
    safe = dict(LoadState="loaded", ActiveState="inactive", MainPID="0",
                FragmentPath=str(UNIT_DIR / UNITS[0]), DropInPaths="")
    for changed, value in [
        ("ActiveState", "active"), ("MainPID", "12345"),
        ("FragmentPath", "/tmp/other.service"),
        ("DropInPaths", "/etc/systemd/system/override.conf"),
    ]:
        values = {**safe, changed: value}
        run = lambda *args, **kw: SimpleNamespace(
            returncode=0, stdout="".join(f"{k}={v}\n" for k, v in values.items()))
        with pytest.raises(ResumeBlocked):
            _systemd_state(UNITS[0], run=run)


def test_tcp_listener_check_rejects_backend_or_telegram_and_ipv6():
    with mock.patch("tools.vps_release_resume.Path.read_text",
                    side_effect=[" h\n 0: 0100007F:223D 00000000:0000 0A x\n", " h\n"]):
        with pytest.raises(ResumeBlocked, match="PAPER_port_owned"):
            _assert_no_listeners()
    with mock.patch("tools.vps_release_resume.Path.read_text",
                    side_effect=[" h\n", " h\n 0: 00000000000000000000000000000000:223E 0000:0000 0A x\n"]):
        with pytest.raises(ResumeBlocked, match="PAPER_port_owned"):
            _assert_no_listeners()


def test_no_automatic_stop_start_sql_or_network_calls():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        installed = fixture(root)
        with mock.patch("tools.vps_release_resume.subprocess.run") as run:
            with mock.patch("tools.vps_release_resume._assert_no_listeners"):
                assert check(root, installed).startswith("RESUME_READY:")
            run.assert_not_called()
