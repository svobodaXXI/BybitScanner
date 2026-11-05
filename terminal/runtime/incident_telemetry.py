"""Bounded asynchronous, strict-allowlist evidence for #449 PAPER incidents.

Independent of the console writer and trading owner. A full queue or failed
filesystem never blocks protection, Scanner or WebSocket continuity fencing.
This is best-effort observability, not an execution / FLAT safety receipt.
Reuses the existing atomic, bounded-200-file Robot incident recorder but writes
into a *separate* directory so telemetry cannot evict Robot failure evidence.
Raw exceptions, arbitrary messages and untrusted context are never persisted.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
import queue
import re
import threading
import uuid

from robot_failure_diagnostics import record_robot_incident


_CAPACITY = 256
_ALLOWED = {
    "OWNER_SLOW": {
        "task_kind": "name", "task_label": "name",
        "processing_ms": "metric", "queue_depth": "count",
        "ingress_queue_latency_ms": "metric", "ingress_pending": "count",
        "symbol": "symbol", "role": "name",
    },
    "INGRESS_WATERMARK": {
        "capacity": "count", "pending": "count",
        "symbol": "symbol", "role": "name",
    },
    "INGRESS_OVERFLOW": {
        "capacity": "count", "pending": "count",
        "symbol": "symbol", "role": "name",
    },
    "WS_DISCONNECT": {
        "contexts": "count", "generation": "count",
        "symbol": "symbol", "error_class": "name",
    },
}
_SYMBOL = re.compile(r"[A-Z0-9]{1,32}\Z", re.ASCII)
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.]{0,95}\Z", re.ASCII)
_EVENT_ID = re.compile(r"[A-Z0-9]{1,32}:[0-9]{1,20}:[0-9]{1,20}\Z", re.ASCII)
_SENTINEL = object()
_active = None


def _safe_value(value, kind):
    if kind == "name":
        return value if isinstance(value, str) and _NAME.fullmatch(value) else "UNAVAILABLE"
    if kind == "symbol":
        return value if isinstance(value, str) and _SYMBOL.fullmatch(value) else "UNKNOWN"
    if kind == "count":
        return value if type(value) is int and 0 <= value <= 1_000_000_000 else None
    if kind == "metric":
        return (round(float(value), 3)
                if type(value) in (int, float) and math.isfinite(value)
                and 0 <= value <= 1_000_000_000 else None)
    return None


def _default_directory() -> Path:
    override = os.environ.get("BYBITSCANNER_OWNER_INCIDENT_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    db = os.environ.get("BYBITSCANNER_PAPER_DB", "").strip()
    if db:
        return Path(db).expanduser().parent / "owner_incidents"
    return Path(__file__).resolve().parents[2] / "runtime" / "terminal" / "owner_incidents"


class IncidentTelemetry:
    def __init__(self, *, directory: Path | str | None = None, capacity: int = _CAPACITY,
                 writer=None):
        if type(capacity) is not int or not 1 <= capacity <= 4096:
            raise ValueError("incident queue capacity invalid")
        self.directory = Path(directory) if directory is not None else _default_directory()
        self.queue = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self._writer = record_robot_incident if writer is None else writer
        self._thread = threading.Thread(
            target=self._run, name="owner-incident-telemetry", daemon=True,
        )
        self._thread.start()

    def publish(self, category: str, *, event_id: str = "", **facts) -> bool:
        schema = _ALLOWED.get(category)
        if schema is None:
            return False
        try:
            incident_id = (event_id if isinstance(event_id, str)
                           and _EVENT_ID.fullmatch(event_id) else uuid.uuid4().hex)
            allowed = {
                key: _safe_value(facts[key], kind)
                for key, kind in schema.items() if key in facts
            }
            # Unknown fields are deliberately ignored. No raw strings or stack
            # traces can enter the queue or the recorder's fact serializer.
            symbol = allowed.get("symbol")
            record = {
                "incident_type": "PAPER_OWNER_OBSERVABILITY",
                "stage": category,
                "reason_code": category,
                "symbol": symbol if isinstance(symbol, str) else None,
                "facts": {"incident_id": incident_id, **allowed},
                "incident_dir": self.directory,
            }
            self.queue.put_nowait(record)
            return True
        except queue.Full:
            self.dropped += 1  # bounded diagnostics loss, NEVER safety bypass
            return False
        except Exception:
            return False

    def _run(self):
        while True:
            item = self.queue.get()
            try:
                if item is _SENTINEL:
                    return
                try:
                    self._writer(**item)
                except Exception:
                    pass  # optional diagnostics must never affect protection
            finally:
                self.queue.task_done()

    def close(self, *, timeout: float = 5.0) -> bool:
        """Best-effort flush for test / orderly operator shutdown; never owner IO."""
        try:
            self.queue.put(_SENTINEL, timeout=min(timeout, 0.5))
        except queue.Full:
            return False
        self._thread.join(timeout=max(0.0, timeout))
        return not self._thread.is_alive()


def start_incident_telemetry(*, directory: Path | str | None = None):
    """Start once after the HTTP port-ownership barrier; no disk IO on owner."""
    global _active
    if _active is None:
        _active = IncidentTelemetry(directory=directory)
    return _active


def report_incident(category: str, *, event_id: str = "", **facts) -> bool:
    current = _active
    if current is None:
        return False
    try:
        return current.publish(category, event_id=event_id, **facts)
    except Exception:
        return False
