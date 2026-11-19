"""Optional, source-only preview evidence; never an entry receipt or Robot writer.

Not wired to a runtime. A future owner-approved off-owner caller can persist
one exact observed 30s window without adding WebSocket subscriptions or DB writes.
Absence of a capture, missing prints, or local timestamps is NOT source proof.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
from decimal import Decimal

_MAX_PRINTS = 512
_KEEP = 200
_PREFIX = "pattern-flow-shadow-"


def _window_rows(prints: tuple, decision_ms: int) -> list[list[str | int]]:
    if type(decision_ms) is not int or decision_ms < 30_000 or not isinstance(prints, tuple):
        raise ValueError("invalid shadow window")
    start, middle = decision_ms - 30_000, decision_ms - 15_000
    rows: list[list[str | int]] = []
    seen: set[str] = set()
    previous = current = False
    prior_time = -1
    for item in prints:
        t = getattr(item, "timestamp_ms", None)
        if type(t) is not int:
            raise ValueError("non-exact trade time")
        if not start <= t < decision_ms:
            continue
        received = getattr(item, "received_at_ms", None)
        trade_id = getattr(item, "trade_id", None)
        sequence = getattr(item, "sequence", None)
        side = getattr(item, "side", None)
        price = getattr(item, "price", None)
        quantity = getattr(item, "quantity", None)
        if (type(received) is not int or not t <= received <= decision_ms
                or type(trade_id) is not str or not trade_id or len(trade_id) > 128
                or type(sequence) is not int or sequence < 0
                or side not in ("Buy", "Sell")
                or t < prior_time or trade_id in seen
                or len(rows) >= _MAX_PRINTS
                or not isinstance(price, Decimal) or not price.is_finite()
                or not isinstance(quantity, Decimal) or not quantity.is_finite()
                or price <= 0 or quantity <= 0):
            raise ValueError("unverifiable shadow trade facts")
        rows.append([trade_id, t, sequence, side, str(price), str(quantity), received])
        seen.add(trade_id)
        prior_time = t
        if t < middle:
            previous = True
        else:
            current = True
    if not previous or not current:
        raise ValueError("shadow windows incomplete")
    return rows


def window_digest(prints: tuple, decision_ms: int) -> str:
    rows = _window_rows(prints, decision_ms)
    return hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def build_shadow_sample(record, preview, snapshot: dict) -> dict:
    """Fail closed if a refreshed market snapshot differs from the preview's tape."""
    if (record.status != "APPROVED"
            or record.candidate_id != preview.candidate_id
            or record.state_revision != preview.state_revision
            or record.symbol.value != preview.symbol
            or not isinstance(record.robot_state, dict)
            or record.robot_state.get("direction") != preview.direction
            or preview.source_complete is not False
            or preview.trading_authorized is not False
            or not isinstance(snapshot, dict)
            or snapshot.get("symbol") != preview.symbol
            or snapshot.get("generation") != preview.transport_generation
            or snapshot.get("invalid_frames") != 0
            or snapshot.get("continuity") != "UNPROVEN"
            or snapshot.get("order_authority") is not False
            or (snapshot.get("gap_or_truncation") is not False) != preview.gap_or_truncation):
        raise ValueError("unverified candidate or source identity")
    rows = _window_rows(snapshot.get("prints"), preview.known_at_ms)
    digest = hashlib.sha256(json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    if not preview.window_sha256 or digest != preview.window_sha256:
        raise ValueError("preview/source changed between observations")
    signal = record.signal_snapshot
    state = record.robot_state
    if (not isinstance(signal, dict) or not isinstance(state, dict)
            or signal.get("pattern") not in ("Falling Wedge", "Rising Wedge", "L-shape", "MIRROR", "IKIGAI_BOX")
            or not isinstance(state.get("phase"), str)
            or type(preview.known_at_ms) is not int
            or not isinstance(record.snapshot_sha256, str)
            or len(record.snapshot_sha256) != 64):
        raise ValueError("missing frozen host metadata")
    return {
        "schema": "BYBITSCANNER_PATTERN_FLOW_SHADOW_V1",
        "evidence_kind": "NON_AUTHORITATIVE_PREVIEW",
        "candidate_id": preview.candidate_id,
        "state_revision": preview.state_revision,
        "signal_snapshot_sha256": record.snapshot_sha256,
        "symbol": preview.symbol,
        "pattern": signal["pattern"],
        "direction": preview.direction,
        "phase": state["phase"],
        "known_at_ms": preview.known_at_ms,
        "window_start_ms": preview.known_at_ms - 30_000,
        "transport_generation": preview.transport_generation,
        "window_sha256": digest,
        "gap_or_truncation": preview.gap_or_truncation,
        "buy_wave_accelerating": preview.transition.buy_wave_accelerating,
        "sell_wave_accelerating": preview.transition.sell_wave_accelerating,
        "public_trade_rows": rows,
        "local_receipt_times_available": True,
        "source_complete": False,
        "trading_authorized": False,
    }


def save_shadow_sample(directory: Path, sample: dict) -> bool:
    """Best-effort atomic, separately scoped bounded files; call off-owner only.

    This writer is intentionally NOT connected to any live lifecycle, scheduler
    or feature flag. It cannot report source completeness or grant entry.
    """
    if (not isinstance(sample, dict)
            or sample.get("schema") != "BYBITSCANNER_PATTERN_FLOW_SHADOW_V1"
            or sample.get("source_complete") is not False
            or sample.get("trading_authorized") is not False):
        return False
    try:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        name = f"{_PREFIX}{sample['known_at_ms']:016d}-{secrets.token_hex(4)}.json"
        target = root / name
        temp = root / ("." + name + ".tmp")
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(sample, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temp.replace(target)
        existing = sorted(root.glob(f"{_PREFIX}*.json"))
        for item in existing[:-_KEEP]:
            try:
                item.unlink()
            except OSError:
                pass
        return True
    except (OSError, ValueError, TypeError, KeyError):
        return False
