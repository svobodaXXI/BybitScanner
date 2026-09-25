"""One focused shared OPEN trade entry attestation persistence check."""
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from terminal.domain.models import Symbol, TradingAccountId
from terminal.persistence.sqlite_store import (
    SQLiteStore, ImmutableExecutionConflict, PersistenceError,
)


class RobotEntryAttestationTests(unittest.TestCase):
    def test_refresh_open_trade_entry_attestation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteStore.open(Path(directory) / "paper.sqlite3")
            try:
                account = TradingAccountId("paper")
                symbol = Symbol("BTCUSDT")
                store.create_robot_candidate(
                    candidate_id="candidate-1", trading_account_id=account, symbol=symbol,
                    status="APPROVED", signal_snapshot={"symbol": symbol.value},
                    approved_at_ms=1000, updated_at_ms=1000,
                )
                original, _ = store.create_robot_trade(
                    trade_id="trade-1", trading_account_id=account,
                    candidate_id="candidate-1", symbol=symbol, direction="LONG",
                    pattern="Falling Wedge", source_timeframe="1",
                    signal_time_ms=900, entry_time_ms=1500, entry_path="LIMIT",
                    actual_wv=Decimal("0.8"), average_entry=Decimal("100"),
                    stop_price=Decimal("98"), take_price=Decimal("106"),
                    entry_quantity=Decimal("1"), entry_position_version=4,
                    created_at_ms=1500,
                )
                args = dict(trading_account_id=account, candidate_id="candidate-1",
                            symbol=symbol, average_entry=Decimal("95"),
                            entry_quantity=Decimal("2"), entry_position_version=5,
                            updated_at_ms=1600)
                changed, did_change = store.refresh_open_robot_trade_entry_attestation(
                    "trade-1", **args)
                self.assertTrue(did_change)
                self.assertEqual(changed, replace(original, average_entry=Decimal("95"),
                    entry_quantity=Decimal("2"), entry_position_version=5,
                    updated_at_ms=1600, version=original.version + 1))
                self.assertEqual(store.get_robot_candidate("candidate-1").status, "OPEN")
                same, did_change = store.refresh_open_robot_trade_entry_attestation(
                    "trade-1", **{**args, "updated_at_ms": 1700})
                self.assertFalse(did_change)
                self.assertEqual(same, changed)
                for overrides in (
                    {"entry_quantity": Decimal("1")},
                    {"entry_position_version": 4},
                    {"average_entry": Decimal("94"), "entry_position_version": 5},
                ):
                    with self.subTest(overrides=overrides), self.assertRaises(ImmutableExecutionConflict):
                        store.refresh_open_robot_trade_entry_attestation(
                            "trade-1", **{**args, **overrides})
                for overrides in (
                    {"trading_account_id": TradingAccountId("foreign")},
                    {"candidate_id": "foreign"},
                    {"symbol": Symbol("ETHUSDT")},
                ):
                    with self.subTest(identity=overrides), self.assertRaises(PersistenceError):
                        store.refresh_open_robot_trade_entry_attestation(
                            "trade-1", **{**args, **overrides})
                self.assertEqual(store.get_robot_trade("trade-1"), changed)
            finally:
                store.close()
