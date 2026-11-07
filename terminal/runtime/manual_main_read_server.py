"""Loopback-only, read-only HTTP boundary for independently owned Bybit MAIN accounts.

Access is intended exclusively through the existing Telegram-authenticated Nginx
origin. No paper runtime, Robot, order execution, credential ingress or service
start is added by importing this module. POST /refresh performs exchange READS
and updates only the separate MAIN snapshot store.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from terminal.application.manual_main_accounts import ManualMainAccounts
from terminal.persistence.credential_store import create_credential_store
from terminal.persistence.live_account_store import LiveAccountProjectionStore

HOST = "127.0.0.1"
PORT = 8771
PREFIX = "/api/manual-main"


def checked_main_state_dir(value: str) -> Path:
    """No implicit state creation or fallback to any PAPER DB directory."""
    if not isinstance(value, str) or not value:
        raise RuntimeError("manual_main_state_dir_required")
    directory = Path(value)
    if not directory.is_absolute() or not directory.is_dir() or directory.is_symlink():
        raise RuntimeError("manual_main_state_dir_invalid")
    if directory.stat().st_mode & 0o077:
        raise RuntimeError("manual_main_state_dir_not_private")
    paper_db = os.environ.get("BYBITSCANNER_PAPER_DB", "").strip()
    if paper_db and directory.resolve() == Path(paper_db).resolve().parent:
        raise RuntimeError("manual_main_paper_state_collision")
    return directory


class MainReadHandler(BaseHTTPRequestHandler):
    """Exact allowlisted paths only; no trading or account-key POST endpoints."""
    accounts: ManualMainAccounts

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _account_path(path: str, suffix: str) -> str | None:
        marker = PREFIX + "/accounts/"
        if not path.startswith(marker) or not path.endswith(suffix):
            return None
        encoded = path[len(marker):-len(suffix)]
        account_id = unquote(encoded)
        if (not account_id.startswith("bybit-") or len(account_id) > 64
                or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in account_id)):
            return None
        return account_id

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == PREFIX + "/health":
            self._json(200, {"ok": True, "component": "manual_main_read", "trading_enabled": False})
        elif path == PREFIX + "/accounts":
            self._json(200, {"ok": True, **self.accounts.catalog()})
        elif (account_id := self._account_path(path, "/summary")) is not None:
            try:
                summary = self.accounts.summary(account_id)
            except LookupError:
                self._json(404, {"ok": False, "error": "account_not_found"})
                return
            self._json(200, {"ok": True, "summary": summary})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if (account_id := self._account_path(path, "/refresh")) is None:
            self._json(405, {"ok": False, "error": "read_only_gateway"})
            return
        # No request payload is read; no credential ingress or order mutation.
        if self.headers.get("Content-Length", "0") != "0" or self.headers.get("Transfer-Encoding"):
            self._json(400, {"ok": False, "error": "unexpected_payload"})
            return
        try:
            summary = self.accounts.refresh(account_id)
        except LookupError:
            self._json(404, {"ok": False, "error": "account_not_found"})
            return
        except Exception:
            self._json(503, {"ok": False, "error": "main_account_refresh_unavailable"})
            return
        self._json(200, {"ok": True, "summary": summary})

    def log_message(self, format: str, *args) -> None:
        # Never put account IDs, query strings or credentials into access logs.
        pass


def serve(accounts: ManualMainAccounts, *, port: int = PORT) -> None:
    """Intentionally loopback-bound; Nginx owner auth is the public boundary."""
    handler = type("BoundManualMainReadHandler", (MainReadHandler,), {"accounts": accounts})
    server = ThreadingHTTPServer((HOST, port), handler)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    state_dir = checked_main_state_dir(os.environ.get("BYBITSCANNER_MAIN_STATE_DIR", ""))
    # No PAPER database, port, credentials or runtime are ever opened here.
    accounts = ManualMainAccounts(
        create_credential_store(state_dir / "main.credentials.systemd"),
        LiveAccountProjectionStore(state_dir / "main.snapshots.sqlite3"),
    )
    try:
        serve(accounts)
    finally:
        accounts.close()


if __name__ == "__main__":
    main()
