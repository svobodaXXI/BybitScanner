"""Separate atomic SQLite projection store for normalized LIVE account snapshots."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path


class LiveAccountStoreError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LiveAccountSnapshot:
    account_id: str
    environment: str
    read_only: bool
    refresh_generation: int
    wallet_balance_usdt: Decimal
    total_equity_usdt: Decimal
    available_balance_usdt: Decimal
    exchange_time_ms: int | None
    positions: tuple[dict[str, object], ...]
    orders: tuple[dict[str, object], ...]
    updated_at_ms: int

    def transport(self, *, status: str) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "environment": self.environment,
            "status": status,
            "refresh_generation": self.refresh_generation,
            "wallet_balance_usdt": str(self.wallet_balance_usdt),
            "total_equity_usdt": str(self.total_equity_usdt),
            "available_balance_usdt": str(self.available_balance_usdt),
            "exchange_time_ms": self.exchange_time_ms,
            "position_count": len(self.positions),
            "order_count": len(self.orders),
            "positions": list(self.positions),
            "orders": list(self.orders),
            "updated_at_ms": self.updated_at_ms,
        }


class LiveAccountProjectionStore:
    def __init__(self, path: Path) -> None:
        try:
            self._connection = sqlite3.connect(path)
            self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute("""
                CREATE TABLE IF NOT EXISTS live_account_snapshots (
                    account_id TEXT PRIMARY KEY,
                    environment TEXT NOT NULL,
                    read_only INTEGER NOT NULL,
                    refresh_generation INTEGER NOT NULL,
                    wallet_balance_usdt TEXT NOT NULL,
                    total_equity_usdt TEXT NOT NULL,
                    available_balance_usdt TEXT NOT NULL,
                    exchange_time_ms INTEGER,
                    positions_json TEXT NOT NULL,
                    orders_json TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    CHECK (refresh_generation >= 1),
                    CHECK (read_only IN (0, 1))
                ) WITHOUT ROWID
            """)
            self._connection.commit()
        except (sqlite3.Error, OSError) as exc:
            raise LiveAccountStoreError("live_account_store_unavailable") from exc

    def close(self) -> None:
        self._connection.close()

    def get(self, account_id: str) -> LiveAccountSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM live_account_snapshots WHERE account_id=?", (account_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return LiveAccountSnapshot(
                row[0], row[1], bool(row[2]), int(row[3]), Decimal(row[4]),
                Decimal(row[5]), Decimal(row[6]), row[7],
                tuple(json.loads(row[8])), tuple(json.loads(row[9])), int(row[10]),
            )
        except Exception as exc:
            raise LiveAccountStoreError("live_account_snapshot_corrupt") from exc

    def publish(self, snapshot: LiveAccountSnapshot) -> None:
        try:
            with self._connection:
                cursor = self._connection.execute("""
                    INSERT INTO live_account_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(account_id) DO UPDATE SET
                      environment=excluded.environment, read_only=excluded.read_only,
                      refresh_generation=excluded.refresh_generation,
                      wallet_balance_usdt=excluded.wallet_balance_usdt,
                      total_equity_usdt=excluded.total_equity_usdt,
                      available_balance_usdt=excluded.available_balance_usdt,
                      exchange_time_ms=excluded.exchange_time_ms,
                      positions_json=excluded.positions_json, orders_json=excluded.orders_json,
                      updated_at_ms=excluded.updated_at_ms
                    WHERE excluded.refresh_generation > live_account_snapshots.refresh_generation
                """, (
                    snapshot.account_id, snapshot.environment, int(snapshot.read_only),
                    snapshot.refresh_generation, str(snapshot.wallet_balance_usdt),
                    str(snapshot.total_equity_usdt), str(snapshot.available_balance_usdt),
                    snapshot.exchange_time_ms,
                    json.dumps(snapshot.positions, separators=(",", ":")),
                    json.dumps(snapshot.orders, separators=(",", ":")), snapshot.updated_at_ms,
                ))
                if cursor.rowcount != 1:
                    raise LiveAccountStoreError("stale_live_account_snapshot")
        except LiveAccountStoreError:
            raise
        except (sqlite3.Error, TypeError, ValueError) as exc:
            raise LiveAccountStoreError("live_account_snapshot_write_failed") from exc
