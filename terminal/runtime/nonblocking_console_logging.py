"""Console logging that can never block the PAPER owner (A3-R8).

Root cause (2026-10-12 dump of backend PID 12620): the PAPER owner thread logged
"Slow PAPER owner task" through logging.StreamHandler and stayed forever inside
KERNELBASE!WriteConsoleW; every other logging thread then waited on that handler's
lock. A Windows console stops accepting writes while a QuickEdit selection or Pause
is active, so any thread that writes to it synchronously can stall indefinitely.

Here every logger call only formats the record and does a non-blocking put into a
bounded queue; one daemon consumer thread is the only writer to the console. A full
queue drops the record and counts it (no blocking, no unbounded memory); the drop
count is written once the console accepts output again. stop() is bounded by a
timeout, so a hung console can neither block the owner nor shutdown.
"""
from __future__ import annotations

import atexit
import logging
import logging.handlers
import queue
import sys
import threading

DEFAULT_QUEUE_SIZE = 10_000
_POLL_S = 0.1
_STD_INPUT_HANDLE = -10
_ENABLE_QUICK_EDIT_MODE = 0x0040
_ENABLE_EXTENDED_FLAGS = 0x0080


class _DropOnFullQueueHandler(logging.handlers.QueueHandler):
    def __init__(self, record_queue: queue.Queue, owner: "NonBlockingConsoleLogging"):
        super().__init__(record_queue)
        self._owner = owner

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self._owner._count_drop()


class NonBlockingConsoleLogging:
    """Bounded queue + single console consumer thread; see the module docstring."""

    def __init__(self, stream, *, fmt: str, queue_size: int = DEFAULT_QUEUE_SIZE):
        self.stream = stream
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self.handler = _DropOnFullQueueHandler(self.queue, self)
        self.handler.setFormatter(logging.Formatter(fmt))  # formatted on the caller, written by the consumer
        self._lock = threading.Lock()
        self._dropped = 0
        self._reported = 0
        self._stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, name="console-log-writer", daemon=True)

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    def _count_drop(self) -> None:
        with self._lock:
            self._dropped += 1

    def start(self) -> "NonBlockingConsoleLogging":
        self.thread.start()
        return self

    def stop(self, timeout_s: float = 2.0) -> bool:
        """Drain what the console accepts within ``timeout_s``; False if the writer is still stuck."""
        self._stopping.set()
        if self.thread.is_alive() and self.thread is not threading.current_thread():
            self.thread.join(timeout=timeout_s)
        return not self.thread.is_alive()

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text + "\n")
            self.stream.flush()
        except Exception:
            pass  # a broken console must not kill the consumer

    def _run(self) -> None:
        while True:
            try:
                record = self.queue.get(timeout=_POLL_S)
            except queue.Empty:
                if self._stopping.is_set():
                    return
                continue
            self._write(record.getMessage())
            with self._lock:
                missed, self._reported = self._dropped - self._reported, self._dropped
            if missed:
                self._write(f"[LOGGING] {missed} log records dropped while the console was not accepting output")


def install_nonblocking_console_logging(*, level, fmt: str, stream=None,
                                        queue_size: int = DEFAULT_QUEUE_SIZE,
                                        register_atexit: bool = True) -> NonBlockingConsoleLogging:
    """Replace the root handlers with the bounded non-blocking queue handler."""
    console = NonBlockingConsoleLogging(sys.stderr if stream is None else stream,
                                        fmt=fmt, queue_size=queue_size).start()
    root = logging.getLogger()
    root.handlers[:] = [console.handler]
    root.setLevel(level)
    if register_atexit:
        atexit.register(console.stop, 2.0)
    return console


def disable_console_quick_edit(kernel32=None) -> bool:
    """Turn QuickEdit off for THIS process's console only; False when there is no console."""
    if kernel32 is None:
        if sys.platform != "win32":
            return False
        import ctypes
        kernel32 = ctypes.windll.kernel32
    import ctypes

    handle = kernel32.GetStdHandle(_STD_INPUT_HANDLE)
    if not handle or handle == -1:
        return False
    mode = ctypes.c_uint32()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        return False
    return bool(kernel32.SetConsoleMode(handle, (mode.value & ~_ENABLE_QUICK_EDIT_MODE) | _ENABLE_EXTENDED_FLAGS))
