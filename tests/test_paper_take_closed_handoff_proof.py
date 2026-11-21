"""Synthetic read-only proof for the old-runtime -> new-runtime TAKE-closed handoff.

The scratch PAPER runtime generates a real internal TAKE before inspection.
No call here sends an order to a VPS or changes a production database.
"""
import sqlite3
import tempfile
from pathlib import Path
from copy import deepcopy

import pytest
from terminal.domain.models import TradingAccountId, Symbol

from tests.test_robot_protected_postfill_recovery import _take_closed_orphan
from tools.flat_paper_recovery_gate import FlatRecoveryBlocked
from tools.paper_take_closed_handoff_proof import PROOF_LABEL, prove_take_closed_approved


SHA = "ebd19436135688de650058ba9b342b1c48ea7f56"
IDENTITY = "synthetic-paper-identity"


def snapshots():
    return dict(
        expected_identity=IDENTITY,
        expected_build_sha=SHA,
        backend={
            "ok": True, "component": "paper_backend", "mode": "paper",
            "paper_live_safe": True, "database_identity": IDENTITY,
            "build_sha": SHA, "process_instance_id": "synthetic-owned-backend",
        },
        scanner={"mode": "SCANNER_STOPPED", "worker_quiescent": True},
        autopilot={"mode": "OFF"},
        protection={
            "healthy": True, "unhealthy_symbols": {},
            "covered_symbols": [], "armed_symbols": [],
            "coverage_roles": {}, "ingress": {"current_pending": 0},
        },
    )


def prove(path, data=None):
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        return prove_take_closed_approved(conn, **(data or snapshots()))


def test_real_scratch_paper_take_proves_flat_without_mutation():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        try:
            before = runtime.store.get_robot_candidate("legacy-protected-low-rr")
            assert prove(path) == PROOF_LABEL
            assert prove(path) == PROOF_LABEL  # proof is read-only and repeatable
            after = runtime.store.get_robot_candidate("legacy-protected-low-rr")
            assert before == after and after.status == "APPROVED"
            assert runtime.store.get_robot_trade("robot-trade-legacy-protected-low-rr") is None
        finally:
            runtime.close()


@pytest.mark.parametrize("change", [
    lambda p: p["backend"].update(paper_live_safe=False),
    lambda p: p["backend"].update(build_sha="0" * 40),
    lambda p: p["backend"].update(database_identity="foreign"),
    lambda p: p["scanner"].update(mode="SCANNER_RUNNING"),
    lambda p: p["autopilot"].update(mode="PAPER_AUTO"),
    lambda p: p["protection"].update(armed_symbols=["BTCUSDT"]),
    lambda p: p["protection"].update(coverage_roles={"BTCUSDT": "EXPOSURE"}),
    lambda p: p["protection"]["ingress"].update(current_pending=1),
])
def test_snapshot_drift_or_active_protection_blocks(change):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        try:
            payload = deepcopy(snapshots())
            change(payload)
            with pytest.raises(FlatRecoveryBlocked):
                prove(path, payload)
        finally:
            runtime.close()


@pytest.mark.parametrize("sql,params", [
    ("UPDATE position_projections SET quantity='1' WHERE trading_account_id='paper'", ()),
    ("UPDATE robot_candidates SET status='OPEN' WHERE trading_account_id='paper'", ()),
    ("UPDATE executions SET fee='-1' WHERE exec_id LIKE 'paper-take-exec-%'", ()),
    ("UPDATE executions SET quantity='17' WHERE exec_id LIKE 'paper-take-exec-%'", ()),
    ("UPDATE executions SET order_id='unrelated' WHERE exec_id LIKE 'paper-take-exec-%'", ()),
    ("UPDATE executions SET exchange_timestamp_ms=0 WHERE exec_id LIKE 'paper-take-exec-%'", ()),
])
def test_scratch_immutable_lineage_drift_blocks(sql, params):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        runtime.close()
        with sqlite3.connect(path) as conn:
            conn.execute(sql, params)
        with pytest.raises(FlatRecoveryBlocked):
            prove(path)


def _append_never_traded_box(runtime, *, candidate_id="box-robot-stbl-proof", symbol="STBLUSDT", expected_proof=True):
    """Only the synthetic scratch fixture is mutated; no VPS/PAPER write."""
    from terminal.domain.models import TradingAccountId, Symbol
    from terminal.persistence.sqlite_store import SQLiteStore
    account = TradingAccountId("paper")
    approved_at = 1795168251149
    record, created = runtime.store.create_robot_candidate(
        candidate_id=candidate_id, trading_account_id=account, symbol=Symbol(symbol),
        status="APPROVED",
        signal_snapshot={"pattern": "Box", "symbol": symbol, "timeframe": "5"},
        approved_at_ms=approved_at, updated_at_ms=approved_at,
    )
    assert created
    runtime.store.save_robot_candidate_state(
        record.candidate_id, status="APPROVED",
        robot_state={"phase": "BOX_ENTRY_READY", "direction": "LONG"},
        expected_revision=record.state_revision, updated_at_ms=approved_at + 1,
    )
    actual = runtime.store.get_robot_candidate(record.candidate_id)
    assert runtime.store.prove_approved_candidate_never_traded(actual) is expected_proof
    return actual


def test_one_take_closed_plus_one_independently_never_traded_box_proves():
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        try:
            other = _append_never_traded_box(runtime)
            before = runtime.store.get_robot_candidate(other.candidate_id)
            assert prove(path) == PROOF_LABEL
            assert prove(path) == PROOF_LABEL
            assert runtime.store.get_robot_candidate(other.candidate_id) == before
            assert runtime.store.get_robot_candidate(
                "legacy-protected-low-rr"
            ).status == "APPROVED"
            # The new owner must reconcile the actual TAKE without opening
            # the unrelated Box or inventing an execution for it.
            original_fills = runtime.store.load_executions_for_symbol(
                TradingAccountId("paper"),
                Symbol("BTCUSDT"),
            )
            result = runtime.robot_reconcile()
            # This scratch fixture does NOT warm STBL's candle cache. The
            # owner may account the immutable TAKE but must leave admission
            # blocked rather than invent geometry evidence for the Box.
            assert result.success is False
            assert "closed candle cache unavailable: STBLUSDT" in result.reason
            assert runtime.robot_admission_ready() is False
            assert runtime.store.get_robot_candidate(
                "legacy-protected-low-rr"
            ).status == "CLOSED"
            assert runtime.store.get_robot_candidate(other.candidate_id) == before
            assert runtime.store.load_executions_for_symbol(
                TradingAccountId("paper"),
                Symbol("BTCUSDT"),
            ) == original_fills
            assert runtime.store.prove_approved_candidate_never_traded(
                runtime.store.get_robot_candidate(other.candidate_id)
            )
        finally:
            runtime.close()


def test_second_approved_box_without_no_execution_proof_blocks(monkeypatch):
    from terminal.persistence.sqlite_store import SQLiteStore
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        try:
            _append_never_traded_box(runtime)
            monkeypatch.setattr(
                SQLiteStore, "prove_approved_candidate_never_traded",
                lambda self, record: False,
            )
            with pytest.raises(
                FlatRecoveryBlocked, match="take_closed_other_box_never_traded_unproven"
            ):
                prove(path)
        finally:
            runtime.close()


@pytest.mark.parametrize("invalidity", [
    "third_approved", "foreign_pattern", "same_symbol",
    "unexpected_phase", "postfill_emergency", "additional_take_owner",
])
def test_second_owner_not_verified_as_inert_blocks(invalidity):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "paper.sqlite3"
        runtime = _take_closed_orphan(path)
        try:
            if invalidity == "foreign_pattern":
                _append_never_traded_box(
                    runtime, candidate_id="wedge-untraded-extra"
                )
            elif invalidity == "same_symbol":
                _append_never_traded_box(runtime, symbol="BTCUSDT", expected_proof=False)
            else:
                record = _append_never_traded_box(runtime)
                if invalidity == "third_approved":
                    _append_never_traded_box(
                        runtime, candidate_id="box-robot-third", symbol="XRPUSDT"
                    )
                elif invalidity in (
                    "unexpected_phase", "postfill_emergency", "additional_take_owner"
                ):
                    state = dict(record.robot_state)
                    if invalidity == "unexpected_phase":
                        state["phase"] = "BOX_ORDER_ACTIVE"
                    elif invalidity == "postfill_emergency":
                        state["execution"] = {"emergency_close_pending": True}
                    else:
                        state["execution"] = {
                            "entry_mode": "LATE_ADMISSION_MARKET",
                            "emergency_close_pending": True,
                        }
                    runtime.store.save_robot_candidate_state(
                        record.candidate_id, status="APPROVED", robot_state=state,
                        expected_revision=record.state_revision,
                        updated_at_ms=record.updated_at_ms + 1,
                    )
            with pytest.raises(FlatRecoveryBlocked):
                prove(path)
        finally:
            runtime.close()
