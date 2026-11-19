"""Focused safety contracts for the pinned, one-shot FUSDT STOP reconciliation."""
import os
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import vps_box_stop_reconcile as reconcile


def _reply(body, status=200):
    return SimpleNamespace(status=status, json=lambda: body)


@pytest.fixture
def proven_fusdt(monkeypatch, tmp_path):
    from terminal.persistence import sqlite_store
    from terminal.statistics import reader
    from tools import paper_maintenance, runtime_intent, stop_robot_runtime, vps_release_identity

    db = tmp_path / "paper.sqlite3"
    sqlite3.connect(db).close()
    incident = {"candidate_status": "CLOSED", "active": (), "exit_reason": "STOP",
                "runtime": "RECONCILIATION_REQUIRED", "reason": reconcile.REASON}
    monkeypatch.setattr(vps_release_identity, "verify_release", lambda _root: reconcile.OLD_SHA)
    monkeypatch.setattr(stop_robot_runtime, "_environment", lambda _path: {})
    monkeypatch.setattr(stop_robot_runtime, "_database_path", lambda _root, _env: db)
    monkeypatch.setattr(runtime_intent, "expected_database_identity", lambda _root, _env: "dbid")
    monkeypatch.setattr(
        paper_maintenance, "_active_required_flat_proof",
        lambda _db: ("ROBOT_RUNNING", incident["runtime"],
                     incident["reason"] if incident["runtime"] == "RECONCILIATION_REQUIRED" else None),
    )

    class Store:
        def __init__(self, *_args): pass

        def get_robot_candidate(self, candidate_id):
            assert candidate_id == reconcile.CANDIDATE
            return SimpleNamespace(status=incident["candidate_status"],
                                   symbol=SimpleNamespace(value="FUSDT"))

        def load_active_robot_candidate_states(self, account):
            assert account.value == "paper"
            return incident["active"]

    class Statistics:
        def __init__(self, _db): pass

        def load_completed_trades(self, *, trading_account_id):
            assert trading_account_id == "paper"
            return (SimpleNamespace(candidate_id=reconcile.CANDIDATE, symbol="FUSDT",
                                    exit_reason=incident["exit_reason"],
                                    exit_time_ms=reconcile.STOP_EXIT_MS),)

    monkeypatch.setattr(sqlite_store, "SQLiteStore", Store)
    monkeypatch.setattr(reader, "RobotStatisticsReader", Statistics)
    def api(url, _timeout):
        if url.endswith("/api/health"):
            body = dict(ok=True, component="paper_backend", mode="paper",
                        paper_live_safe=True, build_sha=reconcile.OLD_SHA,
                        database_identity="dbid", process_instance_id="original")
        elif url.endswith("/api/scanner/status"):
            body = dict(ok=True, mode="SCANNER_STOPPED")
        elif url.endswith("/api/robot/autopilot"):
            body = dict(ok=True, mode="OFF", trading_account_id={"value": "paper"})
        elif url.endswith("/api/robot/state"):
            body = dict(mode="ROBOT_RUNNING", recovery_status=incident["runtime"],
                        reason=incident["reason"])
        elif url.endswith("/api/robot/protection-health"):
            body = dict(ok=True, healthy=True, covered_symbols=[], armed_symbols=[],
                        coverage_roles={}, unhealthy_symbols={})
        elif url.endswith("/health"):
            body = dict(component="telegram_monitoring", status="ready",
                        database_identity="dbid")
        else:
            raise AssertionError("unexpected API path " + url)
        return _reply(body)

    monkeypatch.setattr(runtime_intent, "http_get", api)
    return db, incident


def test_preflight_proves_exact_stop_and_frozen_runtime(proven_fusdt, tmp_path):
    db, incident = proven_fusdt
    assert reconcile._attest(reconcile.OLD_SHA, tmp_path, None) == "original"
    incident["runtime"] = "PAUSED"
    assert reconcile._attest(reconcile.OLD_SHA, tmp_path, None, after=True) == "original"


@pytest.mark.parametrize("bad", ["open", "entry", "stop", "owner", "wrong-reason"])
def test_preflight_rejects_unproven_or_nonterminal_incident(proven_fusdt, tmp_path, bad):
    _, incident = proven_fusdt
    if bad == "open":
        incident["candidate_status"] = "OPEN"
    elif bad == "entry":
        incident["active"] = (object(),)
    elif bad == "stop":
        incident["exit_reason"] = "TAKE"
    elif bad == "owner":
        incident["runtime"] = "READY"
    elif bad == "wrong-reason":
        incident["reason"] = "OTHER_REQUIRED"
    assert reconcile._attest(reconcile.OLD_SHA, tmp_path, None) is None


@pytest.fixture
def one_shot(monkeypatch, tmp_path):
    from tools import paper_maintenance, runtime_intent, vps_gitless_release_activate
    root = tmp_path / "installed"
    journal = tmp_path / "journal"
    root.mkdir()
    journal.mkdir(mode=0o700)
    statuses = []
    calls = []
    monkeypatch.setattr(paper_maintenance, "_known_drain_receipt",
                        lambda _journal, _target, _old, *, phase, uid:
                        phase == "deferred")
    monkeypatch.setattr(vps_gitless_release_activate, "_sync_directory", lambda _root: None)
    monkeypatch.setattr(
        reconcile, "_attest",
        lambda _sha, _root, _env, *, after=False:
        ("instance" if not statuses or statuses[-1] != "block" else None),
    )
    monkeypatch.setattr(
        runtime_intent, "http_post_json",
        lambda url, payload, timeout: (
            calls.append((url, payload, timeout))
            or _reply(dict(ok=True, success=True, mode="ROBOT_RUNNING",
                           recovery_status="PAUSED"))
        ),
    )
    return root, journal, statuses, calls


def _run(root, journal):
    return reconcile.reconcile_once(
        reconcile.OLD_SHA, root=root, env_file=None,
        journal_root=journal, trusted_uid=os.geteuid(),
    )


def test_one_shot_calls_only_canonical_reconcile_and_is_not_replayed(one_shot):
    root, journal, _statuses, calls = one_shot
    status = _run(root, journal)
    assert status.startswith("READY: FUSDT STOP reconciled to PAUSED")
    assert calls == [("http://127.0.0.1:8765/api/robot/reconcile", {}, 180)]
    assert _run(root, journal).startswith("BLOCKED: reconcile_once_already_invoked")
    assert len(calls) == 1


def test_missing_deferred_receipt_never_posts_or_creates_marker(one_shot, monkeypatch):
    from tools import paper_maintenance
    root, journal, _, calls = one_shot
    monkeypatch.setattr(paper_maintenance, "_known_drain_receipt", lambda *_a, **_kw: False)
    assert _run(root, journal).startswith("BLOCKED: reconcile_known_drain_receipt")
    assert not calls
    assert not list(journal.glob(".owner-fusdt-box-stop-reconcile-*"))


def test_failed_post_consumes_one_shot_without_retry(one_shot, monkeypatch):
    from tools import runtime_intent
    root, journal, _, calls = one_shot
    def unavailable(*_args):
        calls.append("attempt")
        raise TimeoutError("lost reply")
    monkeypatch.setattr(runtime_intent, "http_post_json", unavailable)
    assert "no_replay" in _run(root, journal)
    assert _run(root, journal).startswith("BLOCKED: reconcile_once_already_invoked")
    assert calls == ["attempt"]


def test_unproven_preflight_never_posts_or_creates_marker(one_shot, monkeypatch):
    root, journal, _, calls = one_shot
    monkeypatch.setattr(reconcile, "_attest", lambda *_args, **_kwargs: None)
    assert _run(root, journal).startswith("BLOCKED: reconcile_runtime_or_STOP")
    assert not calls
    assert not list(journal.glob(".owner-fusdt-box-stop-reconcile-*"))


def test_reconcile_action_routes_through_existing_locked_monolith(monkeypatch, capsys):
    from tools import paper_maintenance
    monkeypatch.setattr(paper_maintenance, "_owner_action_lifecycle_guard", nullcontext)
    monkeypatch.setattr(reconcile, "reconcile_once",
                        lambda sha, **kw: ("READY: pinned reconciliation" if sha == reconcile.OLD_SHA
                                          else "BLOCKED: wrong release"))
    assert paper_maintenance.main([reconcile.OLD_SHA, "--action", "reconcile"]) == 0
    assert "READY: pinned reconciliation" in capsys.readouterr().out
    assert paper_maintenance.main(["a" * 40, "--action", "reconcile"]) == 2
