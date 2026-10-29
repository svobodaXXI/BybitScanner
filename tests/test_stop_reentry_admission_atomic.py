"""Canonical Scanner admission and reentry Diary identity share one SQLite commit."""
from decimal import Decimal
import sqlite3

import pytest

from terminal.application import robot_admission
from terminal.application.robot_admission import (
    RobotReentryAdmissionRequest, admit_robot_candidate,
)
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import PersistenceError, SQLiteStore


def _candidate(candidate_id):
    return {
        "candidate_id": candidate_id,
        "status": "AVAILABLE",
        "symbol": "LABUSDT",
        "timeframe": "1",
        "signal_snapshot": {
            "pattern": "Falling Wedge",
            "fixture_unique_candidate": candidate_id,
        },
    }


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "paper.sqlite3"
    with SQLiteStore.open(db) as store:
        account = TradingAccountId("paper")
        row = store.initialize_robot_runtime_state(account, updated_at_ms=0)
        store.update_robot_runtime_state(
            account, mode="ROBOT_RUNNING", recovery_status="READY",
            reason=None, expected_version=row.version, updated_at_ms=1,
        )
    monkeypatch.setattr(
        robot_admission, "load_candidate",
        lambda candidate_id, **kwargs: _candidate(candidate_id),
    )
    return db


def proposal(*, risk="4", budget="10"):
    return RobotReentryAdmissionRequest(
        campaign_id="campaign-frozen-lab-long",
        direction="LONG",
        frozen_thesis_sha256="f" * 64,
        reserved_risk_usdt=Decimal(risk),
        original_risk_budget_usdt=Decimal(budget),
    )


def _counts(path):
    with sqlite3.connect(path) as con:
        return (
            con.execute("SELECT count(*) FROM robot_candidates").fetchone()[0],
            con.execute("SELECT count(*) FROM robot_reentry_campaigns").fetchone()[0],
            con.execute("SELECT count(*) FROM robot_reentry_attempts").fetchone()[0],
        )


def test_original_candidate_and_diary_lineage_are_one_atomic_admission(env):
    recorded, created = admit_robot_candidate(
        "original", database_path=env, clock_ms=lambda: 100,
        mark_legacy_approved=False, reentry=proposal(),
    )
    assert created is True
    assert recorded.candidate_id == "original"
    assert _counts(env) == (1, 1, 1)
    recorded_again, created_again = admit_robot_candidate(
        "original", database_path=env, clock_ms=lambda: 101,
        mark_legacy_approved=False, reentry=proposal(),
    )
    assert not created_again
    assert recorded_again.candidate_id == "original"
    assert _counts(env) == (1, 1, 1)


def test_reentry_contract_failure_rolls_back_canonical_candidate(env):
    with pytest.raises(PersistenceError, match="risk budget"):
        admit_robot_candidate(
            "original", database_path=env, clock_ms=lambda: 100,
            mark_legacy_approved=False, reentry=proposal(risk="20", budget="10"),
        )
    assert _counts(env) == (0, 0, 0)


def test_existing_scanner_candidate_without_reentry_contract_is_unchanged(env):
    recorded, created = admit_robot_candidate(
        "normal", database_path=env, clock_ms=lambda: 100,
        mark_legacy_approved=False,
    )
    assert created and recorded.candidate_id == "normal"
    assert _counts(env) == (1, 0, 0)


def test_external_admission_transaction_can_atomically_rollback_both(env):
    with SQLiteStore.open(env) as store:
        with pytest.raises(RuntimeError), store.robot_admission_transaction():
            admit_robot_candidate(
                "original", transaction_store=store, clock_ms=lambda: 100,
                mark_legacy_approved=False, reentry=proposal(),
            )
            raise RuntimeError("simulated process failure before commit")
    assert _counts(env) == (0, 0, 0)
