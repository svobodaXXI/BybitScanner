"""Ephemeral elapsed-time breakdown for one serialized protection callback.

Stage totals are disjoint. SQLite transaction-control intervals are nested
subsets, not additional stages or a measurement of CPU time / OS fsync.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time


_active = ContextVar("protection_callback_timing", default=None)
STAGES = ("state", "limit", "fill", "protection", "recovery")


@dataclass
class CallbackTiming:
    elapsed: dict = field(default_factory=dict)
    valid: bool = True

    def now(self):
        try:
            return time.perf_counter()
        except Exception:
            self.valid = False
            return None

    def record(self, name, started):
        try:
            ended = self.now()
            if started is not None and ended is not None:
                self.elapsed[name] = self.elapsed.get(name, 0.0) + (ended - started) * 1000
        except Exception:
            self.valid = False

    def report(self, event_id, callback_ms):
        stages = {name: self.elapsed.get(name, 0.0) for name in STAGES}
        measured = sum(stages.values())
        return {
            "event_id": event_id or None,
            "clock": "perf_counter_elapsed",
            "callback_elapsed_ms": callback_ms,
            "stages_ms": stages,
            "stage_sum_ms": measured,
            "unmeasured_ms": callback_ms - measured,
            "accounting_valid": self.valid and 0 <= measured <= callback_ms,
            "sqlite_control_nested_ms": {
                name: self.elapsed.get("sqlite_" + name, 0.0)
                for name in ("begin", "commit", "rollback")
            },
        }


@contextmanager
def capture_callback():
    trace = CallbackTiming()
    token = _active.set(trace)
    try:
        yield trace
    finally:
        _active.reset(token)


@contextmanager
def protection_span(name):
    trace = _active.get()
    started = trace.now() if trace is not None else None
    try:
        yield
    finally:
        if trace is not None:
            trace.record(name, started)
