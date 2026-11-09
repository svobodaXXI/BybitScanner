"""Account-isolated, at-most-once manual Bybit MAIN command boundary.

No Scanner/Robot/PAPER imports or data writes. Disabled unless separately armed
by a protected service environment; a checked-in release never enables LIVE.
UNKNOWN outcomes stay fenced across restarts and must not be replayed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path

from terminal.exchange.bybit_v5_adapter import BybitCredentials

_ACTION = re.compile(r"[A-Za-z0-9_-]{8,36}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{2,22}\Z")
_OPERATIONS = frozenset({
    "market", "limit", "limit/amend", "limit/cancel",
    "stop", "stop/amend", "stop/delete",
    "take", "take/amend", "take/delete", "full-close",
})


class ManualMainTradeBlocked(ValueError):
    pass


def _require(value, reason: str) -> None:
    if not value:
        raise ManualMainTradeBlocked(reason)


def _positive(value, label: str) -> Decimal:
    try:
        _require(isinstance(value, str), label + "_invalid")
        v = Decimal(value)
        _require(v.is_finite() and v > 0, label + "_invalid")
        return v
    except (InvalidOperation, TypeError) as exc:
        raise ManualMainTradeBlocked(label + "_invalid") from exc


def _number(value: Decimal) -> str:
    return format(value, "f")


class ManualMainTradeLedger:
    """Single durable decision before any exchange call. No unknown replay."""

    def __init__(self, path: Path) -> None:
        _require(path.parent.is_dir() and not path.parent.is_symlink()
                 and not path.parent.stat().st_mode & 0o077,
                 "main_ledger_directory_not_private")
        self._conn = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA journal_mode=DELETE")
        self._conn.execute("""CREATE TABLE IF NOT EXISTS manual_main_actions (
            account_id TEXT NOT NULL, action_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL, operation TEXT NOT NULL,
            state TEXT NOT NULL, order_id TEXT,
            PRIMARY KEY (account_id, action_id))""")
        self._lock = threading.RLock()

    def reserve(self, account: str, action_id: str, fingerprint: str, operation: str) -> tuple[str, str | None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                row = self._conn.execute(
                    "SELECT fingerprint, state, order_id FROM manual_main_actions WHERE account_id=? AND action_id=?",
                    (account, action_id),
                ).fetchone()
                if row is not None:
                    _require(row[0] == fingerprint, "client_action_conflict")
                    self._conn.execute("COMMIT")
                    return row[1], row[2]
                unresolved = self._conn.execute(
                    "SELECT 1 FROM manual_main_actions WHERE account_id=? AND state IN ('PENDING','UNKNOWN') LIMIT 1",
                    (account,),
                ).fetchone()
                _require(unresolved is None, "main_reconciliation_required")
                self._conn.execute(
                    "INSERT INTO manual_main_actions VALUES (?,?,?,?,?,NULL)",
                    (account, action_id, fingerprint, operation, "PENDING"),
                )
                self._conn.execute("COMMIT")
                return "NEW", None
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise

    def finish(self, account: str, action_id: str, status: str, order_id: str | None) -> None:
        _require(status in {"ACKNOWLEDGED", "UNKNOWN", "REJECTED"}, "invalid_action_outcome")
        with self._lock:
            self._conn.execute(
                "UPDATE manual_main_actions SET state=?,order_id=? WHERE account_id=? AND action_id=? AND state='PENDING'",
                (status, order_id, account, action_id),
            )

    def close(self) -> None:
        self._conn.close()


class ManualMainTrader:
    def __init__(self, accounts, ledger: ManualMainTradeLedger, *,
                 enabled: bool = False, max_notional: Decimal = Decimal("0"),
                 http_factory=None) -> None:
        self._accounts = accounts
        self._ledger = ledger
        self._enabled = enabled
        self._ceiling = max_notional
        self._http_factory = http_factory
        self._lock = threading.RLock()

    @property
    def enabled(self) -> bool:
        return self._enabled and self._ceiling.is_finite() and self._ceiling > 0

    def can_trade(self, account_id: str) -> bool:
        if not self.enabled:
            return False
        try:
            stored = self._accounts._lookup(account_id)
            summary = self._accounts.summary(account_id)
            return bool(not stored.read_only and summary and summary.get("status") == "READY")
        except (LookupError, ValueError):
            return False

    def submit(self, operation: str, payload: dict) -> dict:
        """Never issue an exchange call without fresh account and journal attestation."""
        _require(self.enabled, "manual_main_live_disabled")
        _require(operation in _OPERATIONS, "unsupported_main_operation")
        _require(isinstance(payload, dict), "invalid_main_payload")
        _require(payload.get("confirmed") is True, "owner_confirmation_required")
        account = payload.get("account_id")
        action = payload.get("client_action_id")
        symbol = payload.get("symbol")
        generation = payload.get("session_generation")
        _require(isinstance(account, str) and account.startswith("bybit-"), "invalid_main_account")
        _require(isinstance(action, str) and _ACTION.fullmatch(action), "invalid_client_action")
        _require(isinstance(symbol, str) and _SYMBOL.fullmatch(symbol), "invalid_main_symbol")
        _require(type(generation) is int and generation > 0, "invalid_main_generation")
        # No API keys enter the request or response.
        with self._lock:
            stored = self._accounts._lookup(account)
            _require(stored.environment == "MAINNET" and not stored.read_only,
                     "main_trade_credentials_not_authorized")
            snapshot = self._accounts.summary(account)
            _require(snapshot is not None and snapshot.get("status") == "READY"
                     and snapshot.get("refresh_generation") == generation,
                     "stale_main_account_authority")
            validated = self._accounts._validator.validate(
                BybitCredentials(stored.api_key, stored.api_secret))
            _require(validated.environment == "MAINNET" and not validated.read_only,
                     "main_trade_credentials_not_authorized")
            params = self._prepare(operation, payload, snapshot)
            fingerprint = hashlib.sha256(json.dumps(
                {"operation": operation, "payload": payload},
                sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            ).encode()).hexdigest()
            state, order_id = self._ledger.reserve(account, action, fingerprint, operation)
            if state != "NEW":
                return self._result(state, action, order_id)
            status, order_id = "UNKNOWN", None
            try:
                if self._http_factory is None:
                    from pybit.unified_trading import HTTP
                    factory = HTTP
                else:
                    factory = self._http_factory
                api = factory(
                    testnet=False, api_key=stored.api_key, api_secret=stored.api_secret,
                    timeout=10, force_retry=False, max_retries=0, log_requests=False,
                )
                method = {
                    "market": api.place_order,
                    "limit": api.place_order,
                    "full-close": api.place_order,
                    "limit/amend": api.amend_order,
                    "limit/cancel": api.cancel_order,
                    "stop": api.set_trading_stop,
                    "stop/amend": api.set_trading_stop,
                    "stop/delete": api.set_trading_stop,
                    "take": api.set_trading_stop,
                    "take/amend": api.set_trading_stop,
                    "take/delete": api.set_trading_stop,
                }[operation]
                reply = method(**params)
                if isinstance(reply, dict) and reply.get("retCode") == 0:
                    result = reply.get("result")
                    order_id = result.get("orderId") if isinstance(result, dict) else None
                    status = "ACKNOWLEDGED"
                # Even an exchange error may be ambiguous; no implicit retry.
            except Exception:
                status = "UNKNOWN"
            self._ledger.finish(account, action, status, order_id)
            return self._result(status, action, order_id)

    @staticmethod
    def _result(state: str, action_id: str, order_id: str | None) -> dict:
        return {
            "status": "accepted_pending" if state == "ACKNOWLEDGED" else
                      "unknown" if state in ("UNKNOWN", "PENDING") else "rejected",
            "reason_code": "exchange_ack" if state == "ACKNOWLEDGED" else
                           "reconciliation_required" if state in ("UNKNOWN", "PENDING") else "exchange_rejected",
            "command_id": action_id,
            "order_id": order_id,
            "reconciliation_required": state in ("UNKNOWN", "PENDING"),
        }

    def _prepare(self, op: str, data: dict, snapshot: dict) -> dict:
        symbol = data["symbol"]
        common = {"category": "linear", "symbol": symbol}
        if op in ("market", "limit"):
            _require(data.get("side") in ("Buy", "Sell"), "invalid_order_side")
            volume = data.get("volume")
            _require(isinstance(volume, dict) and volume.get("unit") == "usdt",
                     "main_requires_usdt_volume")
            notional = _positive(volume.get("amount"), "volume")
            _require(notional <= self._ceiling, "manual_main_notional_ceiling")
            reference = _positive(data.get("sizing_reference_price"), "reference_price")
            # Exchange lot validation and final rejection remain authoritative.
            qty = notional / reference
            _require(qty > 0, "invalid_order_quantity")
            args = {**common, "side": data["side"], "qty": _number(qty),
                    "orderType": "Market" if op == "market" else "Limit",
                    "orderLinkId": data["client_action_id"][:36]}
            if op == "limit":
                price = _positive(data.get("limit_price"), "limit_price")
                _require(qty * max(price, reference) <= self._ceiling,
                         "manual_main_notional_ceiling")
                args.update(price=_number(price), timeInForce="GTC")
            else:
                args["slippageToleranceType"] = "Percent"
                args["slippageTolerance"] = "0.5"
            return args
        if op == "full-close":
            positions = [p for p in snapshot.get("positions", [])
                         if p.get("symbol") == symbol and
                         Decimal(str(p.get("quantity", "0"))) > 0]
            _require(len(positions) == 1, "main_close_position_ambiguous")
            position = positions[0]
            _require(position.get("side") in ("Buy", "Sell"), "main_close_side_invalid")
            idx = position.get("position_idx", 0)
            _require(type(idx) is int and idx in (0, 1, 2), "main_close_hedge_invalid")
            return {**common, "side": "Sell" if position["side"] == "Buy" else "Buy",
                    "orderType": "Market", "qty": str(position["quantity"]),
                    "reduceOnly": True, "positionIdx": idx,
                    "orderLinkId": data["client_action_id"][:36]}
        if op in ("limit/amend", "limit/cancel"):
            order_id = data.get("order_id")
            _require(isinstance(order_id, str) and 1 <= len(order_id) <= 96
                     and re.fullmatch(r"[A-Za-z0-9_-]+", order_id), "invalid_main_order_id")
            args = {**common, "orderId": order_id}
            if op == "limit/amend":
                price = _positive(data.get("limit_price"), "limit_price")
                args["price"] = _number(price)
                # Do not allow quantity increases without a fresh bounded intent.
                _require(data.get("quantity") in (None, "", "0"), "main_amend_qty_unsupported")
            return args
        _require(op.startswith(("stop", "take")), "unsupported_main_operation")
        stop = data.get("stop_loss")
        take = data.get("take_profit")
        args = {**common, "tpslMode": "Full", "positionIdx": 0}
        if op.startswith("stop"):
            args["stopLoss"] = "0" if op.endswith("/delete") else _number(_positive(stop, "stop_loss"))
            args["slTriggerBy"] = "MarkPrice"
        else:
            args["takeProfit"] = "0" if op.endswith("/delete") else _number(_positive(take, "take_profit"))
            args["tpTriggerBy"] = "MarkPrice"
        return args


def enabled_from_environment() -> tuple[bool, Decimal]:
    enabled = os.environ.get("BYBITSCANNER_MANUAL_MAIN_TRADING_ENABLED", "") == "1"
    try:
        cap = Decimal(os.environ.get("BYBITSCANNER_MANUAL_MAIN_MAX_ORDER_USDT", "0"))
    except InvalidOperation:
        cap = Decimal("0")
    return enabled, cap
