"""Ephemeral elapsed-time breakdown for one serialized protection callback.

Stage totals are disjoint. SQLite transaction-control intervals are nested
subsets, not additional stages or a measurement of CPU time / OS fsync.

``callback_cpu_ms`` is the owning thread's CPU time over the callback
(``time.thread_time_ns``); ``callback_non_cpu_wall_ms`` is elapsed minus that.
Non-CPU wall time is time the thread was not running for any reason (waiting
for the interpreter, I/O, the OS scheduler); it is not a measurement of any one
of them. The CPU clock can be coarse (``cpu_clock_resolution_ms``); when it is
unavailable both CPU fields are null and nothing else changes.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import time


_active = ContextVar("protection_callback_timing", default=None)
STAGES = ("state", "limit", "fill", "protection", "recovery")


def _thread_cpu_ns():
    try:
        return time.thread_time_ns()
    except Exception:
        return None


def _cpu_clock_resolution_ms():
    try:
        return time.get_clock_info("thread_time").resolution * 1000
    except Exception:
        return None


@dataclass
class CallbackTiming:
    elapsed: dict = field(default_factory=dict)
    valid: bool = True
    cpu_started_ns: int | None = None
    cpu_ms: float | None = None

    def finish_cpu(self):
        ended = _thread_cpu_ns()
        if self.cpu_started_ns is not None and ended is not None and ended >= self.cpu_started_ns:
            self.cpu_ms = (ended - self.cpu_started_ns) / 1_000_000

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
            "callback_cpu_ms": self.cpu_ms,
            "callback_non_cpu_wall_ms": None if self.cpu_ms is None else callback_ms - self.cpu_ms,
            "cpu_clock": "thread_time_ns",
            "cpu_clock_resolution_ms": _cpu_clock_resolution_ms(),
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
    trace = CallbackTiming(cpu_started_ns=_thread_cpu_ns())
    token = _active.set(trace)
    try:
        yield trace
    finally:
        _active.reset(token)
        trace.finish_cpu()


@contextmanager
def protection_span(name):
    trace = _active.get()
    started = trace.now() if trace is not None else None
    try:
        yield
    finally:
        if trace is not None:
            trace.record(name, started)
