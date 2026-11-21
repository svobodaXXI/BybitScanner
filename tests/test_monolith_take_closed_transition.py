"""Protected TAKE-closed monolith transition, on scratch PAPER only.

No real process signal: pid/token/listener and single exit are simulated.
"""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile

import pytest

from tests.test_robot_protected_postfill_recovery import _take_closed_orphan
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.flat_paper_recovery_transition import ROOT, execute_flat_handoff
from tools.paper_take_closed_handoff_proof import PROOF_LABEL
from tools.runtime_intent import expected_database_identity


SHA = "ebd19436135688de650058ba9b342b1c48ea7f56"
PID = 499992


def _take_transition(*, execute, taint=None, listener=True, exit_after=True):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        runtime.close()
        identity = expected_database_identity(ROOT, {"BYBITSCANNER_PAPER_DB": str(path)})
        snapshots = {
            "backend": {
                "ok": True, "component": "paper_backend", "mode": "paper",
                "paper_live_safe": True, "database_identity": identity,
                "build_sha": SHA, "process_instance_id": "pinned-stable-owner",
            },
            "scanner": {"mode": "SCANNER_STOPPED", "worker_quiescent": True},
            "autopilot": {"mode": "OFF"},
            "protection": {
                "healthy": True, "unhealthy_symbols": {}, "covered_symbols": [],
                "armed_symbols": [], "coverage_roles": {},
                "ingress": {"current_pending": 0},
            },
        }
        if taint is not None:
            taint(path, snapshots)
        events = []
        live = [True]
        @contextmanager
        def barrier(db_path):
            assert db_path == path
            with sqlite3.connect(path) as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("PRAGMA query_only=ON")
                events.append("read-only-writer-barrier")
                try:
                    yield conn
                finally:
                    conn.rollback()
                    events.append("released")

        def signal_once(pid, signum):
            assert pid == PID
            events.append("single-signal")
            if exit_after:
                live[0] = False

        result = execute_flat_handoff(
            db_path=path, expected_identity=identity,
            expected_pid=PID, expected_build_sha=SHA,
            execute=execute, snapshots=snapshots,
            take_closed_approved=True,
            service_pid=lambda: PID,
            start_token=lambda _pid: "pinned-start-identity",
            listener_owner=lambda _pid: listener,
            writer_guard=barrier,
            send_interrupt=signal_once, is_alive=lambda _pid: live[0],
            monotonic=lambda: 0 if not events or "single-signal" not in events else 100,
            sleep=lambda _secs: None,
        )
        return result, events


def test_take_closed_handoff_preflight_never_signals():
    result, events = _take_transition(execute=False)
    assert result == "PRECHECK_ONLY: FLAT proven under writer barrier; no process action"
    assert events == ["read-only-writer-barrier", "released"]


def test_take_closed_handoff_requires_original_listener_and_one_signal():
    result, events = _take_transition(execute=True)
    assert result == "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed"
    assert events == ["read-only-writer-barrier", "single-signal", "released"]


def test_take_closed_handoff_rejects_foreign_listener_without_signal():
    with pytest.raises(FlatRecoveryBlocked, match="backend_listener_owner_unproven"):
        _take_transition(execute=True, listener=False)


def test_take_closed_handoff_rejects_changed_record_without_signal():
    def taint(path, _snapshots):
        with sqlite3.connect(path) as conn:
            conn.execute("UPDATE position_projections SET quantity='1' WHERE trading_account_id='paper'")
    with pytest.raises(FlatRecoveryBlocked, match="take_closed_account_not_flat"):
        _take_transition(execute=True, taint=taint)


def test_take_closed_handoff_is_mutually_exclusive():
    with pytest.raises(FlatRecoveryBlocked, match="mutually_exclusive_flat_incident_proofs"):
        execute_flat_handoff(
            db_path=Path("/never-touch"), expected_identity="nope",
            expected_pid=PID, expected_build_sha=SHA, execute=False,
            take_closed_approved=True, proven_one_flat_orphan=True,
        )


def test_pre_stop_proof_failure_keeps_one_shot_journal_empty(tmp_path, monkeypatch):
    import os
    import tools.stop_robot_runtime as stop_runtime
    import tools.vps_release_identity as release
    from tools.paper_maintenance import deploy_staged_editor_only

    root, stage, journal = (tmp_path / "installed", tmp_path / "stage",
                            tmp_path / "journal")
    root.mkdir()
    stage.mkdir()
    old = "b" * 40
    target = "a" * 40
    monkeypatch.setattr(release, "verify_release", lambda *_a, **_k: old)
    requested = []
    def builder(env, sha, *, execute=True):
        assert sha == old
        requested.append(execute)
        if not execute:
            return lambda: (_ for _ in ()).throw(
                FlatRecoveryBlocked("source_lineage_unproven"))
        return lambda: pytest.fail("no irreversible transition without preproof")
    monkeypatch.setattr(stop_runtime, "build_take_closed_approved_handoff", builder)
    result = deploy_staged_editor_only(
        target, stage=stage, root=root, transactions=journal,
        take_closed_approved_handoff=True,
        preflight=lambda *_a, **_k: None,
        installer=lambda *_a, **_k: pytest.fail("never install"),
        resume=lambda *_a, **_k: pytest.fail("never resume"),
        trusted_uid=os.geteuid(),
    )
    assert result.startswith("BLOCKED: take_closed_pre_STOP_proof:")
    assert requested == [False]
    assert not (journal / (".stop-invoked-" + target)).exists()


def test_pre_stop_proof_dispatches_only_one_existing_stop_controller(
    tmp_path, monkeypatch,
):
    import os
    import tools.stop_robot_runtime as stop_runtime
    import tools.vps_release_identity as release
    import tools.paper_maintenance as maintenance

    root, stage, journal = (tmp_path / "installed", tmp_path / "stage",
                            tmp_path / "journal")
    root.mkdir()
    stage.mkdir()
    old, target = "b" * 40, "a" * 40
    monkeypatch.setattr(release, "verify_release", lambda *_a, **_k: old)
    events = []
    def builder(env, sha, *, execute=True):
        assert sha == old
        events.append("build-live" if execute else "build-preproof")
        return (lambda: "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed"
                if execute else
                "PRECHECK_ONLY: FLAT proven under writer barrier; no process action")
    class StubShutdown:
        def __init__(self, **kwargs):
            assert kwargs["take_closed_approved_handoff"] is not None
            assert kwargs["dual_orphan_handoff"] is None
            assert kwargs["proven_one_flat_orphan_handoff"] is None
            events.append("canonical-owner")
        def run(self, scope):
            assert scope == "all"
            events.append("protected-stop")
            from tools.stop_robot_runtime import ShutdownResult
            return ShutdownResult("all", True, "simulated", runtime_stopped=True)

    monkeypatch.setattr(stop_runtime, "build_take_closed_approved_handoff", builder)
    monkeypatch.setattr(maintenance, "RuntimeShutdown", StubShutdown)
    result = maintenance.deploy_staged_editor_only(
        target, root=root, stage=stage, transactions=journal,
        take_closed_approved_handoff=True,
        preflight=lambda *_a, **_k: events.append("source-preflight"),
        installer=lambda *_a, **_k: (events.append("install"), "INSTALLED_STOPPED: exact")[1],
        resume=lambda *_a, **_k: (events.append("resume"), "READY: EDITOR_ONLY")[1],
        trusted_uid=os.geteuid(),
    )
    assert result == "READY: EDITOR_ONLY"
    assert events == [
        "source-preflight", "build-preproof", "build-live",
        "canonical-owner", "protected-stop", "install", "resume",
    ]


def test_cli_take_closed_requires_explicit_verified_stage(monkeypatch, capsys):
    from tools import paper_maintenance as maint
    with pytest.raises(SystemExit):
        maint.main(["a" * 40, "--take-closed-approved-handoff"])
    assert "TAKE-closed handoff requires exact staged Gitless operation" in capsys.readouterr().err

    calls = []
    monkeypatch.setattr(
        maint, "deploy_staged_editor_only",
        lambda *args, **kwargs: (calls.append(kwargs),
                                 "BLOCKED: TEST_ONLY_NO_RUNTIME_ACTION")[1],
    )
    assert maint.main([
        "a" * 40, "--staged-gitless-editor-only",
        "/var/lib/bybitscanner-stage-git-" + "a" * 40,
        "--take-closed-approved-handoff",
    ]) == 2
    assert calls[0]["take_closed_approved_handoff"] is True


def test_existing_stop_owner_routes_required_to_take_handoff_not_legacy_reconcile(tmp_path, monkeypatch):
    from tools.stop_robot_runtime import RuntimeShutdown, ShutdownResult
    events = []
    def protected_callback():
        events.append("proof-and-signal-once")
        return "INTERRUPT_EXIT_OBSERVED: backend exit; restart not performed"

    owner = RuntimeShutdown(
        root=tmp_path, env={"BYBITSCANNER_PAPER_DB": str(tmp_path / "scratch.sqlite3")},
        robot_state=lambda: ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        take_closed_approved_handoff=protected_callback,
        legacy_supported=False,
    )
    monkeypatch.setattr(owner, "_probe_backend", lambda: "present")
    monkeypatch.setattr(owner, "_probe_telegram", lambda: "absent")
    monkeypatch.setattr(owner, "_freeze_autopilot", lambda: False)
    monkeypatch.setattr(owner, "_stop_scanner", lambda: False)
    monkeypatch.setattr(owner, "_require_autopilot_off", lambda: None)
    monkeypatch.setattr(owner, "_require_scanner_stopped", lambda: None)
    monkeypatch.setattr(
        owner, "_reconcile_robot",
        lambda: pytest.fail("old incompatible reconcile must not run"),
    )
    result = owner.run("all")
    assert isinstance(result, ShutdownResult)
    assert result.ok and result.runtime_stopped
    assert result.steps == ("backend:take-closed-approved-handoff",)
    assert events == ["proof-and-signal-once"]


def test_take_closed_handoff_rejects_unknown_callback_outcome(tmp_path, monkeypatch):
    from tools.stop_robot_runtime import RuntimeShutdown
    owner = RuntimeShutdown(
        root=tmp_path, env={"BYBITSCANNER_PAPER_DB": str(tmp_path / "scratch.sqlite3")},
        robot_state=lambda: ("ROBOT_RUNNING", "RECONCILIATION_REQUIRED"),
        take_closed_approved_handoff=lambda: "OUTCOME_UNKNOWN: no replay",
        legacy_supported=False,
    )
    monkeypatch.setattr(owner, "_probe_backend", lambda: "present")
    monkeypatch.setattr(owner, "_probe_telegram", lambda: "absent")
    monkeypatch.setattr(owner, "_freeze_autopilot", lambda: False)
    monkeypatch.setattr(owner, "_stop_scanner", lambda: False)
    monkeypatch.setattr(owner, "_require_autopilot_off", lambda: None)
    monkeypatch.setattr(owner, "_require_scanner_stopped", lambda: None)
    result = owner.run("all")
    assert not result.ok and not result.runtime_stopped
    assert "do not retry or deploy" in result.message


def test_cli_take_closed_cannot_bundle_paper_auto_start(monkeypatch, capsys):
    from tools import paper_maintenance as maint
    with pytest.raises(SystemExit):
        maint.main([
            "a" * 40,
            "--staged-gitless-editor-only",
            "/var/lib/bybitscanner-stage-git-" + "a" * 40,
            "--take-closed-approved-handoff",
            "--start-paper-after-editor",
        ])
    assert "no PAPER START" in capsys.readouterr().err


def test_owner_update_take_closed_enters_existing_global_lock(monkeypatch, capsys):
    import contextlib
    from tools import paper_maintenance as maint

    events = []
    @contextlib.contextmanager
    def locked():
        events.append("global-owner-lock")
        yield
        events.append("owner-lock-released")

    monkeypatch.setattr(maint, "_owner_action_lifecycle_guard", locked)
    monkeypatch.setattr(maint, "_verified_staged_module_bootstrap", lambda *a, **kw: True)
    monkeypatch.setattr(
        maint, "deploy_staged_editor_only",
        lambda *args, **kwargs: (
            events.append(("dispatch", kwargs["take_closed_approved_handoff"],
                           kwargs["stage"])),
            "BLOCKED: TEST_ONLY_NO_RUNTIME_ACTION",
        )[1],
    )
    sha = "a" * 40
    assert maint.main([sha, "--action", "update-take-closed"]) == 2
    assert events == [
        "global-owner-lock",
        ("dispatch", True, Path("/var/lib/bybitscanner-stage-git-" + sha)),
        "owner-lock-released",
    ]
    assert capsys.readouterr().out == "BLOCKED: TEST_ONLY_NO_RUNTIME_ACTION\\n"
