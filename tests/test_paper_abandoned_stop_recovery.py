"""Focused non-VPS regression for the confirmed STOP / no-stage recovery fence."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import paper_abandoned_stop_recovery as recovery

OLD = "a" * 40
TARGET = "b" * 40
IDENTITY = "c" * 64


@pytest.fixture
def case(tmp_path, monkeypatch):
    from tools import paper_maintenance as maintenance
    from tools import vps_release_identity as release

    journal = tmp_path / "transactions"
    journal.mkdir(mode=0o700)
    (journal / ".release.lock").write_bytes(b"")
    (journal / ".release.lock").chmod(0o600)
    (journal / (".stop-invoked-" + TARGET)).write_bytes(
        b"STOP_INVOKED; not install authorization\\n")
    (journal / (".stop-confirmed-" + TARGET)).write_bytes(
        f"CANONICAL_ALL_STOP_CONFIRMED:{OLD}:{TARGET}\n".encode("ascii"))
    monkeypatch.setattr(recovery, "verify_release", lambda root: OLD)
    monkeypatch.setattr(release, "verify_release", lambda root: OLD)
    monkeypatch.setattr(maintenance, "_confirmed_stop_receipt", lambda *a, **kw: True)
    monkeypatch.setattr(maintenance, "_proven_prior_exceptional_completion",
                        lambda *a, **kw: False)
    return journal


def run(journal, *, runner=None, ready=None, host=None):
    calls = []
    def start(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)
    result = recovery.recover_abandoned_stop(
        TARGET, OLD, root=Path("/release"), transactions=journal, uid=os.geteuid(),
        runner=runner or start,
        freeze=lambda *_: IDENTITY,
        host_preflight=host or (lambda *a, **kw: None),
        ready=ready or (lambda *a: True),
    )
    return result, calls


def test_exact_stop_recovery_is_once_and_keeps_original_receipts(case):
    before = {p.name: p.read_bytes() for p in case.glob(".stop-*")}
    status, calls = run(case)
    assert status.startswith("READY:")
    assert calls == [["sudo", "-n", "systemctl", "start",
                      "bybitscanner-paper-backend.service"]]
    assert {p.name: p.read_bytes() for p in case.glob(".stop-*")} == before
    assert recovery.proven_abandoned_stop(
        case, TARGET, root=Path("/release"), uid=os.geteuid())
    ready, calls = run(case)
    assert ready.startswith("READY:")
    assert not calls


def test_no_confirmed_stop_never_starts(case, monkeypatch):
    from tools import paper_maintenance as maintenance
    monkeypatch.setattr(maintenance, "_confirmed_stop_receipt",
                        lambda *a, **kw: False)
    with pytest.raises(recovery.AbandonedStopBlocked, match="canonical_STOP_unproven"):
        run(case)
    assert not list(case.glob(".abandoned-stop-*"))


def test_unknown_result_has_durable_attempt_and_never_retries(case):
    count = []
    def unknown(argv, **kwargs):
        count.append(argv)
        raise OSError("transport lost")
    with pytest.raises(recovery.AbandonedStopBlocked, match="outcome_unknown"):
        run(case, runner=unknown)
    assert len(count) == 1
    assert (case / (".abandoned-stop-attempt-" + TARGET)).is_file()
    assert not (case / (".abandoned-stop-restored-" + TARGET)).exists()
    with pytest.raises(recovery.AbandonedStopBlocked, match="prior_recovery_attempt"):
        run(case)
    assert len(count) == 1


def test_missing_host_proof_never_writes_attempt(case):
    with pytest.raises(recovery.AbandonedStopBlocked, match="host_not_safe"):
        run(case, host=lambda *a, **kw: (_ for _ in ()).throw(
            recovery.AbandonedStopBlocked("host_not_safe")))
    assert not list(case.glob(".abandoned-stop-*"))


def test_other_unresolved_stop_remains_global_fence(case):
    other = "d" * 40
    (case / (".stop-invoked-" + other)).write_bytes(b"unresolved")
    with pytest.raises(recovery.AbandonedStopBlocked, match="another_unresolved"):
        run(case)
    assert not list(case.glob(".abandoned-stop-*"))


def test_target_install_journal_forbids_abandonment(case):
    (case / TARGET).mkdir()
    with pytest.raises(recovery.AbandonedStopBlocked, match="target_install_journal_exists"):
        run(case)


def test_existing_attempt_without_ready_receipt_must_not_replay(case):
    attempt, _ = recovery._paths(case, TARGET)
    attempt.write_bytes(recovery._receipt_payload(OLD, TARGET))
    with pytest.raises(recovery.AbandonedStopBlocked, match="prior_recovery_attempt"):
        run(case)
