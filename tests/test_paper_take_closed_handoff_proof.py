"""Synthetic read-only proof for the old-runtime -> new-runtime TAKE-closed handoff.

The scratch PAPER runtime generates a real internal TAKE before inspection.
No call here sends an order to a VPS or changes a production database.
"""
import sqlite3
import tempfile
from pathlib import Path
from copy import deepcopy

import pytest

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
