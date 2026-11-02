"""Immutable final chart attachment for a closed PAPER Robot trade.

This is a downstream Trading Diary artifact, not an execution or position store.
Only CLOSED, actually filled trades qualify. No signal/open/rejected PNGs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from pathlib import Path

DEFAULT_ARCHIVE_DIR = Path(__file__).resolve().parents[2] / "runtime" / "terminal" / "diary" / "closed_charts"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class ClosedChartArchiveError(ValueError):
    pass


def _decimal(value):
    if value is None:
        return None
    return str(value)


def _write_once(path: Path, content: bytes) -> None:
    """Atomic publish. Existing closed-trade evidence is never silently replaced."""
    if path.exists():
        if path.read_bytes() != content:
            raise ClosedChartArchiveError(f"conflicting existing archive: {path.name}")
        return
    temp = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        # Exclusive create protects an existing artifact even with concurrent workers.
        try:
            os.link(temp, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ClosedChartArchiveError(f"conflicting existing archive: {path.name}")
    finally:
        temp.unlink(missing_ok=True)


def archive_closed_chart(view, rendered_chart: Path | str, *, archive_dir: Path | str | None = None) -> tuple[Path, Path]:
    """Attach one final PNG and its factual summary to the existing Diary scope.

    Called only after an actual close and rendering. Failure is observational:
    callers must not allow it to block Telegram delivery or Robot protection.
    """
    trade = getattr(view, "trade", None)
    if trade is None or getattr(view, "is_open", True) or getattr(trade, "exit_time_ms", None) is None:
        raise ClosedChartArchiveError("only a confirmed closed Robot trade may be archived")
    trade_id = str(getattr(trade, "trade_id", ""))
    if not _SAFE_ID.fullmatch(trade_id):
        raise ClosedChartArchiveError("invalid trade identity")
    markers = [
        {"time_ms": int(m.time_ms), "price": _decimal(m.price), "side": m.side}
        for m in view.markers if m.filled
    ]
    if not markers:
        raise ClosedChartArchiveError("no actual execution markers")
    chart = Path(rendered_chart)
    raw = chart.read_bytes()
    if not raw.startswith(b"\x89PNG\r\n\x1a\n") or len(raw) <= 8:
        raise ClosedChartArchiveError("rendered artifact is not a PNG")

    gross = getattr(trade, "realized_pnl_usdt", None)
    fees = getattr(view, "fees_usdt", None)
    from decimal import Decimal
    net = str(Decimal(str(gross)) - Decimal(str(fees))) if gross is not None and fees is not None else None
    report = {
        "schema": "diary-closed-chart-v1",
        "trade_id": trade_id,
        "candidate_id": str(getattr(trade, "candidate_id", "") or ""),
        "symbol": view.symbol,
        "direction": view.direction,
        "pattern": view.pattern,
        "signal_snapshot_available": view.signal_snapshot is not None,
        "entry_time_ms": getattr(trade, "entry_time_ms", None),
        "exit_time_ms": trade.exit_time_ms,
        "exit_reason": getattr(trade, "exit_reason", None),
        "average_entry": _decimal(view.average_entry),
        "stop_price": _decimal(view.stop_price),
        "take_price": _decimal(view.take_price),
        "exit_price": _decimal(getattr(trade, "exit_price", None)),
        "gross_pnl_usdt": _decimal(gross),
        "execution_fees_usdt": _decimal(fees),
        "net_pnl_usdt": net,
        "executions": markers,
        "execution_provenance": "position_view_filled_markers",
        "levels_provenance": "stored_robot_trade_or_position_protection",
        "historical_level_changes_available": False,
        "png_sha256": hashlib.sha256(raw).hexdigest(),
    }
    folder = Path(archive_dir) if archive_dir is not None else DEFAULT_ARCHIVE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    picture = folder / (trade_id + ".png")
    summary = folder / (trade_id + ".json")
    encoded = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    _write_once(summary, encoded)
    _write_once(picture, raw)
    return picture, summary
