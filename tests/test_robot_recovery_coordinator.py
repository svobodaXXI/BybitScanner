from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from robot_state_machine import initialize_state
from terminal.application.robot_recovery import (
    PAUSED,
    READY,
    RECONCILING,
    RobotRecoveryCoordinator,
    RobotRecoveryError,
)
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


ACCOUNT_ID = TradingAccountId("paper")


def _snapshot():
    return {
        "symbol": "TESTUSDT",
        "pattern": "Falling Wedge",
        "geometry": {
            "upper_line": {"slope": -1.0, "intercept": 200.0},
            "lower_line": {"slope": -0.5, "intercept": 145.0},
            "apex": {"index": 110, "price": 90.0, "valid_intersection": True},
            "current_index": 100,
        },
    }


def _state():
    candidate = {
        "candidate_id": "candidate-1",
        "status": "APPROVED",
        "timeframe": "1",
        "symbol": "TESTUSDT",
        "signal_snapshot": _snapshot(),
    }
    state, _ = initialize_state(candidate)
    return state


class _Clock:
    def __init__(self, value=1000):
        self.value = value

    def __call__(self):
        self.value += 1
        return self.value


class RobotRecoveryCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = SQLiteStore.open(Path(self.temp_dir.name) / "terminal.db")
        self.clock = _Clock()

    def tearDown(self):
        self.store.close()
        self.temp_dir.cleanup()

    def _initialize_running(self):
        state = self.store.initialize_robot_runtime_state(
            ACCOUNT_ID, updated_at_ms=self.clock(),
        )
        return self.store.update_robot_runtime_state(
            ACCOUNT_ID,
            mode="ROBOT_RUNNING",
            recovery_status=READY,
            reason=None,
            expected_version=state.version,
            updated_at_ms=self.clock(),
        )

    def _create_waiting_candidate(self):
        candidate, created = self.store.create_robot_candidate(
            candidate_id="candidate-1",
            trading_account_id=ACCOUNT_ID,
            symbol=Symbol("TESTUSDT"),
            status="APPROVED",
            signal_snapshot=_snapshot(),
            approved_at_ms=self.clock(),
            updated_at_ms=self.clock(),
        )
        self.assertTrue(created)
        return self.store.save_robot_candidate_state(
            candidate.candidate_id,
            status="APPROVED",
            robot_state=_state(),
            expected_revision=candidate.state_revision,
            updated_at_ms=self.clock(),
        )

    def _create_open_candidate(self):
        candidate, created = self.store.create_robot_candidate(
            candidate_id="candidate-open",
            trading_account_id=ACCOUNT_ID,
            symbol=Symbol("TESTUSDT"),
            status="APPROVED",
            signal_snapshot=_snapshot(),
            approved_at_ms=self.clock(),
            updated_at_ms=self.clock(),
        )
        self.assertTrue(created)
        _, trade_created = self.store.create_robot_trade(
            trade_id="trade-open",
            trading_account_id=ACCOUNT_ID,
            candidate_id=candidate.candidate_id,
            symbol=Symbol("TESTUSDT"),
            direction="LONG",
            pattern="Falling Wedge",
            source_timeframe="1",
            signal_time_ms=10,
            entry_time_ms=20,
            entry_path="MARKET",
            actual_wv=Decimal("1"),
            average_entry=Decimal("100"),
            stop_price=Decimal("98"),
            take_price=Decimal("103"),
            entry_quantity=Decimal("1"),
            entry_position_version=1,
            created_at_ms=self.clock(),
        )
        self.assertTrue(trade_created)

    def test_first_run_stays_stopped_and_admission_closed(self):
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.mode, "ROBOT_STOPPED")
        self.assertEqual(result.runtime_state.recovery_status, "ROBOT_STOPPED")
        self.assertFalse(result.admission_ready)
        self.assertFalse(coordinator.admission_ready())

    def test_stopped_with_surviving_open_trade_requires_reconciliation(self):
        self._create_open_candidate()
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.mode, "ROBOT_STOPPED")
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertFalse(result.admission_ready)

    def test_stopped_reconciliation_required_is_not_auto_cleared(self):
        runtime = self.store.initialize_robot_runtime_state(
            ACCOUNT_ID, updated_at_ms=self.clock(),
        )
        self.store.update_robot_runtime_state(
            ACCOUNT_ID,
            mode="ROBOT_STOPPED",
            recovery_status="RECONCILIATION_REQUIRED",
            reason="earlier ambiguous recovery",
            expected_version=runtime.version,
            updated_at_ms=self.clock(),
        )
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(result.runtime_state.reason, "earlier ambiguous recovery")
        self.assertFalse(result.admission_ready)

    def test_running_waiting_candidate_recovers_before_ready(self):
        original = self._create_waiting_candidate()
        self._initialize_running()
        coordinator = RobotRecoveryCoordinator(
            self.store,
            ACCOUNT_ID,
            latest_geometry_index_provider=lambda symbol, snapshot: 105,
            clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, READY)
        self.assertTrue(result.admission_ready)
        recovered = self.store.get_robot_candidate(original.candidate_id)
        self.assertIsNotNone(recovered)
        self.assertEqual(recovered.state_revision, original.state_revision + 1)
        self.assertEqual(recovered.robot_state["geometry_cursor"], 105)
        self.assertEqual(recovered.robot_state["phase"], "WAITING_BREAKOUT")

    def test_legacy_waiting_candidate_without_cursor_anchor_fails_closed_before_network(self):
        self._create_waiting_candidate()
        self._initialize_running()
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertFalse(result.admission_ready)
        self.assertIn("Scanner geometry cursor anchor", result.runtime_state.reason)

    def test_running_open_trade_can_recover_without_geometry_read(self):
        self._create_open_candidate()
        self._initialize_running()
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.recovery_status, READY)
        self.assertTrue(result.admission_ready)
        self.assertEqual(result.decisions[0].status, "RESUME_OPEN_POSITION")

    def test_restart_while_paused_lands_back_on_paused_not_ready(self):
        running = self._initialize_running()
        self.store.update_robot_runtime_state(
            ACCOUNT_ID,
            mode="ROBOT_RUNNING",
            recovery_status=PAUSED,
            reason=None,
            expected_version=running.version,
            updated_at_ms=self.clock(),
        )
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, PAUSED)
        self.assertFalse(result.admission_ready)

    def test_restart_while_reconciliation_required_stays_fenced_not_ready(self):
        """A backend restart must not reopen admission over unproven evidence.

        RECONCILIATION_REQUIRED is not PAUSED, so the was_paused branch used to
        fall through to READY and silently clear the fence while stale Robot
        trades were still open.
        """
        self._create_open_candidate()
        running = self._initialize_running()
        fenced = self.store.update_robot_runtime_state(
            ACCOUNT_ID,
            mode="ROBOT_RUNNING",
            recovery_status="RECONCILIATION_REQUIRED",
            reason="reconcile_robot cannot prove Robot ownership/protection for: trade-open",
            expected_version=running.version,
            updated_at_ms=self.clock(),
        )
        candidate_before = self.store.get_robot_candidate("candidate-open")
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )

        result = coordinator.recover()

        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(
            result.runtime_state.reason,
            "reconcile_robot cannot prove Robot ownership/protection for: trade-open",
        )
        self.assertFalse(result.admission_ready)
        self.assertEqual(result.decisions, ())
        # Nothing was persisted: neither the runtime row nor candidate state.
        self.assertEqual(result.runtime_state.version, fenced.version)
        durable = self.store.get_robot_runtime_state(ACCOUNT_ID)
        self.assertEqual(durable.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertEqual(durable.version, fenced.version)
        candidate_after = self.store.get_robot_candidate("candidate-open")
        self.assertEqual(candidate_after.state_revision, candidate_before.state_revision)
        self.assertEqual(candidate_after.updated_at_ms, candidate_before.updated_at_ms)
        # The explicit operator path remains the only way out.
        self.assertEqual(
            coordinator.reconcile_required().runtime_state.recovery_status, RECONCILING,
        )

    def test_restart_while_paused_with_open_trade_still_reconciles_it(self):
        self._create_open_candidate()
        running = self._initialize_running()
        self.store.update_robot_runtime_state(
            ACCOUNT_ID,
            mode="ROBOT_RUNNING",
            recovery_status=PAUSED,
            reason=None,
            expected_version=running.version,
            updated_at_ms=self.clock(),
        )
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.recover()
        self.assertEqual(result.runtime_state.recovery_status, PAUSED)
        self.assertFalse(result.admission_ready)
        self.assertEqual(result.decisions[0].status, "RESUME_OPEN_POSITION")

    def test_reconcile_required_holds_reconciling_until_runtime_finishes(self):
        running = self._initialize_running()
        self.store.update_robot_runtime_state(
            ACCOUNT_ID, mode="ROBOT_RUNNING",
            recovery_status="RECONCILIATION_REQUIRED", reason="needs repair",
            expected_version=running.version, updated_at_ms=self.clock(),
        )
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.reconcile_required()
        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, RECONCILING)
        self.assertFalse(result.admission_ready)
        self.assertFalse(coordinator.admission_ready())

    def test_reconcile_required_rejects_every_other_durable_state_without_side_effect(self):
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        running = self._initialize_running()
        with self.assertRaises(RobotRecoveryError):
            coordinator.reconcile_required()
        self.assertEqual(
            self.store.get_robot_runtime_state(ACCOUNT_ID).version, running.version,
        )

        paused = self.store.update_robot_runtime_state(
            ACCOUNT_ID, mode="ROBOT_RUNNING", recovery_status=PAUSED, reason=None,
            expected_version=running.version, updated_at_ms=self.clock(),
        )
        with self.assertRaises(RobotRecoveryError):
            coordinator.reconcile_required()
        self.assertEqual(
            self.store.get_robot_runtime_state(ACCOUNT_ID).version, paused.version,
        )

        stopped_required = self.store.update_robot_runtime_state(
            ACCOUNT_ID, mode="ROBOT_STOPPED",
            recovery_status="RECONCILIATION_REQUIRED", reason="stopped ambiguity",
            expected_version=paused.version, updated_at_ms=self.clock(),
        )
        with self.assertRaises(RobotRecoveryError):
            coordinator.reconcile_required()
        self.assertEqual(
            self.store.get_robot_runtime_state(ACCOUNT_ID).version, stopped_required.version,
        )

    def test_start_from_never_initialized_reaches_running_ready(self):
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )
        result = coordinator.start()
        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, READY)
        self.assertTrue(result.admission_ready)

    def test_start_recovers_a_surviving_waiting_candidate(self):
        original = self._create_waiting_candidate()
        coordinator = RobotRecoveryCoordinator(
            self.store,
            ACCOUNT_ID,
            latest_geometry_index_provider=lambda symbol, snapshot: 105,
            clock_ms=self.clock,
        )
        result = coordinator.start()
        self.assertEqual(result.runtime_state.recovery_status, READY)
        recovered = self.store.get_robot_candidate(original.candidate_id)
        self.assertEqual(recovered.state_revision, original.state_revision + 1)


if __name__ == "__main__":
    unittest.main()
