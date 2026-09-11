import tempfile
import unittest
from pathlib import Path

from robot_candidate_store import create_signal_snapshot, load_candidate
from terminal.application.robot_admission import (
    RobotAdmissionRejected,
    admit_robot_candidate,
)
from terminal.domain.models import TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


class RobotAdmissionGateTests(unittest.TestCase):
    def _make_candidate(self, directory: Path, candidate_id: str = "candidate-1"):
        return create_signal_snapshot(
            {
                "symbol": "ONGUSDT",
                "pattern": "Falling Wedge",
                "geometry": {
                    "current_index": 10,
                    "apex": {"index": 30},
                    "upper_line": {"slope": 0.1, "intercept": 10},
                    "lower_line": {"slope": -0.1, "intercept": 20},
                },
            },
            timeframe="1",
            store_dir=directory,
            candidate_id=candidate_id,
            created_at="2026-09-09T20:00:00+00:00",
        )

    @staticmethod
    def _ready_database(path: Path) -> None:
        store = SQLiteStore.open(path)
        try:
            runtime = store.initialize_robot_runtime_state(
                TradingAccountId("paper"), updated_at_ms=1000,
            )
            store.update_robot_runtime_state(
                TradingAccountId("paper"),
                mode="ROBOT_RUNNING",
                recovery_status="READY",
                reason=None,
                expected_version=runtime.version,
                updated_at_ms=1001,
            )
        finally:
            store.close()

    def test_stopped_runtime_rejects_without_legacy_approval_or_sqlite_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir)

            store = SQLiteStore.open(db_path)
            try:
                store.initialize_robot_runtime_state(
                    TradingAccountId("paper"), updated_at_ms=1000,
                )
            finally:
                store.close()

            with self.assertRaises(RobotAdmissionRejected):
                admit_robot_candidate(
                    "candidate-1",
                    database_path=db_path,
                    store_dir=candidate_dir,
                    clock_ms=lambda: 1002,
                )

            legacy = load_candidate("candidate-1", store_dir=candidate_dir)
            self.assertEqual(legacy["status"], "AVAILABLE")

            store = SQLiteStore.open(db_path)
            try:
                self.assertIsNone(store.get_robot_candidate("candidate-1"))
            finally:
                store.close()

    def test_ready_runtime_admits_and_marks_legacy_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir)
            self._ready_database(db_path)

            record, created = admit_robot_candidate(
                "candidate-1",
                approval={"source": "telegram_robot_button", "message_id": 100},
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 2000,
            )

            self.assertTrue(created)
            self.assertEqual(record.candidate_id, "candidate-1")
            self.assertEqual(record.trading_account_id, TradingAccountId("paper"))
            self.assertEqual(record.status, "APPROVED")
            self.assertEqual(load_candidate("candidate-1", store_dir=candidate_dir)["status"], "APPROVED")

    def test_repeat_admission_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir)
            self._ready_database(db_path)

            first, created = admit_robot_candidate(
                "candidate-1",
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 2000,
            )
            second, repeated_created = admit_robot_candidate(
                "candidate-1",
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 3000,
            )

            self.assertTrue(created)
            self.assertFalse(repeated_created)
            self.assertEqual(first, second)

    def test_existing_admission_is_returned_without_requiring_runtime_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir)
            self._ready_database(db_path)

            first, _ = admit_robot_candidate(
                "candidate-1",
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 2000,
            )

            store = SQLiteStore.open(db_path)
            try:
                runtime = store.get_robot_runtime_state(TradingAccountId("paper"))
                assert runtime is not None
                store.update_robot_runtime_state(
                    TradingAccountId("paper"),
                    mode="ROBOT_STOPPED",
                    recovery_status="ROBOT_STOPPED",
                    reason=None,
                    expected_version=runtime.version,
                    updated_at_ms=3000,
                )
            finally:
                store.close()

            second, created = admit_robot_candidate(
                "candidate-1",
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 4000,
            )

            self.assertFalse(created)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
