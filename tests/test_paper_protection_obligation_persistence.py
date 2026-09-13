from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    DuplicateIdentity,
    SQLiteStore,
)


class PaperProtectionObligationPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "paper-protection.sqlite3"
        self.account = TradingAccountId("paper")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _open_trade(
        self, store: SQLiteStore, *, trade_id: str = "robot-trade-c1",
        entry_quantity: Decimal = Decimal("2.5"), entry_position_version: int = 1,
    ) -> None:
        store.create_robot_candidate(
            candidate_id="c1",
            trading_account_id=self.account,
            symbol=Symbol("BTCUSDT"),
            status="APPROVED",
            signal_snapshot={"pattern": "Falling Wedge"},
            approved_at_ms=1000,
            updated_at_ms=1000,
        )
        store.create_robot_trade(
            trade_id=trade_id,
            trading_account_id=self.account,
            candidate_id="c1",
            symbol=Symbol("BTCUSDT"),
            direction="LONG",
            pattern="Falling Wedge",
            source_timeframe="1",
            signal_time_ms=1000,
            entry_time_ms=1100,
            entry_path="LIMIT",
            actual_wv=Decimal("1"),
            average_entry=Decimal("100"),
            stop_price=Decimal("98"),
            take_price=Decimal("104"),
            entry_quantity=entry_quantity,
            entry_position_version=entry_position_version,
            created_at_ms=1100,
        )

    def _make_trade_legacy(self, store: SQLiteStore, trade_id: str) -> None:
        """Simulate a v17 (pre-attestation) row: NULL entry_quantity/
        entry_position_version, exactly what a migrated legacy trade has."""
        store._connection.execute(
            "UPDATE robot_trades SET entry_quantity=NULL, entry_position_version=NULL "
            "WHERE trade_id=?",
            (trade_id,),
        )

    def test_schema_contains_durable_protection_obligation_migration(self) -> None:
        self.assertGreaterEqual(SCHEMA_VERSION, 17)
        store = SQLiteStore.open(self.db_path)
        try:
            self.assertEqual(store.schema_version(), SCHEMA_VERSION)
            self.assertTrue(store.has_table("paper_protection_obligations"))
        finally:
            store.close()

    def test_first_crossing_is_latched_once_per_robot_trade(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store)
            first, created = store.latch_paper_protection_obligation(
                trade_id="robot-trade-c1",
                protection_version=2,
                winning_leg="STOP",
                trigger_price=Decimal("98"),
                observed_exit_price=Decimal("97.9"),
                observed_quantity=Decimal("2.5"),
                market_event_id="BTCUSDT:10:20",
                source_generation=0,
                source_sequence=10,
                source_update_id=20,
                source_event_at_ms=1199,
                source_matching_engine_cts_ms=1198,
                observed_bid_price=Decimal("97.9"),
                observed_ask_price=Decimal("98.0"),
                source_received_at_ms=1200,
                latched_at_ms=1201,
            )
            later, created_later = store.latch_paper_protection_obligation(
                trade_id="robot-trade-c1",
                protection_version=2,
                winning_leg="TAKE",
                trigger_price=Decimal("104"),
                observed_exit_price=Decimal("104.5"),
                observed_quantity=Decimal("2.5"),
                market_event_id="BTCUSDT:11:21",
                source_generation=0,
                source_sequence=10,
                source_update_id=20,
                source_event_at_ms=1199,
                source_matching_engine_cts_ms=1198,
                observed_bid_price=Decimal("97.9"),
                observed_ask_price=Decimal("98.0"),
                source_received_at_ms=1202,
                latched_at_ms=1203,
            )

            self.assertTrue(created)
            self.assertFalse(created_later)
            self.assertEqual(later, first)
            self.assertEqual(first.winning_leg, "STOP")
            self.assertEqual(first.status, "TRIGGERED")
            self.assertEqual(first.trade_id, "robot-trade-c1")
            self.assertTrue(first.order_id.value.startswith("paper-protection-order-"))
            self.assertTrue(first.exec_id.value.startswith("paper-protection-exec-"))
        finally:
            store.close()

    def test_unresolved_obligation_survives_restart_with_stable_close_identity(self) -> None:
        store = SQLiteStore.open(self.db_path)
        self._open_trade(store)
        latched, _ = store.latch_paper_protection_obligation(
            trade_id="robot-trade-c1",
            protection_version=2,
            winning_leg="TAKE",
            trigger_price=Decimal("104"),
            observed_exit_price=Decimal("104.2"),
            observed_quantity=Decimal("2.5"),
            market_event_id="BTCUSDT:12:22",
            source_generation=0,
            source_sequence=12,
            source_update_id=22,
            source_event_at_ms=1299,
            source_matching_engine_cts_ms=1298,
            observed_bid_price=Decimal("104.2"),
            observed_ask_price=Decimal("104.3"),
            source_received_at_ms=1300,
            latched_at_ms=1301,
        )
        store.close()

        reopened = SQLiteStore.open(self.db_path)
        try:
            unresolved = reopened.load_unresolved_paper_protection_obligations(self.account)
            self.assertEqual(len(unresolved), 1)
            self.assertEqual(unresolved[0].obligation_id, latched.obligation_id)
            self.assertEqual(unresolved[0].order_id, latched.order_id)
            self.assertEqual(unresolved[0].exec_id, latched.exec_id)
            self.assertEqual(unresolved[0].market_event_id, "BTCUSDT:12:22")
            self.assertEqual(unresolved[0].source_generation, 0)
            self.assertEqual(unresolved[0].source_sequence, 12)
            self.assertEqual(unresolved[0].source_update_id, 22)
            self.assertEqual(unresolved[0].source_event_at_ms, 1299)
            self.assertEqual(unresolved[0].source_matching_engine_cts_ms, 1298)
            self.assertEqual(unresolved[0].source_received_at_ms, 1300)
            self.assertEqual(unresolved[0].observed_bid_price, Decimal("104.2"))
            self.assertEqual(unresolved[0].observed_ask_price, Decimal("104.3"))
            self.assertEqual(unresolved[0].observed_exit_price, Decimal("104.2"))
            self.assertEqual(unresolved[0].observed_quantity, Decimal("2.5"))
            self.assertEqual(unresolved[0].protection_version, 2)
            self.assertEqual(unresolved[0].winning_leg, "TAKE")
        finally:
            reopened.close()

    def test_get_paper_protection_obligation_for_trade(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store)
            self.assertIsNone(store.get_paper_protection_obligation_for_trade("robot-trade-c1"))

            latched, _ = store.latch_paper_protection_obligation(
                trade_id="robot-trade-c1",
                protection_version=1,
                winning_leg="STOP",
                trigger_price=Decimal("98"),
                observed_exit_price=Decimal("97.9"),
                observed_quantity=Decimal("2.5"),
                market_event_id="BTCUSDT:14:24",
                source_generation=0,
                source_sequence=10,
                source_update_id=20,
                source_event_at_ms=1199,
                source_matching_engine_cts_ms=1198,
                observed_bid_price=Decimal("97.9"),
                observed_ask_price=Decimal("98.0"),
                source_received_at_ms=1500,
                latched_at_ms=1501,
            )
            found = store.get_paper_protection_obligation_for_trade("robot-trade-c1")
            self.assertEqual(found, latched)
            self.assertIsNone(store.get_paper_protection_obligation_for_trade("no-such-trade"))
        finally:
            store.close()

    def test_create_robot_trade_persists_entry_attestation(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store, entry_quantity=Decimal("3.75"), entry_position_version=4)
            trade = store.get_robot_trade("robot-trade-c1")
            self.assertEqual(trade.entry_quantity, Decimal("3.75"))
            self.assertEqual(trade.entry_position_version, 4)
        finally:
            store.close()

    def test_create_robot_trade_rejects_invalid_attestation(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            with self.assertRaises(ValueError):
                self._open_trade(store, entry_quantity=Decimal("0"), entry_position_version=1)
        finally:
            store.close()
        store = SQLiteStore.open(self.db_path)
        try:
            with self.assertRaises(ValueError):
                self._open_trade(store, entry_quantity=Decimal("1"), entry_position_version=0)
        finally:
            store.close()

    def test_create_robot_trade_duplicate_with_different_attestation_fails_closed(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store, entry_quantity=Decimal("2.5"), entry_position_version=1)
            with self.assertRaises(DuplicateIdentity):
                store.create_robot_trade(
                    trade_id="robot-trade-c1",
                    trading_account_id=self.account,
                    candidate_id="c1",
                    symbol=Symbol("BTCUSDT"),
                    direction="LONG",
                    pattern="Falling Wedge",
                    source_timeframe="1",
                    signal_time_ms=1000,
                    entry_time_ms=1100,
                    entry_path="LIMIT",
                    actual_wv=Decimal("1"),
                    average_entry=Decimal("100"),
                    stop_price=Decimal("98"),
                    take_price=Decimal("104"),
                    entry_quantity=Decimal("999"),
                    entry_position_version=1,
                    created_at_ms=1100,
                )
        finally:
            store.close()

    def test_legacy_trade_has_null_attestation(self) -> None:
        """A pre-v18 (v17) row migrated forward has no attestation at all --
        the exact state D2.3 dispatch must treat as missing and fail closed."""
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store)
            self._make_trade_legacy(store, "robot-trade-c1")
            trade = store.get_robot_trade("robot-trade-c1")
            self.assertIsNone(trade.entry_quantity)
            self.assertIsNone(trade.entry_position_version)
        finally:
            store.close()

    def test_obligation_transition_is_optimistic_and_idempotent(self) -> None:
        store = SQLiteStore.open(self.db_path)
        try:
            self._open_trade(store)
            latched, _ = store.latch_paper_protection_obligation(
                trade_id="robot-trade-c1",
                protection_version=2,
                winning_leg="STOP",
                trigger_price=Decimal("98"),
                observed_exit_price=Decimal("97.9"),
                observed_quantity=Decimal("2.5"),
                market_event_id="BTCUSDT:13:23",
                source_generation=0,
                source_sequence=10,
                source_update_id=20,
                source_event_at_ms=1199,
                source_matching_engine_cts_ms=1198,
                observed_bid_price=Decimal("97.9"),
                observed_ask_price=Decimal("98.0"),
                source_received_at_ms=1400,
                latched_at_ms=1401,
            )
            dispatching = store.transition_paper_protection_obligation(
                latched.obligation_id,
                expected_status="TRIGGERED",
                next_status="DISPATCHING",
                expected_version=latched.version,
                updated_at_ms=1410,
            )
            self.assertEqual(dispatching.status, "DISPATCHING")
            self.assertEqual(dispatching.version, latched.version + 1)

            with self.assertRaises(ConcurrentUpdate):
                store.transition_paper_protection_obligation(
                    latched.obligation_id,
                    expected_status="TRIGGERED",
                    next_status="DISPATCHING",
                    expected_version=latched.version,
                    updated_at_ms=1411,
                )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
