"""Stable backport of PR #393: robot_candidates hot-path read indexes, no schema bump.

Incident 2026-10-06: protection/book-update owner tasks ran for seconds. The
dominant substage was SQLite: robot_candidates is a WITHOUT ROWID table with
multi-KB signal snapshots and no symbol/status index, so the per-symbol and
active-status reads made on every protection event, book update and coverage
resync walked the whole candidate history (~200 ms per read on a copy of the
laptop DB, growing with history). Main adds the indexes as schema v25; stable
is pinned to schema 24 ("no migration"), so SQLiteStore.open() creates the same
two indexes idempotently and leaves user_version at 24.

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
from terminal.persistence import sqlite_store as sqlite_store_module
from terminal.persistence.sqlite_store import SQLiteStore
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


def _raw_state(path: Path) -> tuple[int, set[str]]:
    connection = sqlite3.connect(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='robot_candidates' AND name NOT LIKE 'sqlite_autoindex%'"
            )
        }
    finally:
        connection.close()
    return version, names


class _RecordingConnection(sqlite3.Connection):
    """Records every statement SQLiteStore.open() sends on its connection."""

    statements: list[str]

    def execute(self, sql, *args, **kwargs):  # noqa: D401 - sqlite3 signature
        if not hasattr(self, "statements"):
            self.statements = []
        self.statements.append(sql)
        return super().execute(sql, *args, **kwargs)


def _open_recording(path: Path) -> tuple[SQLiteStore, list[str]]:
    holder: list[_RecordingConnection] = []
    real_connect = sqlite3.connect

    def connect(*args, **kwargs):
        connection = real_connect(*args, factory=_RecordingConnection, **kwargs)
        connection.statements = []
        holder.append(connection)
        return connection

    with patch.object(sqlite_store_module.sqlite3, "connect", connect):
        store = SQLiteStore.open(path)
    return store, holder[0].statements


def _make_v24_without_indexes(path: Path) -> None:
    store = SQLiteStore.open(path)
    try:
        _seed_history(store, 0, 3)
        _drop_hot_indexes(store)
    finally:
        store.close()
    assert _raw_state(path) == (24, set())


class SchemaStaysAt24Tests(unittest.TestCase):
    def test_schema_module_is_unchanged_at_24(self):
        self.assertEqual(schema.SCHEMA_VERSION, 24)
        self.assertFalse(hasattr(schema, "SCHEMA_V25_MIGRATION_STATEMENTS"))
        self.assertFalse(any("robot_candidates_account" in sql for sql in schema.SCHEMA_STATEMENTS))


class IndexLifecycleTests(unittest.TestCase):
    def test_fresh_database_gets_both_indexes_at_user_version_24(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            SQLiteStore.open(path).close()
            version, names = _raw_state(path)
            self.assertEqual(version, 24)
            self.assertTrue(set(HOT_INDEXES).issubset(names))

    def test_existing_v24_database_without_indexes_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            _make_v24_without_indexes(path)
            store = SQLiteStore.open(path)
            try:
                before = store.load_robot_candidates(ACCOUNT)
                self.assertEqual(len(before), 3)  # candidates preserved
            finally:
                store.close()
            version, names = _raw_state(path)
            self.assertEqual(version, 24)  # no migration, no version bump
            self.assertTrue(set(HOT_INDEXES).issubset(names))

    def test_second_open_issues_no_write_transaction(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            _make_v24_without_indexes(path)

            first, first_statements = _open_recording(path)
            first.close()
            self.assertTrue(any(s.strip().upper().startswith("BEGIN") for s in first_statements))
            self.assertEqual(
                sum("CREATE INDEX" in s.upper() for s in first_statements), len(HOT_INDEXES),
            )

            second, second_statements = _open_recording(path)
            second.close()
            joined = " ".join(second_statements).upper()
            self.assertNotIn("BEGIN", joined)
            self.assertNotIn("CREATE INDEX", joined)
            self.assertEqual(_raw_state(path)[0], 24)

    def test_partially_indexed_database_only_creates_the_missing_index(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.sqlite3"
            _make_v24_without_indexes(path)
            connection = sqlite3.connect(path)
            connection.execute(
                "CREATE INDEX robot_candidates_account_symbol "
                "ON robot_candidates(trading_account_id, symbol)"
            )
            connection.commit()
            connection.close()

            store, statements = _open_recording(path)
            store.close()
            created = [s for s in statements if "CREATE INDEX" in s.upper()]
            self.assertEqual(len(created), 1)
            self.assertIn("robot_candidates_account_status", created[0])
            version, names = _raw_state(path)
            self.assertEqual(version, 24)
            self.assertTrue(set(HOT_INDEXES).issubset(names))


class HotReadAccessPathTests(unittest.TestCase):
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
                runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
                try:
                    _open_robot_position_with_confirmed_protection(
                        runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                        stop_price=Decimal("64000"), take_price=Decimal("64600"),
                        trade_id="trade-latency", candidate_id="candidate-latency",
                    )
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
        # Without the indexes every protection event walks the whole history.
        self.assertGreater(old_large - old_small, 900)
        # With them, 10x more unrelated history costs (almost) nothing.
        self.assertLess(abs(new_large - new_small), 25)
        self.assertLess(new_large * 5, old_large)


class ProtectionOutcomeEquivalenceTests(unittest.TestCase):
    """The indexes change only the access path: identical STOP/TAKE outcomes."""

    def _protection_outcome(self, *, indexed: bool, bid: str, ask: str):
        with tempfile.TemporaryDirectory() as temp:
            provider = MutableBookProvider("BTCUSDT", _entry_book())
            runtime = _runtime_with_provider(Path(temp) / "paper.sqlite3", provider)
            try:
                _open_robot_position_with_confirmed_protection(
                    runtime, symbol="BTCUSDT", entry_price=Decimal("64250.5"),
                    stop_price=Decimal("64000"), take_price=Decimal("64600"),
                    trade_id="trade-latency", candidate_id="candidate-latency",
                )
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
                return (
                    results[0],
                    replace(obligation, obligation_id="", version=0, updated_at_ms=0,
                            latched_at_ms=0, source_received_at_ms=0,
                            source_event_at_ms=0, source_sequence=0,
                            source_update_id=0),
                    results[2],
                    (trade.exit_reason, trade.exit_price),
                    len(runtime.store.load_executions()),
                )
            finally:
                runtime.close()

    def test_stop_and_take_outcomes_identical_with_and_without_indexes(self):
        for leg, bid, ask in (("STOP", "63990", "63995"), ("TAKE", "64610", "64615")):
            with self.subTest(leg=leg):
                old = self._protection_outcome(indexed=False, bid=bid, ask=ask)
                new = self._protection_outcome(indexed=True, bid=bid, ask=ask)
                self.assertEqual(old[0], ((), None))
                self.assertEqual(new[1].winning_leg, leg)
                self.assertEqual(new[1].status, "RESOLVED")
                self.assertEqual(new[2], ((), None))  # duplicate is a no-op
                self.assertEqual(new[3][0], leg)
                self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
