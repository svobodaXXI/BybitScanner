"""Loopback-only, independently owned Bybit MAIN HTTP boundary.

Access is intended exclusively through the existing Telegram-authenticated Nginx
origin. No PAPER runtime or Robot is imported. Manual trading is separately gated, off by default.
The only credential ingress is a same-origin MAIN provisioning POST. POST /refresh performs exchange READS
and updates only the separate MAIN snapshot store.
"""
from __future__ import annotations

import json
import os
from terminal.exchange.bybit_account_validation import AccountValidationError
from terminal.persistence.credential_store import CredentialStoreError
from terminal.application.manual_main_accounts import ManualMainAccountError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from terminal.application.manual_main_accounts import ManualMainAccounts
from terminal.application.manual_main_trading import (
    ManualMainTrader, ManualMainTradeLedger, ManualMainTradeBlocked, enabled_from_environment,
)
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
    """Only owner-authenticated MAIN provisioning and reads, no order execution."""
    accounts: ManualMainAccounts
    trader: ManualMainTrader | None = None

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
            self._json(200, {"ok": True, "component": "manual_main_read",
                             "trading_enabled": bool(self.trader and self.trader.enabled)})
        elif path == PREFIX + "/accounts":
            self._json(200, {"ok": True, **self.accounts.catalog()})
        elif (account_id := self._account_path(path, "/summary")) is not None:
            try:
                summary = self.accounts.summary(account_id)
            except LookupError:
                self._json(404, {"ok": False, "error": "account_not_found"})
                return
            if summary is not None:
                summary = {**summary, "trading_enabled": bool(self.trader and self.trader.can_trade(account_id))}
            self._json(200, {"ok": True, "summary": summary})
        else:
            self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == PREFIX + "/accounts":
            self._provision()
            return
        trade_prefix = PREFIX + "/trade/"
        if path.startswith(trade_prefix):
            self._trade(path[len(trade_prefix):])
            return
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

    def _trade(self, operation: str) -> None:
        """Same-origin manual MAIN action, not PAPER execution."""
        if self.trader is None or not self.trader.enabled:
            self._json(403, {"ok": False, "error": "manual_main_live_disabled"})
            return
        host = self.headers.get("Host", "")
        if not host or self.headers.get("Origin", "") != "https://" + host:
            self._json(403, {"ok": False, "error": "origin_required"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._json(415, {"ok": False, "error": "json_required"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, {"ok": False, "error": "invalid_payload"})
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if not 0 < size <= 4096:
            self._json(413, {"ok": False, "error": "invalid_payload"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
            result = self.trader.submit(operation, payload)
        except (ManualMainTradeBlocked, ValueError, TypeError) as exc:
            self._json(409, {"ok": False, "error": str(exc)[:80]})
            return
        except Exception:
            # This boundary cannot prove that no exchange call took place.
            # Never turn a 503 into a retryable release of the client action.
            self._json(503, {
                "ok": False, "status": "unknown",
                "reason_code": "manual_main_outcome_unknown",
                "reconciliation_required": True,
            })
            return
        self._json(200, {"ok": result["status"] != "rejected", **result})

    def _provision(self) -> None:
        # Existing authenticated ingress enforces Telegram owner session + Origin.
        # Independently require same HTTPS origin for local callers.
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        if not host or origin != "https://" + host:
            self._json(403, {"ok": False, "error": "origin_required"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._json(415, {"ok": False, "error": "json_required"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, {"ok": False, "error": "invalid_payload"})
            return
        try:
            size = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            size = -1
        if not 0 < size <= 8192:
            self._json(413, {"ok": False, "error": "invalid_payload"})
            return
        try:
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or set(payload) != {
                "display_name", "api_key", "api_secret",
            }:
                raise ValueError("invalid_main_account_payload")
            result = self.accounts.provision(
                payload["display_name"], payload["api_key"], payload["api_secret"],
            )
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid_account_payload"})
            return
        except AccountValidationError:
            self._json(422, {"ok": False, "error": "bybit_validation_failed"})
            return
        except ManualMainAccountError:
            self._json(422, {"ok": False, "error": "main_account_ineligible"})
            return
        except CredentialStoreError:
            self._json(503, {"ok": False, "error": "credential_storage_failed"})
            return
        except Exception:
            self._json(503, {"ok": False, "error": "account_provisioning_unavailable"})
            return
        self._json(201 if result["created"] else 200, {
            "ok": True, "created": result["created"], "account_id": result["account_id"],
        })

    def log_message(self, format: str, *args) -> None:
        # Never put account IDs, query strings or credentials into access logs.
        pass


def serve(accounts: ManualMainAccounts, *, port: int = PORT,
          trader: ManualMainTrader | None = None) -> None:
    """Intentionally loopback-bound; Nginx owner auth is the public boundary."""
    handler = type("BoundManualMainReadHandler", (MainReadHandler,), {"accounts": accounts, "trader": trader})
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
        LiveAccountProjectionStore(state_dir / "main.snapshots.sqlite3", check_same_thread=False),
    )
    enabled, ceiling = enabled_from_environment()
    ledger = ManualMainTradeLedger(state_dir / "main.actions.sqlite3") if enabled and ceiling > 0 else None
    trader = ManualMainTrader(accounts, ledger, enabled=enabled, max_notional=ceiling) if ledger else None
    try:
        serve(accounts, trader=trader)
    finally:
        if ledger:
            ledger.close()
        accounts.close()


if __name__ == "__main__":
    main()
