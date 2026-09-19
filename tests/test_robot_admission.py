import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from robot_candidate_store import create_signal_snapshot, load_candidate
from terminal.application.robot_admission import (
    RobotAdmissionRejected,
    admit_robot_candidate,
)
from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import SQLiteStore


class RobotAdmissionGateTests(unittest.TestCase):
    def _make_candidate(
        self, directory: Path, candidate_id: str = "candidate-1", pattern: str = "Falling Wedge",
    ):
        return create_signal_snapshot(
            {
                "symbol": "ONGUSDT",
                "pattern": pattern,
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

    def test_unsupported_pattern_is_rejected_before_sqlite_admission(self):
        import telegram_review

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir, pattern="Triangle Compression")
            self._ready_database(db_path)

            with self.assertRaises(RobotAdmissionRejected) as raised:
                admit_robot_candidate(
                    "candidate-1",
                    database_path=db_path,
                    store_dir=candidate_dir,
                    clock_ms=lambda: 2000,
                )

            self.assertEqual(
                telegram_review._robot_admission_reason_text(raised.exception),
                "паттерн не поддерживается роботом",
            )
            self.assertEqual(
                load_candidate("candidate-1", store_dir=candidate_dir)["status"], "AVAILABLE",
            )
            store = SQLiteStore.open(db_path)
            try:
                self.assertIsNone(store.get_robot_candidate("candidate-1"))
            finally:
                store.close()

    def test_5m_candidate_without_projected_robot_geometry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            create_signal_snapshot(
                {
                    "symbol": "ONGUSDT",
                    "pattern": "Falling Wedge",
                    "timeframe": "5",
                    "geometry": {
                        "current_index": 10,
                        "apex": {"index": 30},
                        "upper_line": {"slope": -1.0, "intercept": 20},
                        "lower_line": {"slope": -0.5, "intercept": 15},
                    },
                    "robot_handoff_ready": False,
                },
                timeframe="5",
                store_dir=candidate_dir,
                candidate_id="candidate-5m",
                created_at="2026-09-09T20:00:00+00:00",
            )
            self._ready_database(db_path)

            with self.assertRaisesRegex(
                RobotAdmissionRejected, "no proven Robot 1m handoff",
            ):
                admit_robot_candidate(
                    "candidate-5m",
                    database_path=db_path,
                    store_dir=candidate_dir,
                    clock_ms=lambda: 2000,
                )

            store = SQLiteStore.open(db_path)
            try:
                self.assertIsNone(store.get_robot_candidate("candidate-5m"))
            finally:
                store.close()

    def test_5m_candidate_with_projected_robot_geometry_is_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            create_signal_snapshot(
                {
                    "symbol": "ONGUSDT",
                    "pattern": "Falling Wedge",
                    "timeframe": "5",
                    "geometry": {
                        "current_index": 10,
                        "apex": {"index": 30},
                        "upper_line": {"slope": -1.0, "intercept": 20},
                        "lower_line": {"slope": -0.5, "intercept": 15},
                    },
                    "robot_geometry": {
                        "current_index": 10,
                        "apex": {"index": 110.0},
                        "upper_line": {"slope": -0.2, "intercept": 12.0},
                        "lower_line": {"slope": -0.1, "intercept": 11.0},
                    },
                    "scanner_geometry_cursor": {
                        "version": "1.0",
                        "timeframe": "1",
                        "geometry_index": 10,
                        "source_candle_time_ms": 1_000_000,
                    },
                    "robot_handoff_ready": True,
                    "scanner_source_timeframe": "5",
                },
                timeframe="5",
                store_dir=candidate_dir,
                candidate_id="candidate-5m",
                created_at="2026-09-09T20:00:00+00:00",
            )
            self._ready_database(db_path)

            record, created = admit_robot_candidate(
                "candidate-5m",
                database_path=db_path,
                store_dir=candidate_dir,
                clock_ms=lambda: 2000,
            )

            self.assertTrue(created)
            self.assertEqual(record.status, "APPROVED")
            self.assertEqual(
                record.signal_snapshot["scanner_source_timeframe"], "5",
            )
            self.assertEqual(
                record.signal_snapshot["robot_geometry"]["apex"]["index"],
                110.0,
            )

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

    def test_active_owner_on_symbol_advisory_rejects_new_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate_dir = root / "candidates"
            db_path = root / "paper.sqlite3"
            self._make_candidate(candidate_dir, "owner")
            self._make_candidate(candidate_dir, "candidate-2")
            self._ready_database(db_path)

            store = SQLiteStore.open(db_path)
            try:
                owner_snapshot = load_candidate("owner", store_dir=candidate_dir)["signal_snapshot"]
                store.create_robot_candidate(
                    candidate_id="owner",
                    trading_account_id=TradingAccountId("paper"),
                    symbol=Symbol("ONGUSDT"),
                    status="APPROVED",
                    signal_snapshot=owner_snapshot,
                    approved_at_ms=1500,
                    updated_at_ms=1500,
                )
                store.create_robot_trade(
                    trade_id="robot-trade-owner",
                    trading_account_id=TradingAccountId("paper"),
                    candidate_id="owner",
                    symbol=Symbol("ONGUSDT"),
                    direction="LONG",
                    pattern="Falling Wedge",
                    source_timeframe="1",
                    signal_time_ms=1500,
                    entry_time_ms=1600,
                    entry_path="LIMIT",
                    actual_wv=Decimal("1"),
                    average_entry=Decimal("1"),
                    stop_price=Decimal("0.9"),
                    take_price=Decimal("1.2"),
                    entry_quantity=Decimal("1"),
                    entry_position_version=1,
                    created_at_ms=1600,
                )
            finally:
                store.close()

            with self.assertRaisesRegex(
                RobotAdmissionRejected, "active exposure owner: owner",
            ):
                admit_robot_candidate(
                    "candidate-2",
                    database_path=db_path,
                    store_dir=candidate_dir,
                    clock_ms=lambda: 2000,
                )

            self.assertEqual(
                load_candidate("candidate-2", store_dir=candidate_dir)["status"],
                "AVAILABLE",
            )
            store = SQLiteStore.open(db_path)
            try:
                self.assertIsNone(store.get_robot_candidate("candidate-2"))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
