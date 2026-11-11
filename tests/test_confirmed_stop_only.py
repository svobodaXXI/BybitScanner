"""Focused offline regressions for owner-approved STOP-receipt-only continuation."""
import os
from pathlib import Path
from types import SimpleNamespace

import tools.paper_maintenance as maintenance
import tools.vps_release_identity as identity


def test_confirmed_stop_continuation_does_not_replay_stop(monkeypatch, tmp_path):
    target = "a" * 40
    old = "b" * 40
    root, stage, transactions = (tmp_path / n for n in ("installed", "stage", "transactions"))
    root.mkdir()
    stage.mkdir()
    monkeypatch.setattr(identity, "verify_release", lambda *_args, **_kw: old)
    events = []
    crash = [True]

    def stop(_scope):
        events.append("STOP")
        return SimpleNamespace(ok=True, runtime_stopped=True)

    def install(*_args, **_kw):
        events.append("INSTALL")
        if crash[0]:
            raise OSError("interrupted after confirmed STOP")
        return "INSTALLED_STOPPED: verified"

    opts = dict(
        root=root, stage=stage, transactions=transactions,
        trusted_uid=os.geteuid(),
        preflight=lambda *_a, **_k: events.append("PREFLIGHT"),
        installer=install,
        resume=lambda *_a, **_k: "READY: EDITOR_ONLY",
    )
    first = maintenance.deploy_staged_editor_only(target, stop=stop, **opts)
    assert first.startswith("BLOCKED: Gitless_switch_unproven:OSError")
    assert events == ["PREFLIGHT", "STOP", "INSTALL"]
    assert maintenance._confirmed_stop_receipt(transactions, target, old, uid=os.geteuid())

    crash[0] = False
    result = maintenance.deploy_staged_editor_only(
        target, confirmed_stop_only=True, **opts
    )
    assert result == "READY: EDITOR_ONLY"
    assert events == ["PREFLIGHT", "STOP", "INSTALL", "PREFLIGHT", "INSTALL"]


def test_confirmed_stop_only_never_initiates_new_stop(monkeypatch, tmp_path):
    target = "a" * 40
    root, stage, transactions = (tmp_path / n for n in ("installed", "stage", "transactions"))
    root.mkdir()
    stage.mkdir()
    transactions.mkdir(mode=0o700)
    monkeypatch.setattr(identity, "verify_release", lambda *_args, **_kw: "b" * 40)
    events = []
    result = maintenance.deploy_staged_editor_only(
        target, root=root, stage=stage, transactions=transactions,
        trusted_uid=os.geteuid(), confirmed_stop_only=True,
        preflight=lambda *_a, **_k: events.append("PREFLIGHT"),
        installer=lambda *_a, **_k: events.append("INSTALL"),
    )
    assert result.startswith("BLOCKED:")
    assert "confirmed_stop_only" in result
    assert events == []


def test_confirmed_stop_only_refuses_stop_callback_and_orphan_handoff(tmp_path):
    root, stage = tmp_path / "installed", tmp_path / "stage"
    root.mkdir()
    stage.mkdir()
    result = maintenance.deploy_staged_editor_only(
        "a" * 40, root=root, stage=stage,
        confirmed_stop_only=True, stop=lambda *_: None,
    )
    assert result == "BLOCKED: confirmed_stop_only_conflicting_STOP_or_handoff"
