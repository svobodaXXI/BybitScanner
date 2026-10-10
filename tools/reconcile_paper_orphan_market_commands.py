"""Close the two orphaned OGUSDT PAPER Market commands (owner-run, stopped runtime only).

Usage:
  python -m tools.reconcile_paper_orphan_market_commands \
      --database paper_runtime.sqlite3 --backup BACKUP.sqlite3 --backup-sha256 HEX [--apply]

Without ``--apply`` it only proves and reports (DRY-RUN). Every guard fails closed:
the PAPER backend and the Telegram worker must not answer, the database must
already be on the current schema (it is never migrated here), and the backup must
match its SHA-256, pass integrity_check and still hold both commands in their
pre-change SUBMITTING state. See terminal.application.paper_orphan_market_commands.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from terminal.application.paper_orphan_market_commands import (
    ALLOWED_ORPHAN_COMMANDS, OrphanEvidenceError, fail_orphan_paper_market_commands,
    prove_orphan_paper_market_command,
)
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import SQLiteStore

DEFAULT_BACKEND_HEALTH = "http://127.0.0.1:8765/api/health"
DEFAULT_TELEGRAM_HEALTH = "http://127.0.0.1:8766/health"
EXIT_OK, EXIT_BLOCKED, EXIT_REFUSED, EXIT_USAGE = 0, 2, 3, 64


def probe_listening(url: str) -> bool:
    """True unless the endpoint provably refuses the connection (fail closed)."""
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except urllib.error.HTTPError:
        return True
    except urllib.error.URLError as error:
        return not isinstance(error.reason, ConnectionRefusedError)
    except ConnectionRefusedError:
        return False
    except Exception:
        return True


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_database(path: Path) -> str | None:
    if not path.is_file():
        return f"database not found: {path}"
    connection = _read_only(path)
    try:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            return f"database schema is v{version}, expected v{SCHEMA_VERSION}; it is not migrated here"
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return "database quick_check failed"
    finally:
        connection.close()
    return None


def _check_backup(database: Path, backup: Path, expected_sha256: str) -> str | None:
    if not backup.is_file():
        return f"backup not found: {backup}"
    if backup.resolve() == database.resolve():
        return "backup is the database itself"
    if _sha256(backup) != expected_sha256.strip().lower():
        return "backup SHA-256 does not match"
    connection = _read_only(backup)
    try:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return "backup integrity_check failed"
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
            return "backup is not on the current schema"
        rows = dict(
            ((command_id, (state, int(version)))
             for command_id, state, version in connection.execute(
                 "SELECT command_id, current_state, version FROM trading_commands "
                 f"WHERE command_id IN ({','.join('?' * len(ALLOWED_ORPHAN_COMMANDS))})",
                 tuple(ALLOWED_ORPHAN_COMMANDS)))
        )
    finally:
        connection.close()
    if rows != {command_id: ("submitting", 2) for command_id in ALLOWED_ORPHAN_COMMANDS}:
        return "backup does not hold both commands in their pre-change SUBMITTING state"
    return None


def main(
    argv: list[str] | None = None, *,
    probe_listening: Callable[[str], bool] = probe_listening,
    out: Callable[[str], None] = lambda line: print(line, flush=True),
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
) -> int:
    parser = argparse.ArgumentParser(prog="reconcile_paper_orphan_market_commands")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--backup-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backend-health", default=DEFAULT_BACKEND_HEALTH)
    parser.add_argument("--telegram-health", default=DEFAULT_TELEGRAM_HEALTH)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_USAGE

    for name, url in (("PAPER backend", args.backend_health),
                      ("Telegram worker", args.telegram_health)):
        if probe_listening(url):
            out(f"BLOCKED: runtime is not fully stopped ({name} answers at {url})")
            return EXIT_BLOCKED
    for problem in (_check_database(args.database),
                    _check_backup(args.database, args.backup, args.backup_sha256)):
        if problem is not None:
            out(f"BLOCKED: {problem}")
            return EXIT_BLOCKED

    store = SQLiteStore.open(args.database)
    try:
        ids = tuple(ALLOWED_ORPHAN_COMMANDS)
        try:
            proofs = [prove_orphan_paper_market_command(store, command_id) for command_id in ids]
            for proof in proofs:
                out(f"PROVEN: {proof.command_id} {proof.symbol} link={proof.order_link_id} "
                    f"no {proof.exec_id} / {proof.order_id}; version={proof.version}"
                    + (" (already FAILED by this reconciliation)" if proof.already_failed else ""))
            if not args.apply:
                out("DRY-RUN: no changes written; re-run with --apply")
                return EXIT_OK
            results = fail_orphan_paper_market_commands(store, ids, occurred_at_ms=clock_ms())
        except OrphanEvidenceError as error:
            out(f"REFUSED: {error}")
            return EXIT_REFUSED
        for record in results:
            out(f"FAILED: {record.command_id.value} state={record.current_state.value} "
                f"version={record.version}")
        return EXIT_OK
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
