"""Durable minimal Robot v0.1 trade records."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import secrets
from typing import Any, Mapping

DEFAULT_TRADE_STORE_DIR = Path(__file__).resolve().parent / "runtime" / "terminal" / "robot_trades"
SCHEMA_VERSION = "1.0"

class RobotTradeStoreError(RuntimeError):
    pass

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def _safe_id(value: str) -> str:
    text = str(value).strip()
    if not text or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in text):
        raise RobotTradeStoreError("invalid trade_id")
    return text

def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"unsupported trade-record value: {type(value).__name__}")

def _freeze(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value), ensure_ascii=False, sort_keys=True, default=_json_default))

def _path(trade_id: str, store_dir: Path) -> Path:
    return store_dir / f"{_safe_id(trade_id)}.json"

def _write_new(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise RobotTradeStoreError(f"trade already exists: {path.stem}") from exc

def _replace(path: Path, record: Mapping[str, Any]) -> None:
    temp = path.with_suffix(f".{secrets.token_hex(6)}.tmp")
    try:
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temp.replace(path)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        raise RobotTradeStoreError(f"cannot update trade {path.stem}") from exc

def create_trade_record(*, trade_id: str, symbol: str, direction: str, pattern: str, source_timeframe: str,
                        signal_time: str, signal_snapshot_id: str, entry_time: str, entry_path: str,
                        actual_wv: Decimal, average_entry: Decimal, stop_price: Decimal, take_price: Decimal,
                        store_dir: Path | str | None = None) -> dict[str, Any]:
    directory = Path(store_dir) if store_dir is not None else DEFAULT_TRADE_STORE_DIR
    record = _freeze({
        "schema_version": SCHEMA_VERSION, "trade_id": _safe_id(trade_id), "symbol": str(symbol).strip().upper(),
        "direction": str(direction).strip().upper(), "pattern": str(pattern).strip(),
        "source_timeframe": str(source_timeframe).strip(), "signal_time": str(signal_time).strip(),
        "signal_snapshot_id": str(signal_snapshot_id).strip(), "entry_time": str(entry_time).strip(),
        "entry_path": str(entry_path).strip(), "actual_wv": actual_wv, "average_entry": average_entry,
        "stop_price": stop_price, "take_price": take_price, "exit_time": None, "exit_price": None,
        "exit_reason": None, "realized_pnl_usdt": None, "realized_pnl_pct": None, "fees_costs_usdt": None,
        "created_at": _utc_now_iso(), "updated_at": _utc_now_iso(),
    })
    required = ("symbol", "direction", "pattern", "source_timeframe", "signal_snapshot_id", "entry_path")
    if any(not record[field] for field in required):
        raise RobotTradeStoreError("trade record required field is empty")
    if Decimal(record["actual_wv"]) <= 0 or Decimal(record["actual_wv"]) > 1:
        raise RobotTradeStoreError("actual_wv must be in (0, 1]")
    for field in ("average_entry", "stop_price", "take_price"):
        if Decimal(record[field]) <= 0:
            raise RobotTradeStoreError(f"{field} must be positive")
    _write_new(_path(trade_id, directory), record)
    return deepcopy(record)

def load_trade_record(trade_id: str, *, store_dir: Path | str | None = None) -> dict[str, Any]:
    directory = Path(store_dir) if store_dir is not None else DEFAULT_TRADE_STORE_DIR
    path = _path(trade_id, directory)
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RobotTradeStoreError(f"trade not found: {trade_id}") from exc
    if not isinstance(record, dict) or record.get("schema_version") != SCHEMA_VERSION or record.get("trade_id") != path.stem:
        raise RobotTradeStoreError("trade record is corrupt")
    return deepcopy(record)

def close_trade_record(trade_id: str, *, exit_time: str, exit_price: Decimal, exit_reason: str,
                       realized_pnl_usdt: Decimal, realized_pnl_pct: Decimal, fees_costs_usdt: Decimal | None = None,
                       store_dir: Path | str | None = None) -> tuple[dict[str, Any], bool]:
    directory = Path(store_dir) if store_dir is not None else DEFAULT_TRADE_STORE_DIR
    path = _path(trade_id, directory)
    record = load_trade_record(trade_id, store_dir=directory)
    if record.get("exit_time") is not None:
        same = (record.get("exit_time") == str(exit_time) and record.get("exit_price") == str(exit_price)
                and record.get("exit_reason") == str(exit_reason) and record.get("realized_pnl_usdt") == str(realized_pnl_usdt)
                and record.get("realized_pnl_pct") == str(realized_pnl_pct)
                and record.get("fees_costs_usdt") == (str(fees_costs_usdt) if fees_costs_usdt is not None else None))
        if not same:
            raise RobotTradeStoreError("trade already closed with different result")
        return record, False
    record.update({"exit_time": str(exit_time), "exit_price": str(exit_price), "exit_reason": str(exit_reason),
                   "realized_pnl_usdt": str(realized_pnl_usdt), "realized_pnl_pct": str(realized_pnl_pct),
                   "fees_costs_usdt": str(fees_costs_usdt) if fees_costs_usdt is not None else None,
                   "updated_at": _utc_now_iso()})
    _replace(path, record)
    return deepcopy(record), True
