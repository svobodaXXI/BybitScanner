"""Owner-attested closure of four stale LIVE Limit commands (owner-run, stopped runtime only).

Usage:
  python -m tools.attest_legacy_live_limit_commands \
      --database paper_runtime.sqlite3 --backup BACKUP.sqlite3 --backup-sha256 HEX \
      [--apply --owner-statement I-ATTEST-LEGACY-LIVE-LIMITS-CANCELLED-2026-10-18]

Without ``--apply`` it only proves and reports (DRY-RUN). Every guard fails closed:
the PAPER backend and the Telegram worker must not answer, the database must already
be on the current schema (never migrated here), and the backup must match its SHA-256,
pass integrity_check and still hold all four commands in their pre-change ``open``
state. It never contacts an exchange. See
terminal.application.legacy_live_limit_owner_attestation.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from pathlib import Path
from typing import Callable

from terminal.application.legacy_live_limit_owner_attestation import (
    ALLOWED_LEGACY_LIVE_COMMANDS, LegacyLiveAttestationError,
    attest_legacy_live_limit_commands, prove_legacy_live_limit_command,
)
from terminal.persistence.schema import SCHEMA_VERSION
from terminal.persistence.sqlite_store import SQLiteStore
from tools.reconcile_celo_orphans import (
    DEFAULT_BACKEND_HEALTH, DEFAULT_TELEGRAM_HEALTH, EXIT_BLOCKED, EXIT_OK, EXIT_REFUSED,
    EXIT_USAGE, _check_database, _read_only, _sha256, probe_listening,
)

OWNER_STATEMENT = "I-ATTEST-LEGACY-LIVE-LIMITS-CANCELLED-2026-10-18"


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
            (command_id, (state, int(version)))
            for command_id, state, version in connection.execute(
                "SELECT command_id, current_state, version FROM trading_commands "
                f"WHERE command_id IN ({','.join('?' * len(ALLOWED_LEGACY_LIVE_COMMANDS))})",
                tuple(ALLOWED_LEGACY_LIVE_COMMANDS))
        )
    finally:
        connection.close()
    if rows != {command_id: ("open", 4) for command_id in ALLOWED_LEGACY_LIVE_COMMANDS}:
        return "backup does not hold all four commands in their pre-change open state"
    return None


def main(
    argv: list[str] | None = None, *,
    probe_listening: Callable[[str], bool] = probe_listening,
    out: Callable[[str], None] = lambda line: print(line, flush=True),
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000),
) -> int:
    parser = argparse.ArgumentParser(prog="attest_legacy_live_limit_commands")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--backup", required=True, type=Path)
    parser.add_argument("--backup-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--owner-statement", default="")
    parser.add_argument("--backend-health", default=DEFAULT_BACKEND_HEALTH)
    parser.add_argument("--telegram-health", default=DEFAULT_TELEGRAM_HEALTH)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_USAGE
    if args.apply and args.owner_statement != OWNER_STATEMENT:
        out("BLOCKED: --apply requires the exact --owner-statement phrase")
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

    # Proof mode opens strictly read-only; apply reuses canonical store durability.
    if args.apply:
        store = SQLiteStore.open(args.database)
    else:
        connection = _read_only(args.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        store = SQLiteStore(connection, args.database, 5000)
    try:
        ids = tuple(ALLOWED_LEGACY_LIVE_COMMANDS)
        try:
            for command_id in ids:
                proof = prove_legacy_live_limit_command(store, command_id)
                out(f"PROVEN: {proof.command_id} {proof.session} order={proof.exchange_order_id} "
                    f"version={proof.version}"
                    + (" (already attested)" if proof.already_attested else ""))
            if not args.apply:
                out("DRY-RUN: no changes written; re-run with --apply and --owner-statement")
                return EXIT_OK
            results = attest_legacy_live_limit_commands(store, ids, occurred_at_ms=clock_ms())
        except LegacyLiveAttestationError as error:
            out(f"REFUSED: {error}")
            return EXIT_REFUSED
        for record in results:
            out(f"ATTESTED: {record.command_id.value} state={record.current_state.value} "
                f"version={record.version}")
        return EXIT_OK
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
