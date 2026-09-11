from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from terminal.application.robot_control import (
    RobotControlRejected,
    close_all_now,
    pause_robot,
    resume_robot,
    start_robot,
    stop_robot,
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


class RobotControlCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "paper.sqlite3"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _set_state(self, *, mode, recovery_status, reason=None):
        store = SQLiteStore.open(self.db_path)
        try:
            runtime = store.get_robot_runtime_state(ACCOUNT_ID)
            if runtime is None:
                runtime = store.initialize_robot_runtime_state(ACCOUNT_ID, updated_at_ms=1000)
            return store.update_robot_runtime_state(
                ACCOUNT_ID, mode=mode, recovery_status=recovery_status, reason=reason,
                expected_version=runtime.version, updated_at_ms=1001,
            )
        finally:
            store.close()

    def _open_candidate(self, *, candidate_id="candidate-open"):
        store = SQLiteStore.open(self.db_path)
        try:
            candidate, _ = store.create_robot_candidate(
                candidate_id=candidate_id,
                trading_account_id=ACCOUNT_ID,
                symbol=Symbol("TESTUSDT"),
                status="APPROVED",
                signal_snapshot=_snapshot(),
                approved_at_ms=1000,
                updated_at_ms=1001,
            )
            store.create_robot_trade(
                trade_id=f"trade-{candidate_id}",
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
                created_at_ms=1002,
            )
        finally:
            store.close()

    def _read_state(self):
        store = SQLiteStore.open(self.db_path)
        try:
            return store.get_robot_runtime_state(ACCOUNT_ID)
        finally:
            store.close()

    # -- start_robot --------------------------------------------------

    def test_start_robot_from_never_initialized_reaches_running_ready(self):
        result = start_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_RUNNING")
        self.assertEqual(result.recovery_status, "READY")

    def test_start_robot_from_stopped_stopped_reaches_running_ready(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        result = start_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_RUNNING")
        self.assertEqual(result.recovery_status, "READY")

    def test_start_robot_rejected_from_stopped_reconciliation_required(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            start_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(self._read_state().recovery_status, "RECONCILIATION_REQUIRED")

    def test_start_robot_rejected_from_running_ready(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        with self.assertRaises(RobotControlRejected):
            start_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_start_robot_rejected_from_running_paused(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        with self.assertRaises(RobotControlRejected):
            start_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    # -- pause_robot --------------------------------------------------

    def test_pause_robot_from_running_ready_reaches_paused(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        result = pause_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_RUNNING")
        self.assertEqual(result.recovery_status, "PAUSED")

    def test_pause_robot_does_not_affect_open_position(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        self._open_candidate()
        pause_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        store = SQLiteStore.open(self.db_path)
        try:
            candidate = store.get_robot_candidate("candidate-open")
        finally:
            store.close()
        self.assertEqual(candidate.status, "OPEN")

    def test_pause_robot_rejected_from_running_paused(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        with self.assertRaises(RobotControlRejected):
            pause_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_pause_robot_rejected_from_running_reconciliation_required(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            pause_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_pause_robot_rejected_from_stopped(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        with self.assertRaises(RobotControlRejected):
            pause_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    # -- resume_robot ---------------------------------------------------

    def test_resume_robot_from_running_paused_reaches_ready(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        result = resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_RUNNING")
        self.assertEqual(result.recovery_status, "READY")

    def test_resume_robot_does_not_affect_open_position(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        self._open_candidate()
        resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        store = SQLiteStore.open(self.db_path)
        try:
            candidate = store.get_robot_candidate("candidate-open")
        finally:
            store.close()
        self.assertEqual(candidate.status, "OPEN")

    def test_resume_robot_rejected_from_running_ready(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        with self.assertRaises(RobotControlRejected):
            resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_resume_robot_rejected_from_running_reconciliation_required(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_resume_robot_rejected_from_stopped_stopped(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        with self.assertRaises(RobotControlRejected):
            resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_resume_robot_rejected_from_stopped_reconciliation_required(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            resume_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    # -- stop_robot -----------------------------------------------------

    def test_stop_robot_from_running_ready_reaches_stopped(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        result = stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_STOPPED")
        self.assertEqual(result.recovery_status, "ROBOT_STOPPED")

    def test_stop_robot_from_running_paused_reaches_stopped(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        result = stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        self.assertEqual(result.mode, "ROBOT_STOPPED")
        self.assertEqual(result.recovery_status, "ROBOT_STOPPED")

    def test_stop_robot_rejected_when_position_open_from_ready(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        self._open_candidate()
        with self.assertRaises(RobotControlRejected):
            stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        state = self._read_state()
        self.assertEqual(state.mode, "ROBOT_RUNNING")
        self.assertEqual(state.recovery_status, "READY")

    def test_stop_robot_rejected_when_position_open_from_paused(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        self._open_candidate()
        with self.assertRaises(RobotControlRejected):
            stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)
        state = self._read_state()
        self.assertEqual(state.mode, "ROBOT_RUNNING")
        self.assertEqual(state.recovery_status, "PAUSED")

    def test_stop_robot_rejected_from_reconciliation_required(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    def test_stop_robot_rejected_from_stopped(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        with self.assertRaises(RobotControlRejected):
            stop_robot(database_path=self.db_path, clock_ms=lambda: 2000)

    # -- close_all_now ---------------------------------------------------

    def test_close_all_now_from_running_ready_posts_to_backend(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        calls = []

        def fake_post(url, payload):
            calls.append((url, payload))
            return {"ok": True, "results": []}

        result = close_all_now(
            database_path=self.db_path, clock_ms=lambda: 2000, http_post=fake_post,
        )
        self.assertEqual(result, {"ok": True, "results": []})
        self.assertEqual(len(calls), 1)
        url, payload = calls[0]
        self.assertEqual(url, "http://127.0.0.1:8765/api/robot/close-all-now")
        self.assertIn("client_action_id", payload)

    def test_close_all_now_from_running_paused_posts_to_backend(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="PAUSED")
        result = close_all_now(
            database_path=self.db_path, clock_ms=lambda: 2000,
            http_post=lambda url, payload: {"ok": True, "results": []},
        )
        self.assertEqual(result, {"ok": True, "results": []})

    def test_close_all_now_uses_custom_backend_url(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")
        calls = []
        close_all_now(
            database_path=self.db_path, clock_ms=lambda: 2000,
            backend_url="http://127.0.0.1:9999",
            http_post=lambda url, payload: calls.append(url) or {"ok": True},
        )
        self.assertEqual(calls, ["http://127.0.0.1:9999/api/robot/close-all-now"])

    def test_close_all_now_rejected_from_stopped(self):
        self._set_state(mode="ROBOT_STOPPED", recovery_status="ROBOT_STOPPED")
        with self.assertRaises(RobotControlRejected):
            close_all_now(
                database_path=self.db_path, clock_ms=lambda: 2000,
                http_post=lambda url, payload: self.fail("must not reach the backend"),
            )

    def test_close_all_now_rejected_from_reconciliation_required(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="RECONCILIATION_REQUIRED")
        with self.assertRaises(RobotControlRejected):
            close_all_now(
                database_path=self.db_path, clock_ms=lambda: 2000,
                http_post=lambda url, payload: self.fail("must not reach the backend"),
            )

    def test_close_all_now_wraps_backend_unreachable_as_rejected(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")

        def unreachable(url, payload):
            raise ConnectionError("backend not running")

        with self.assertRaisesRegex(RobotControlRejected, "could not reach the PAPER backend"):
            close_all_now(database_path=self.db_path, clock_ms=lambda: 2000, http_post=unreachable)

    def test_close_all_now_propagates_backend_rejection(self):
        self._set_state(mode="ROBOT_RUNNING", recovery_status="READY")

        def rejecting(url, payload):
            raise RobotControlRejected("PAPER backend rejected close_all_now: {'ok': False}")

        with self.assertRaises(RobotControlRejected):
            close_all_now(database_path=self.db_path, clock_ms=lambda: 2000, http_post=rejecting)


if __name__ == "__main__":
    unittest.main()
