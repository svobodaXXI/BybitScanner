"""One authorized monolith START for a proven legacy PAPER TAKE closure.

All fills and Robot state originate from a scratch PAPER owner. No VPS or
production SQLite, external Telegram, STOP or Market dispatcher is touched.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.test_robot_protected_postfill_recovery import (
    ACCOUNT, CID, SYMBOL, _take_closed_orphan,
)
from tools import paper_maintenance as maintenance
from tools import runtime_intent
from tools import vps_release_identity


TARGET = "a" * 40
IDENTITY = "synthetic-paper-identity"
REASON = "reconcile_robot could not prove pending Robot entry safety: " + CID


@pytest.fixture
def take_closed_owner(monkeypatch, tmp_path):
    db = tmp_path / "paper.sqlite3"
    runtime = _take_closed_orphan(db)
    phase = ["RECONCILIATION_REQUIRED"]
    observed = []
    protection = {
        "ok": True, "healthy": True, "unhealthy_symbols": {},
        "covered_symbols": [], "armed_symbols": [], "coverage_roles": {},
        "ingress": {"current_pending": 0},
    }
    env = {"BYBITSCANNER_PAPER_DB": str(db)}
    monkeypatch.setattr(maintenance, "_environment", lambda *_: env)
    monkeypatch.setattr(vps_release_identity, "verify_release", lambda *_: TARGET)
    monkeypatch.setattr(runtime_intent, "expected_database_identity",
                        lambda *_: IDENTITY)
    monkeypatch.setattr(maintenance, "_editor_runtime_ready",
                        lambda *_: True)

    def get(url, _timeout):
        if url.endswith("/api/health"):
            body = {
                "ok": True, "component": "paper_backend", "mode": "paper",
                "build_sha": TARGET, "database_identity": IDENTITY,
                "paper_live_safe": True, "robot_admission_ready": False,
                "process_instance_id": "scratch-backend",
            }
        elif url.endswith("/api/scanner/status"):
            body = {"ok": True, "mode": "SCANNER_STOPPED", "worker_quiescent": True}
        elif url.endswith("/api/robot/autopilot"):
            body = {"ok": True, "trading_account_id": {"value": "paper"}, "mode": "OFF"}
        elif url.endswith("/api/robot/protection-health"):
            body = protection
        elif url.endswith("/api/robot/state"):
            body = {
                "ok": True, "mode": "ROBOT_RUNNING",
                "recovery_status": phase[0],
                "reason": REASON if phase[0] == "RECONCILIATION_REQUIRED" else None,
            }
        else:
            pytest.fail("Unexpected read-only endpoint: " + url)
        return SimpleNamespace(status=200, json=lambda: dict(body))

    def start(target, *, root, env_file, editor_status):
        assert target == TARGET and root == tmp_path
        assert editor_status.startswith("READY:")
        assert maintenance._paper_start_quiescent(root, env_file)
        observed.append("start")
        return "READY: proven scratch PAPER start"

    monkeypatch.setattr(runtime_intent, "http_get", get)
    monkeypatch.setattr(maintenance, "start_installed_paper_from_editor", start)
    case = SimpleNamespace(
        runtime=runtime, db=db, phase=phase, observed=observed,
        protection=protection,
    )
    try:
        yield case
    finally:
        runtime.close()


def test_owner_start_take_closed_reconciles_actual_fills_without_replay(
    monkeypatch, take_closed_owner, tmp_path,
):
    case = take_closed_owner
    before_fills = case.runtime.store.load_executions_for_symbol(ACCOUNT, SYMBOL)
    before_commands = case.runtime.store.load_commands_for_symbol_since(
        ACCOUNT, SYMBOL, 0,
    )
    assert len(before_fills) == 2 and len(before_commands) == 1

    def receipt(*_args, **_kwargs):
        case.observed.append("sealed")
        return True

    def post(url, payload, timeout):
        assert url.endswith("/api/robot/reconcile")
        assert payload == {} and timeout == 180
        assert case.observed == ["sealed"]
        case.observed.append("reconcile")
        recovered = case.runtime.robot_reconcile()
        case.phase[0] = recovered.recovery_status
        return SimpleNamespace(
            status=200,
            json=lambda: {
                "ok": True, "success": recovered.success,
                "recovery_status": recovered.recovery_status,
            },
        )

    monkeypatch.setattr(maintenance, "_record_required_reconcile_once", receipt)
    monkeypatch.setattr(runtime_intent, "http_post_json", post)

    assert maintenance._recover_active_take_closed(
        TARGET, root=tmp_path, env_file=None,
    ) == "READY: proven scratch PAPER start"
    assert case.observed == ["sealed", "reconcile", "start"]

    store = case.runtime.store
    assert store.load_executions_for_symbol(ACCOUNT, SYMBOL) == before_fills
    assert store.load_commands_for_symbol_since(ACCOUNT, SYMBOL, 0) == before_commands
    candidate = store.get_robot_candidate(CID)
    trade = store.get_robot_trade("robot-trade-" + CID)
    assert candidate.status == "CLOSED"
    assert "emergency_close_pending" not in candidate.robot_state["execution"]
    assert trade.exit_reason == "TAKE"
    assert trade.fees_costs_usdt == before_fills[0].fee + before_fills[1].fee


def test_owner_start_take_closed_refuses_unhealthy_protection_before_sealing(
    monkeypatch, take_closed_owner, tmp_path,
):
    case = take_closed_owner
    case.protection["armed_symbols"] = ["BTCUSDT"]
    monkeypatch.setattr(
        maintenance, "_record_required_reconcile_once",
        lambda *_a, **_k: pytest.fail("No owner intent without full account proof"),
    )
    monkeypatch.setattr(
        runtime_intent, "http_post_json",
        lambda *_a, **_k: pytest.fail("No reconcile on ambiguous protection"),
    )
    assert maintenance._recover_active_take_closed(
        TARGET, root=tmp_path, env_file=None,
    ).startswith("BLOCKED:")
    assert case.observed == []
    assert case.runtime.store.get_robot_candidate(CID).status == "APPROVED"


def test_owner_start_take_closed_timeout_cannot_replay_reconcile(
    monkeypatch, take_closed_owner, tmp_path,
):
    case = take_closed_owner
    invoked = []

    def receipt(*_args, **_kwargs):
        invoked.append("receipt")
        return len(invoked) == 1

    def timeout(url, payload, _timeout):
        invoked.append("POST")
        raise TimeoutError("unknown outcome")

    monkeypatch.setattr(maintenance, "_record_required_reconcile_once", receipt)
    monkeypatch.setattr(runtime_intent, "http_post_json", timeout)
    first = maintenance._recover_active_take_closed(
        TARGET, root=tmp_path, env_file=None,
    )
    assert first == "BLOCKED: take_closed_reconcile_outcome_unknown; no_replay"
    second = maintenance._recover_active_take_closed(
        TARGET, root=tmp_path, env_file=None,
    )
    assert second == "BLOCKED: take_closed_prior_reconcile_intent; no_replay"
    assert invoked == ["receipt", "POST", "receipt"]
    assert case.observed == []
    assert case.runtime.store.get_robot_trade("robot-trade-" + CID) is None
