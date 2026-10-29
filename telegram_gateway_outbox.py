"""Independent SQLite outbox for Gateway text notifications.

PAPER trading DB is never read or modified. Unknown remote outcomes are held
for operator reconciliation; blindly replaying them could duplicate alerts.
"""
from __future__ import annotations

import os
import json
import sqlite3
import time
from pathlib import Path


class OutboxError(RuntimeError):
    pass


def _path() -> Path:
    raw = os.environ.get("BYBITSCANNER_TELEGRAM_OUTBOX_DB", "").strip()
    if not raw:
        raise OutboxError("Telegram outbox path is not configured")
    path = Path(raw)
    if not path.is_absolute() or path == Path("/var/lib/bybitscanner/paper_runtime.sqlite3"):
        raise OutboxError("Telegram outbox must be an independent absolute DB path")
    return path


def _connect():
    path = _path()
    if not path.parent.is_dir():
        raise OutboxError("Telegram outbox directory does not exist")
    connection = sqlite3.connect(str(path), timeout=5)
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS telegram_outbox (
        event_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        text TEXT NOT NULL,
        reply_markup TEXT,
        status TEXT NOT NULL CHECK(status IN
            ('PENDING','IN_FLIGHT','ACCEPTED','UNKNOWN','REJECTED')),
        created_at_ms INTEGER NOT NULL,
        updated_at_ms INTEGER NOT NULL,
        telegram_message_id TEXT
    )""")
    return connection


def enqueue(event_id: str, chat_id: str, message: str, reply_markup=None) -> None:
    now = int(time.time() * 1000)
    with _connect() as db:
        db.execute(
            "INSERT INTO telegram_outbox "
            "(event_id,chat_id,text,reply_markup,status,created_at_ms,updated_at_ms) "
            "VALUES (?,?,?, ?, 'PENDING',?,?)",
            (event_id, str(chat_id), message,
             json.dumps(reply_markup, ensure_ascii=False) if reply_markup is not None else None,
             now, now),
        )


def mark(event_id: str, status: str, message_id=None) -> None:
    if status not in {"IN_FLIGHT", "ACCEPTED", "UNKNOWN", "REJECTED"}:
        raise OutboxError("Invalid outbox transition")
    with _connect() as db:
        now = int(time.time() * 1000)
        cursor = db.execute(
            "UPDATE telegram_outbox SET status=?, updated_at_ms=?, "
            "telegram_message_id=? WHERE event_id=?",
            (status, now, None if message_id is None else str(message_id), event_id),
        )
        if cursor.rowcount != 1:
            raise OutboxError("Missing outbox event")


def counts() -> dict[str, int]:
    with _connect() as db:
        rows = db.execute(
            "SELECT status, COUNT(*) FROM telegram_outbox GROUP BY status"
        ).fetchall()
    return dict(rows)
