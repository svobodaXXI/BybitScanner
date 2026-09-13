from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import (
    ConcurrentUpdate,
    SQLiteStore,
)


class PaperProtectionObligationPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "paper-protection.sqlite3"
        self.account = TradingAccountId("paper")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _open_trade(self, store: SQLiteStore, *, trade_id: str = "robot-trade-c1") -> None:
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
            created_at_ms=1100,
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
        finally:
            reopened.close()

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
