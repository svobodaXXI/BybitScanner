"""Focused AXTI proof on isolated PAPER SQLite, current schema."""
import tempfile
import unittest
from pathlib import Path

from terminal.persistence.sqlite_store import SQLiteStore
from tests.test_box_plan_persistence import snapshot


class NeverStartedRecoveryTests(unittest.TestCase):
    def test_pending_market_command_blocks_never_started_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore.open(Path(tmp) / "paper.sqlite3")
            try:
                plan, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
                self.assertTrue(store.prove_box_never_started_flat(plan.candidate_id))
                with store._transaction():
                    store._connection.execute(
                        """INSERT INTO trading_commands (
                            command_id, order_link_id, trading_account_id, category, symbol,
                            position_idx, command_kind, side, requested_notional, normalized_price,
                            normalized_quantity, origin, controller, current_state, version,
                            exchange_order_id, created_at_ms, updated_at_ms)
                        VALUES ('pending', 'pending-link', 'paper', 'linear', 'BTCUSDT', 0,
                                'create_market', 'Buy', '10', NULL, '1', 'terminal_manual',
                                'manual', 'submitting', 1, NULL, 100, 100)"""
                    )
                self.assertFalse(store.prove_box_never_started_flat(plan.candidate_id))
            finally:
                store.close()

    def test_historical_round_trip_before_plan_does_not_own_new_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore.open(Path(tmp) / "paper.sqlite3")
            try:
                plan, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
                with store._transaction():
                    store._connection.executemany(
                        """INSERT INTO executions (
                               trading_account_id, category, exec_id, order_id, symbol,
                               side, price, quantity, fee, exchange_timestamp_ms)
                           VALUES ('paper', 'linear', ?, ?, 'BTCUSDT', ?, '90', '1', '0', ?)""",
                        (
                            ("historical-entry", "historical-entry-order", "Buy", 1000),
                            ("historical-exit", "historical-exit-order", "Sell", 2000),
                        ),
                    )
                    store._connection.execute(
                        """INSERT INTO position_projections (
                               trading_account_id, category, symbol, position_idx, side,
                               quantity, average_entry, realized_pnl, accumulated_fee,
                               engaged_notional, sync_state, version, updated_at_ms)
                           VALUES ('paper', 'linear', 'BTCUSDT', 0, 'Flat',
                                   '0', NULL, '0', '0', '0', 'synced', 2, 2000)"""
                    )
                self.assertTrue(store.prove_box_never_started_flat(plan.candidate_id))
            finally:
                store.close()

    def test_fill_from_plan_lifetime_blocks_never_started_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteStore.open(Path(tmp) / "paper.sqlite3")
            try:
                plan, _ = store.save_box_plan_only(snapshot=snapshot(), created_at_ms=3001)
                with store._transaction():
                    store._connection.execute(
                        """INSERT INTO executions (
                               trading_account_id, category, exec_id, order_id, symbol,
                               side, price, quantity, fee, exchange_timestamp_ms)
                           VALUES ('paper', 'linear', 'contemporary', 'contemporary-order',
                                   'BTCUSDT', 'Buy', '90', '1', '0', 3001)"""
                    )
                self.assertFalse(store.prove_box_never_started_flat(plan.candidate_id))
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
