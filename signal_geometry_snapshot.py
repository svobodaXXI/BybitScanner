"""Immutable exact-source candle and boundary evidence for owner Editor review.

Never derive an original detector ray from live chart data. These snapshots are
read-only visual evidence, not trading/admission instructions.
"""
from __future__ import annotations

import hashlib
import json
import math

MAX_BARS = 2000
MAX_BOUNDARIES = 16
MAX_BYTES = 1_000_000
ALLOWED_KINDS = {"ray": 2, "segment": 2, "horizontal": 1, "horizontal-ray": 1}


def canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def validate_snapshot(payload, *, candidate_id, symbol, timeframe):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Invalid snapshot schema")
    if (payload.get("signal_id"), payload.get("symbol"), str(payload.get("timeframe"))) != (
        str(candidate_id), str(symbol), str(timeframe),
    ):
        raise ValueError("Snapshot exact identity mismatch")
    bars = payload.get("bars")
    boundaries = payload.get("boundaries")
    if not isinstance(bars, list) or not 2 <= len(bars) <= MAX_BARS:
        raise ValueError("Missing or oversized frozen candle window")
    if not isinstance(boundaries, list) or not 1 <= len(boundaries) <= MAX_BOUNDARIES:
        raise ValueError("Missing or oversized source geometry")
    previous = -1
    timestamps = set()
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("Malformed bar")
        timestamp = bar.get("open_time_ms")
        if type(timestamp) is not int or timestamp <= previous:
            raise ValueError("Non-monotonic source timestamps")
        previous = timestamp
        timestamps.add(timestamp)
        for field in ("open", "high", "low", "close"):
            value = bar.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid frozen OHLC")
        if bar["high"] < bar["low"] or not (
            bar["low"] <= bar["open"] <= bar["high"]
            and bar["low"] <= bar["close"] <= bar["high"]
        ):
            raise ValueError("Contradictory source OHLC")
    names = set()
    for boundary in boundaries:
        if not isinstance(boundary, dict):
            raise ValueError("Malformed boundary")
        name, kind = boundary.get("boundary_id"), boundary.get("kind")
        if not isinstance(name, str) or not (1 <= len(name) <= 128) or name in names:
            raise ValueError("Duplicate or invalid boundary identity")
        names.add(name)
        if kind not in ALLOWED_KINDS:
            raise ValueError("Unsupported boundary kind")
        anchors = boundary.get("anchors")
        if not isinstance(anchors, list) or len(anchors) != ALLOWED_KINDS[kind]:
            raise ValueError("Incomplete detector anchors")
        previous_anchor = -1
        for anchor in anchors:
            if not isinstance(anchor, dict):
                raise ValueError("Malformed detector anchor")
            at, price = anchor.get("bar_open_time_ms"), anchor.get("price")
            if type(at) is not int or at not in timestamps or at <= previous_anchor:
                raise ValueError("Source anchor not contained in frozen candles")
            previous_anchor = at
            if type(price) not in (int, float) or not math.isfinite(price) or price <= 0:
                raise ValueError("Invalid detector anchor price")
    encoded = canonical_bytes(payload)
    if len(encoded) > MAX_BYTES:
        raise ValueError("Oversized snapshot")
    return encoded, hashlib.sha256(encoded).hexdigest()
