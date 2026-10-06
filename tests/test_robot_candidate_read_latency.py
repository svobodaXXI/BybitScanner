"""P0 Robot protection latency (Slice 2A): robot_candidates hot-path reads.

Incident 2026-10-06: one owner task (process_orderbook_update ~8.4 s,
protection ~4.1 s) could fill the 64-slot protection ingress by itself. The
dominant substage was SQLite: robot_candidates is a WITHOUT ROWID table with
multi-KB signal snapshots and no symbol/status index, so the per-symbol and
active-status reads made on every protection event walked the entire
candidate history (~206 ms per read on the incident database). Schema v25
adds read-only indexes; these tests pin the access path, the history-
independent cost, the migration, and unchanged STOP/TAKE outcomes.

Cost is measured in SQLite VM steps (deterministic), not wall time.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence import schema
from terminal.persistence.sqlite_store import SchemaError, SQLiteStore
from tests.test_terminal_paper_runtime import (
    MutableBookProvider,
    _crossing_book,
    _entry_book,
    _open_robot_position_with_confirmed_protection,
    _runtime_with_provider,
)


ACCOUNT = TradingAccountId("paper")
HOT_INDEXES = ("robot_candidates_account_symbol", "robot_candidates_account_status")


def _seed_history(store: SQLiteStore, start: int, count: int) -> None:
    """Finished candidates on unrelated symbols with Box-sized snapshots."""
    for index in range(start, start + count):
        candidate_id = f"history-{index}"
        store.create_robot_candidate(
            candidate_id=candidate_id, trading_account_id=ACCOUNT,
            symbol=Symbol(f"HIST{index % 40}USDT"), status="APPROVED",
            signal_snapshot={
                "pattern": "IKIGAI_BOX", "index": index,
                "candles": [[minute, "1.0", "2.0"] for minute in range(400)],
            },
            approved_at_ms=1000, updated_at_ms=1000,
        )
        store.save_robot_candidate_state(
            candidate_id, status="EXPIRED", robot_state={"phase": "EXPIRED"},
            expected_revision=0, updated_at_ms=1001,
        )


def _drop_hot_indexes(store: SQLiteStore) -> None:
    for name in HOT_INDEXES:
        store._connection.execute(f"DROP INDEX {name}")


def _vm_steps(store: SQLiteStore, operation) -> int:
    steps = 0

    def count() -> int:
        nonlocal steps
        steps += 1
        return 0

    store._connection.set_progress_handler(count, 1)
    try:
        operation()
    finally:
        store._connection.set_progress_handler(None, 1)
    return steps


def _open_position_runtime(path: Path, provider: MutableBookProvider):
    runtime = _runtime_with_provider(path, provider)
    _open_robot_position_with_confirmed_protection(
        runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
        stop_price=Decimal("64000"), take_price=Decimal("64600"),
        trade_id="trade-latency", candidate_id="candidate-latency",
    )
    return runtime


class RobotCandidateHotReadAccessPathTests(unittest.TestCase):
    def test_per_symbol_and_active_reads_use_account_indexes(self):
        with tempfile.TemporaryDirectory() as temp:
            store = SQLiteStore.open(Path(temp) / "paper.sqlite3")
            try:
                statements: list[str] = []
                store._connection.set_trace_callback(statements.append)
                store.load_robot_candidates_for_symbol(ACCOUNT, Symbol("BTCUSDT"))
                store.load_active_robot_candidate_states(ACCOUNT)
                store._connection.set_trace_callback(None)
                reads = [sql for sql in statements if "FROM robot_candidates" in sql]
                self.assertEqual(len(reads), 2)
                for sql, index in zip(reads, HOT_INDEXES):
                    plan = " ".join(
                        str(row[-1])
                        for row in store._connection.execute(f"EXPLAIN QUERY PLAN {sql}")
                    )
                    self.assertIn(f"USING INDEX {index}", plan)
            finally:
                store.close()

    def test_protection_event_read_cost_does_not_scale_with_candidate_history(self):
        def growth(*, indexed: bool) -> tuple[int, int]:
            with tempfile.TemporaryDirectory() as temp:
                provider = MutableBookProvider("BTCUSDT", _entry_book())
                runtime = _open_position_runtime(Path(temp) / "paper.sqlite3", provider)
                try:
                    if not indexed:
                        _drop_hot_indexes(runtime.store)

                    def event() -> None:
                        book = _crossing_book("BTCUSDT", bid="64249.5", ask="64250.5")
                        finalized, obligation = runtime.process_robot_market_event(
                            "BTCUSDT", book,
                            event_id=f"BTCUSDT:{book.source_sequence}:{book.source_update_id}",
                            received_at_ms=book.received_at_ms,
                        )
                        self.assertEqual((finalized, obligation), ((), None))

                    _seed_history(runtime.store, 0, 20)
                    small = _vm_steps(runtime.store, event)
                    _seed_history(runtime.store, 20, 180)
                    large = _vm_steps(runtime.store, event)
                    return small, large
                finally:
                    runtime.close()

        old_small, old_large = growth(indexed=False)
        new_small, new_large = growth(indexed=True)
        # Old (v24) path: every protection event walks the whole history.
        self.assertGreater(old_large - old_small, 900)
        # Fixed path: 10x more unrelated history costs (almost) nothing.
        self.assertLess(abs(new_large - new_small), 25)
        self.assertLess(new_large * 5, old_large)


class RobotCandidateIndexMigrationTests(unittest.TestCase):
    def _v24_database(self, path: Path) -> tuple:
        store = SQLiteStore.open(path)
        try:
            _seed_history(store, 0, 3)
            before = store.load_robot_candidates(ACCOUNT)
            _drop_hot_indexes(store)
            store._connection.execute("PRAGMA user_version = 24")
        finally:
            store.close()
        return before

    @staticmethod
    def _state(path: Path) -> tuple[int, set[str]]:
        connection = sqlite3.connect(path)
        try:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            names = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='robot_candidates'"
                )
            }
        finally:
            connection.close()
        return version, names

    def test_v24_database_migrates_to_v25_indexes_preserving_candidates(self):
        self.assertEqual(schema.SCHEMA_VERSION, 25)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            before = self._v24_database(path)
            self.assertTrue(set(HOT_INDEXES).isdisjoint(self._state(path)[1]))
            migrated = SQLiteStore.open(path)
            try:
                self.assertEqual(migrated.load_robot_candidates(ACCOUNT), before)
            finally:
                migrated.close()
            version, names = self._state(path)
            self.assertEqual(version, 25)
            self.assertTrue(set(HOT_INDEXES).issubset(names))

    def test_failed_v25_migration_rolls_back_and_retries_cleanly(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            before = self._v24_database(path)
            with patch(
                "terminal.persistence.sqlite_store.SCHEMA_V25_MIGRATION_STATEMENTS",
                schema.SCHEMA_V25_MIGRATION_STATEMENTS + ("INVALID SQL",),
            ):
                with self.assertRaises(SchemaError):
                    SQLiteStore.open(path)
            version, names = self._state(path)
            self.assertEqual(version, 24)
            self.assertTrue(set(HOT_INDEXES).isdisjoint(names))
            migrated = SQLiteStore.open(path)
            try:
                self.assertEqual(migrated.load_robot_candidates(ACCOUNT), before)
            finally:
                migrated.close()
            self.assertEqual(self._state(path)[0], 25)


class RobotProtectionOutcomeEquivalenceTests(unittest.TestCase):
    """The indexes change only the access path: the same ordered events must
    latch and resolve the same STOP/TAKE leg as on the old (v24) path."""

    def _protection_outcome(self, *, indexed: bool, bid: str, ask: str):
        with tempfile.TemporaryDirectory() as temp:
            provider = MutableBookProvider("BTCUSDT", _entry_book())
            runtime = _open_position_runtime(Path(temp) / "paper.sqlite3", provider)
            try:
                if not indexed:
                    _drop_hot_indexes(runtime.store)
                _seed_history(runtime.store, 0, 5)
                trigger = _crossing_book("BTCUSDT", bid=bid, ask=ask)
                provider.set_book("BTCUSDT", trigger)
                results = [
                    runtime.process_robot_market_event(
                        "BTCUSDT", book, event_id=f"evt-{position}",
                        received_at_ms=book.received_at_ms,
                    )
                    for position, book in enumerate((
                        _crossing_book("BTCUSDT", bid="64249.5", ask="64250.5"),
                        trigger,
                        trigger,  # duplicate delivery after resolution
                    ))
                ]
                obligation = results[1][1]
                trade = runtime.store.get_robot_trade("trade-latency")
                executions = runtime.store.load_executions()
                return (
                    results[0],
                    replace(obligation, obligation_id="", version=0, updated_at_ms=0,
                            latched_at_ms=0, source_received_at_ms=0,
                            source_event_at_ms=0, source_sequence=0,
                            source_update_id=0),
                    results[2],
                    (trade.exit_reason, trade.exit_price),
                    len(executions),
                )
            finally:
                runtime.close()

    def test_stop_and_take_outcomes_identical_with_and_without_indexes(self):
        for leg, bid, ask, reason in (
            ("STOP", "63990", "63995", "STOP"),
            ("TAKE", "64610", "64615", "TAKE"),
        ):
            with self.subTest(leg=leg):
                old = self._protection_outcome(indexed=False, bid=bid, ask=ask)
                new = self._protection_outcome(indexed=True, bid=bid, ask=ask)
                self.assertEqual(old[0], ((), None))
                self.assertEqual(new[1].winning_leg, leg)
                self.assertEqual(new[1].status, "RESOLVED")
                self.assertEqual(new[2], ((), None))  # duplicate is a no-op
                self.assertEqual(new[3][0], reason)
                self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
