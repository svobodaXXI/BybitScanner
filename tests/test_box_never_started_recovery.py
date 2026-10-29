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


if __name__ == "__main__":
    unittest.main()
