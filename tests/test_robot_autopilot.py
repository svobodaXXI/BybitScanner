import sqlite3
import tempfile
import unittest
from pathlib import Path

from terminal.application.robot_autopilot import (
    OUTCOME_ALLOW,
    OUTCOME_REJECT,
    OUTCOME_WAIT,
    REASON_ALREADY_ADMITTED,
    REASON_AUTOPILOT_MODE_INVALID,
    REASON_AUTOPILOT_OFF,
    REASON_CANDIDATE_INVALID,
    REASON_CANDIDATE_INVALIDATED,
    REASON_CANDIDATE_NOT_EXECUTABLE,
    REASON_CANDIDATE_STALE,
    REASON_ELIGIBLE,
    REASON_LIVE_NOT_ALLOWED,
    REASON_PORTFOLIO_POLICY_UNSET,
    REASON_PROTECTION_UNHEALTHY,
    REASON_RECONCILIATION_REQUIRED,
    REASON_ROBOT_NOT_READY,
    REASON_SYMBOL_OWNED,
    RobotAutoAdmissionFacts,
    evaluate_auto_admission,
    record_auto_decision,
)
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    PersistenceError,
    SQLiteStore,
)


ACCOUNT = TradingAccountId("paper")


def eligible_facts(**changes):
    values = dict(
        autopilot_mode="SHADOW",
        environment="PAPER",
        robot_mode="ROBOT_RUNNING",
        robot_recovery_status="READY",
        candidate_valid=True,
        candidate_executable=True,
        candidate_stale=False,
        candidate_invalidated=False,
        already_admitted=False,
        reconciliation_clear=True,
        symbol_owned=False,
        protection_healthy=True,
        portfolio_policy_ready=True,
    )
    values.update(changes)
    return RobotAutoAdmissionFacts(**values)


class RobotAutopilotPolicyTests(unittest.TestCase):
    def test_eligible_shadow_candidate_is_allow_without_side_effects(self):
        result = evaluate_auto_admission(eligible_facts())
        self.assertEqual((result.outcome, result.reason_code), (OUTCOME_ALLOW, REASON_ELIGIBLE))

    def test_policy_reason_precedence_is_stable_and_fail_closed(self):
        cases = (
            (dict(autopilot_mode="OFF"), OUTCOME_WAIT, REASON_AUTOPILOT_OFF),
            (dict(autopilot_mode="BROKEN"), OUTCOME_REJECT, REASON_AUTOPILOT_MODE_INVALID),
            (dict(environment="MAINNET"), OUTCOME_REJECT, REASON_LIVE_NOT_ALLOWED),
            (dict(candidate_valid=False), OUTCOME_REJECT, REASON_CANDIDATE_INVALID),
            (dict(candidate_executable=False), OUTCOME_REJECT, REASON_CANDIDATE_NOT_EXECUTABLE),
            (dict(candidate_stale=True), OUTCOME_REJECT, REASON_CANDIDATE_STALE),
            (dict(candidate_invalidated=True), OUTCOME_REJECT, REASON_CANDIDATE_INVALIDATED),
            (dict(already_admitted=True), OUTCOME_WAIT, REASON_ALREADY_ADMITTED),
            (dict(robot_recovery_status="PAUSED"), OUTCOME_WAIT, REASON_ROBOT_NOT_READY),
            (dict(reconciliation_clear=False), OUTCOME_WAIT, REASON_RECONCILIATION_REQUIRED),
            (dict(symbol_owned=True), OUTCOME_WAIT, REASON_SYMBOL_OWNED),
            (dict(protection_healthy=False), OUTCOME_WAIT, REASON_PROTECTION_UNHEALTHY),
            (dict(portfolio_policy_ready=False), OUTCOME_WAIT, REASON_PORTFOLIO_POLICY_UNSET),
        )
        for changes, outcome, reason in cases:
            with self.subTest(changes=changes):
                result = evaluate_auto_admission(eligible_facts(**changes))
                self.assertEqual((result.outcome, result.reason_code), (outcome, reason))


class RobotAutopilotPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "paper.sqlite3"

    def _open(self):
        return SQLiteStore.open(self.db)

    def _shadow_store(self):
        store = self._open()
        state = store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=1000)
        state = store.update_robot_autopilot_state(
            ACCOUNT, mode="SHADOW", expected_version=state.version, updated_at_ms=1100,
        )
        self.assertEqual(state.mode, "SHADOW")
        return store

    def test_paper_runtime_startup_materializes_autopilot_off(self):
        from tests.test_terminal_paper_runtime import _runtime

        runtime = _runtime(self.db)
        try:
            state = runtime.store.get_robot_autopilot_state(ACCOUNT)
            self.assertIsNotNone(state)
            self.assertEqual((state.mode, state.version), ("OFF", 1))
        finally:
            runtime.close()

    def test_state_defaults_off_and_persists_mode_across_restart(self):
        with self._open() as store:
            state = store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=1000)
            self.assertEqual((state.mode, state.version), ("OFF", 1))
            shadow = store.update_robot_autopilot_state(
                ACCOUNT, mode="SHADOW", expected_version=1, updated_at_ms=1100,
            )
            self.assertEqual((shadow.mode, shadow.version), ("SHADOW", 2))

        with self._open() as reopened:
            persisted = reopened.get_robot_autopilot_state(ACCOUNT)
            self.assertEqual((persisted.mode, persisted.version), ("SHADOW", 2))
            auto = reopened.update_robot_autopilot_state(
                ACCOUNT, mode="PAPER_AUTO", expected_version=2, updated_at_ms=1200,
            )
            self.assertEqual((auto.mode, auto.version), ("PAPER_AUTO", 3))
            with self.assertRaisesRegex(ValueError, "unsupported Robot Autopilot mode"):
                reopened.update_robot_autopilot_state(
                    ACCOUNT, mode="LIVE_AUTO", expected_version=3, updated_at_ms=1300,
                )

    def test_shadow_decision_is_append_only_idempotent_and_does_not_mutate_candidate(self):
        store = self._shadow_store()
        try:
            candidate, _ = store.create_robot_candidate(
                candidate_id="candidate-1",
                trading_account_id=ACCOUNT,
                symbol=Symbol("BTCUSDT"),
                status="APPROVED",
                signal_snapshot={"symbol": "BTCUSDT", "pattern": "Falling Wedge"},
                approved_at_ms=1000,
                updated_at_ms=1000,
            )
            before = store.get_robot_candidate(candidate.candidate_id)
            facts = eligible_facts()
            result = evaluate_auto_admission(facts)
            first, created = record_auto_decision(
                store,
                trading_account_id=ACCOUNT,
                candidate_ref=candidate.candidate_id,
                pattern="Falling Wedge",
                symbol=Symbol("BTCUSDT"),
                timeframe="1",
                source_identity=candidate.candidate_id,
                snapshot_sha256=candidate.snapshot_sha256,
                facts=facts,
                result=result,
                evaluated_at_ms=2000,
            )
            replay, created_again = record_auto_decision(
                store,
                trading_account_id=ACCOUNT,
                candidate_ref=candidate.candidate_id,
                pattern="Falling Wedge",
                symbol=Symbol("BTCUSDT"),
                timeframe="1",
                source_identity=candidate.candidate_id,
                snapshot_sha256=candidate.snapshot_sha256,
                facts=facts,
                result=result,
                evaluated_at_ms=2000,
            )
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(replay, first)
            self.assertEqual(
                (first.outcome, first.reason_code, first.resulting_candidate_id),
                (OUTCOME_ALLOW, REASON_ELIGIBLE, None),
            )
            self.assertEqual(store.get_robot_candidate(candidate.candidate_id), before)
            self.assertEqual(store.load_robot_auto_decisions(ACCOUNT), (first,))
        finally:
            store.close()

        with self._open() as reopened:
            decisions = reopened.load_robot_auto_decisions(ACCOUNT)
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0].candidate_ref, "candidate-1")

    def test_audit_refuses_mode_mismatch_and_off_has_no_record(self):
        with self._open() as store:
            store.initialize_robot_autopilot_state(ACCOUNT, updated_at_ms=1000)
            facts = eligible_facts()
            result = evaluate_auto_admission(facts)
            with self.assertRaisesRegex(PersistenceError, "mode does not match"):
                record_auto_decision(
                    store,
                    trading_account_id=ACCOUNT,
                    candidate_ref="candidate-1",
                    pattern="L-shape",
                    symbol=Symbol("TESTUSDT"),
                    timeframe="5",
                    source_identity="candidate-1",
                    snapshot_sha256=None,
                    facts=facts,
                    result=result,
                    evaluated_at_ms=2000,
                )
            self.assertEqual(store.load_robot_auto_decisions(ACCOUNT), ())

    def test_v23_database_migrates_to_autopilot_tables_without_arming_it(self):
        with self._open() as store:
            self.assertEqual(store.settings().schema_version, SCHEMA_VERSION)
        connection = sqlite3.connect(self.db)
        connection.execute("DROP TABLE robot_auto_decisions")
        connection.execute("DROP TABLE robot_autopilot_state")
        connection.execute("PRAGMA user_version = 23")
        connection.commit()
        connection.close()

        with self._open() as migrated:
            self.assertEqual(migrated.settings().schema_version, SCHEMA_VERSION)
            self.assertTrue(migrated.has_table("robot_autopilot_state"))
            self.assertTrue(migrated.has_table("robot_auto_decisions"))
            self.assertIsNone(migrated.get_robot_autopilot_state(ACCOUNT))


if __name__ == "__main__":
    unittest.main()
