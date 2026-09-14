from __future__ import annotations

import hashlib
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from terminal.statistics.reader import (
    RobotStatisticsReadError,
    RobotStatisticsReader,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create_fixture_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE robot_candidates (
                candidate_id TEXT PRIMARY KEY,
                trading_account_id TEXT NOT NULL
            );

            CREATE TABLE robot_trades (
                trade_id TEXT PRIMARY KEY,
                trading_account_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                pattern TEXT NOT NULL,
                source_timeframe TEXT NOT NULL,
                signal_time_ms INTEGER NOT NULL,
                entry_time_ms INTEGER NOT NULL,
                entry_path TEXT NOT NULL,
                actual_wv TEXT NOT NULL,
                average_entry TEXT NOT NULL,
                entry_quantity TEXT,
                entry_position_version INTEGER,
                stop_price TEXT NOT NULL,
                take_price TEXT NOT NULL,
                exit_time_ms INTEGER,
                exit_price TEXT,
                exit_reason TEXT,
                realized_pnl_usdt TEXT,
                realized_pnl_pct TEXT,
                fees_costs_usdt TEXT
            );
            """
        )
        connection.commit()
    finally:
        connection.close()


def _insert_candidate(
    connection: sqlite3.Connection,
    *,
    candidate_id: str,
    account_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO robot_candidates (
            candidate_id,
            trading_account_id
        ) VALUES (?, ?)
        """,
        (candidate_id, account_id),
    )


def _insert_trade(
    connection: sqlite3.Connection,
    *,
    trade_id: str,
    candidate_id: str,
    account_id: str,
    symbol: str,
    exit_time_ms: int | None,
    pnl: str | None,
    fee: str | None = None,
) -> None:
    closed = exit_time_ms is not None
    connection.execute(
        """
        INSERT INTO robot_trades (
            trade_id,
            trading_account_id,
            candidate_id,
            symbol,
            direction,
            pattern,
            source_timeframe,
            signal_time_ms,
            entry_time_ms,
            entry_path,
            actual_wv,
            average_entry,
            entry_quantity,
            entry_position_version,
            stop_price,
            take_price,
            exit_time_ms,
            exit_price,
            exit_reason,
            realized_pnl_usdt,
            realized_pnl_pct,
            fees_costs_usdt
        ) VALUES (
            ?, ?, ?, ?, 'LONG', 'FALLING_WEDGE', '1',
            1000, 2000, 'LIMIT',
            '0.1', '10', '5', 7, '9', '12',
            ?, ?, ?, ?, ?, ?
        )
        """,
        (
            trade_id,
            account_id,
            candidate_id,
            symbol,
            exit_time_ms,
            "11" if closed else None,
            "TAKE" if closed else None,
            pnl,
            "2.5" if closed else None,
            fee,
        ),
    )


class RobotStatisticsReaderTests(unittest.TestCase):
    def test_reads_only_completed_trades_for_requested_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "robot.sqlite3"
            _create_fixture_database(database_path)

            connection = sqlite3.connect(database_path)
            try:
                _insert_candidate(
                    connection,
                    candidate_id="candidate-a-1",
                    account_id="account-a",
                )
                _insert_candidate(
                    connection,
                    candidate_id="candidate-a-open",
                    account_id="account-a",
                )
                _insert_candidate(
                    connection,
                    candidate_id="candidate-b-1",
                    account_id="account-b",
                )

                _insert_trade(
                    connection,
                    trade_id="trade-a-1",
                    candidate_id="candidate-a-1",
                    account_id="account-a",
                    symbol="BTCUSDT",
                    exit_time_ms=5000,
                    pnl="12.5",
                    fee="0.5",
                )
                _insert_trade(
                    connection,
                    trade_id="trade-a-open",
                    candidate_id="candidate-a-open",
                    account_id="account-a",
                    symbol="ETHUSDT",
                    exit_time_ms=None,
                    pnl=None,
                )
                _insert_trade(
                    connection,
                    trade_id="trade-b-1",
                    candidate_id="candidate-b-1",
                    account_id="account-b",
                    symbol="SOLUSDT",
                    exit_time_ms=6000,
                    pnl="20",
                )
                connection.commit()
            finally:
                connection.close()

            trades = RobotStatisticsReader(
                database_path
            ).load_completed_trades(
                trading_account_id="account-a"
            )

            self.assertEqual(len(trades), 1)
            trade = trades[0]

            self.assertEqual(trade.trade_id, "trade-a-1")
            self.assertEqual(trade.trading_account_id, "account-a")
            self.assertEqual(trade.symbol, "BTCUSDT")
            self.assertEqual(trade.realized_pnl_usdt, Decimal("12.5"))
            self.assertEqual(trade.fees_costs_usdt, Decimal("0.5"))
            self.assertEqual(trade.entry_quantity, Decimal("5"))
            self.assertEqual(trade.entry_notional_usdt, Decimal("50"))

    def test_orders_completed_trades_by_exit_time_then_trade_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "robot.sqlite3"
            _create_fixture_database(database_path)

            connection = sqlite3.connect(database_path)
            try:
                for suffix in ("b", "a", "c"):
                    candidate_id = f"candidate-{suffix}"
                    _insert_candidate(
                        connection,
                        candidate_id=candidate_id,
                        account_id="account-a",
                    )
                    _insert_trade(
                        connection,
                        trade_id=f"trade-{suffix}",
                        candidate_id=candidate_id,
                        account_id="account-a",
                        symbol="BTCUSDT",
                        exit_time_ms=5000 if suffix != "c" else 6000,
                        pnl="1",
                    )
                connection.commit()
            finally:
                connection.close()

            trades = RobotStatisticsReader(
                database_path
            ).load_completed_trades(
                trading_account_id="account-a"
            )

            self.assertEqual(
                [trade.trade_id for trade in trades],
                ["trade-a", "trade-b", "trade-c"],
            )

    def test_read_does_not_modify_database_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "robot.sqlite3"
            _create_fixture_database(database_path)

            connection = sqlite3.connect(database_path)
            try:
                _insert_candidate(
                    connection,
                    candidate_id="candidate-a",
                    account_id="account-a",
                )
                _insert_trade(
                    connection,
                    trade_id="trade-a",
                    candidate_id="candidate-a",
                    account_id="account-a",
                    symbol="BTCUSDT",
                    exit_time_ms=5000,
                    pnl="1",
                )
                connection.commit()
            finally:
                connection.close()

            before = _sha256(database_path)

            RobotStatisticsReader(
                database_path
            ).load_completed_trades(
                trading_account_id="account-a"
            )

            after = _sha256(database_path)
            self.assertEqual(after, before)

    def test_missing_database_fails_closed_without_creating_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "missing.sqlite3"

            with self.assertRaises(RobotStatisticsReadError):
                RobotStatisticsReader(
                    database_path
                ).load_completed_trades(
                    trading_account_id="account-a"
                )

            self.assertFalse(database_path.exists())

    def test_incompatible_schema_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "robot.sqlite3"

            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE robot_candidates (
                        candidate_id TEXT PRIMARY KEY,
                        trading_account_id TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE robot_trades (
                        trade_id TEXT PRIMARY KEY
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(
                RobotStatisticsReadError,
                "robot_trades missing required columns",
            ):
                RobotStatisticsReader(
                    database_path
                ).load_completed_trades(
                    trading_account_id="account-a"
                )

    def test_non_text_decimal_storage_fails_closed(self) -> None:
        from terminal.statistics.reader import _load_decimal

        with self.assertRaisesRegex(
            RobotStatisticsReadError,
            "canonical Decimal text",
        ):
            _load_decimal(1.25, field="realized_pnl_usdt")
    def test_orphan_completed_trade_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "robot.sqlite3"
            _create_fixture_database(database_path)

            connection = sqlite3.connect(database_path)
            try:
                _insert_trade(
                    connection,
                    trade_id="orphan-trade",
                    candidate_id="missing-candidate",
                    account_id="account-a",
                    symbol="BTCUSDT",
                    exit_time_ms=5000,
                    pnl="1",
                )
                connection.commit()
            finally:
                connection.close()

            with self.assertRaisesRegex(
                RobotStatisticsReadError,
                "missing or account-mismatched candidate linkage",
            ):
                RobotStatisticsReader(
                    database_path
                ).load_completed_trades(
                    trading_account_id="account-a"
                )
    def test_empty_account_id_is_rejected_before_database_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "does-not-exist.sqlite3"

            with self.assertRaises(ValueError):
                RobotStatisticsReader(
                    database_path
                ).load_completed_trades(
                    trading_account_id="   "
                )

            self.assertFalse(database_path.exists())


if __name__ == "__main__":
    unittest.main()