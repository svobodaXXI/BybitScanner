from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from robot_state_machine import initialize_state
from terminal.application.robot_recovery import (
    READY,
    RobotRecoveryCoordinator,
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
            latest_geometry_index_provider=lambda symbol: 105,
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

    def test_missing_geometry_provider_fails_closed(self):
        self._create_waiting_candidate()
        self._initialize_running()
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )

        result = coordinator.recover()

        self.assertEqual(result.runtime_state.mode, "ROBOT_RUNNING")
        self.assertEqual(result.runtime_state.recovery_status, "RECONCILIATION_REQUIRED")
        self.assertFalse(result.admission_ready)
        self.assertIn("geometry index provider", result.runtime_state.reason)

    def test_running_open_trade_can_recover_without_geometry_provider(self):
        self._create_open_candidate()
        self._initialize_running()
        coordinator = RobotRecoveryCoordinator(
            self.store, ACCOUNT_ID, clock_ms=self.clock,
        )

        result = coordinator.recover()

        self.assertEqual(result.runtime_state.recovery_status, READY)
        self.assertTrue(result.admission_ready)
        self.assertEqual(result.decisions[0].status, "RESUME_OPEN_POSITION")


if __name__ == "__main__":
    unittest.main()
