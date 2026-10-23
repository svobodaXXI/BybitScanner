"""Immutable, validated candle/geometry payload for owner review, never for trading.

A snapshot is strictly associated with the existing original-signal archive key.
Missing or malformed detector coordinates fail closed: do not infer from PNG/live data.
"""
import hashlib
import json
import math

MAX_BARS = 2000
MAX_BYTES = 1_000_000

def canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")

def validate_snapshot(payload, *, candidate_id, symbol, timeframe):
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Unsupported geometry snapshot version")
    if (payload.get("signal_id"), payload.get("symbol"), str(payload.get("timeframe"))) != (
        candidate_id, symbol, str(timeframe)
    ):
        raise ValueError("Geometry snapshot identity mismatch")
    bars = payload.get("bars")
    boundaries = payload.get("boundaries")
    if not isinstance(bars, list) or not 2 <= len(bars) <= MAX_BARS:
        raise ValueError("Frozen candle window missing or oversized")
    if not isinstance(boundaries, list) or len(boundaries) < 2 or len(boundaries) > 16:
        raise ValueError("Source boundaries missing")
    times = []
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("Malformed frozen candle")
        t = bar.get("open_time_ms")
        if type(t) is not int or t < 0 or (times and t <= times[-1]):
            raise ValueError("Non-increasing candle times")
        for field in ("open", "high", "low", "close"):
            val = bar.get(field)
            if type(val) not in (int, float) or not math.isfinite(val) or val <= 0:
                raise ValueError("Invalid frozen candle price")
        if bar["low"] > bar["high"] or any(not bar["low"] <= bar[f] <= bar["high"] for f in ("open", "close")):
            raise ValueError("Inconsistent frozen candle")
        times.append(t)
    time_set = set(times)
    kinds = set()
    ids = set()
    for line in boundaries:
        if not isinstance(line, dict):
            raise ValueError("Malformed boundary")
        name = line.get("boundary_id")
        kind = line.get("kind")
        if not isinstance(name, str) or not name or len(name) > 128 or name in ids or kind not in ("upper", "lower"):
            raise ValueError("Invalid or duplicate boundary")
        ids.add(name)
        kinds.add(kind)
        anchors = line.get("anchors")
        if not isinstance(anchors, list) or len(anchors) != 2:
            raise ValueError("A boundary needs two anchors")
        for anchor in anchors:
            if not isinstance(anchor, dict) or type(anchor.get("bar_open_time_ms")) is not int or anchor["bar_open_time_ms"] not in time_set:
                raise ValueError("Boundary anchor missing from frozen candles")
            p = anchor.get("price")
            if type(p) not in (int, float) or not math.isfinite(p) or p <= 0:
                raise ValueError("Invalid anchor price")
        if anchors[0]["bar_open_time_ms"] >= anchors[1]["bar_open_time_ms"]:
            raise ValueError("Boundary anchors not ordered")
    if not {"upper", "lower"}.issubset(kinds):
        raise ValueError("Upper and lower boundaries required")
    blob = canonical_bytes(payload)
    if len(blob) > MAX_BYTES:
        raise ValueError("Oversized geometry payload")
    return blob, hashlib.sha256(blob).hexdigest()
