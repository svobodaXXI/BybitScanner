"""A3-R8 focused regression: a hung console writer must never block the PAPER owner.

Reproduces the 2026-10-12 dump: the owner thread logged "Slow PAPER owner task"
(SerializedPaperRuntime._observe_owner_task) and stayed inside WriteConsoleW.
The console stream here is a stub whose write() blocks until released.
"""
import io
import logging
import queue
import threading
import time
import unittest

from terminal.runtime.nonblocking_console_logging import (
    DEFAULT_QUEUE_SIZE, NonBlockingConsoleLogging, disable_console_quick_edit,
    install_nonblocking_console_logging,
)

FORMAT = "%(levelname)s %(name)s %(message)s"


class _HungStream:
    """A console whose write() never returns until released (frozen QuickEdit/conhost)."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.lines = []

    def write(self, text):
        self.entered.set()
        self.release.wait(10)
        self.lines.append(text)

    def flush(self):
        pass


class _Isolated(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        self._saved = (root.handlers[:], root.level)
        self.addCleanup(self._restore)

    def _restore(self):
        root = logging.getLogger()
        root.handlers[:] = self._saved[0]
        root.setLevel(self._saved[1])

    def install(self, stream, **kwargs):
        logging_ = install_nonblocking_console_logging(
            level="INFO", fmt=FORMAT, stream=stream, register_atexit=False, **kwargs)
        self.addCleanup(logging_.stop, 0.5)
        return logging_


class HungConsoleWriterTests(_Isolated):
    def test_owner_slow_task_warning_returns_while_console_is_hung(self):
        from terminal.runtime.paper_http_server import SerializedPaperRuntime, SLOW_OWNER_TASK_WARNING_MS

        stream = _HungStream()
        self.addCleanup(stream.release.set)
        self.install(stream)
        logging.getLogger("warmup").warning("first record occupies the console writer")
        self.assertTrue(stream.entered.wait(2))  # the console consumer is now stuck in write()

        owner = SerializedPaperRuntime.__new__(SerializedPaperRuntime)
        owner._owner_diagnostics_disabled = False
        owner._slowest_owner_task = (0.0, None, None)
        owner._requests = queue.Queue()
        started = time.perf_counter()
        for _ in range(50):  # the exact call that hung in the dump, repeated
            owner._observe_owner_task("call", lambda runtime: None, SLOW_OWNER_TASK_WARNING_MS + 364.0)
        self.assertLess(time.perf_counter() - started, 0.5)
        self.assertFalse(owner._owner_diagnostics_disabled)

    def test_overflow_drops_records_instead_of_blocking_or_growing(self):
        stream = _HungStream()
        self.addCleanup(stream.release.set)
        logging_ = self.install(stream, queue_size=10)
        log = logging.getLogger("terminal.runtime.paper_http_server")
        log.warning("occupy the writer")
        self.assertTrue(stream.entered.wait(2))
        started = time.perf_counter()
        for i in range(2000):
            log.warning("record %d", i)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertLessEqual(logging_.queue.qsize(), 10)
        self.assertGreaterEqual(logging_.dropped, 2000 - 10)

    def test_stop_with_a_hung_consumer_is_bounded_and_reported(self):
        stream = _HungStream()
        logging_ = self.install(stream)
        logging.getLogger("x").warning("stuck")
        self.assertTrue(stream.entered.wait(2))
        started = time.perf_counter()
        self.assertFalse(logging_.stop(timeout_s=0.2))
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertTrue(logging_.thread.daemon)  # never keeps the process alive
        stream.release.set()


class NormalPathTests(_Isolated):
    def test_records_reach_the_console_in_order_and_stop_drains(self):
        stream = io.StringIO()
        logging_ = self.install(stream)
        log = logging.getLogger("terminal.runtime.paper_http_server")
        for i in range(5):
            log.warning("message %d", i)
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            log.exception("failure")
        self.assertTrue(logging_.stop(timeout_s=2))
        text = stream.getvalue()
        self.assertEqual([line for line in text.splitlines() if "message" in line],
                         [f"WARNING terminal.runtime.paper_http_server message {i}" for i in range(5)])
        self.assertIn("RuntimeError: boom", text)  # exception text is preserved

    def test_dropped_records_are_reported_once_the_console_recovers(self):
        stream = _HungStream()
        logging_ = self.install(stream, queue_size=2)
        log = logging.getLogger("y")
        log.warning("first")
        self.assertTrue(stream.entered.wait(2))
        for i in range(20):
            log.warning("burst %d", i)
        stream.release.set()
        self.assertTrue(logging_.stop(timeout_s=2))
        self.assertTrue(any("log records dropped" in line for line in stream.lines))

    def test_root_logger_uses_only_the_queue_handler(self):
        logging_ = self.install(io.StringIO())
        self.assertEqual(logging.getLogger().handlers, [logging_.handler])
        self.assertEqual(DEFAULT_QUEUE_SIZE, logging_.queue.maxsize)


class QuickEditTests(unittest.TestCase):
    class _Kernel32:
        def __init__(self, mode, console=True):
            self.mode, self.console, self.set_calls = mode, console, []

        def GetStdHandle(self, which):
            return 7 if which == -10 else 0

        def GetConsoleMode(self, handle, mode_ref):
            if not self.console:
                return 0
            mode_ref._obj.value = self.mode
            return 1

        def SetConsoleMode(self, handle, mode):
            self.set_calls.append(mode)
            return 1

    def test_quick_edit_is_cleared_and_extended_flags_set(self):
        k32 = self._Kernel32(mode=0x1F7)  # QuickEdit (0x40) + extended flags (0x80) + others
        self.assertTrue(disable_console_quick_edit(kernel32=k32))
        self.assertEqual(k32.set_calls, [(0x1F7 & ~0x40) | 0x80])

    def test_no_console_is_a_no_op(self):
        k32 = self._Kernel32(mode=0, console=False)
        self.assertFalse(disable_console_quick_edit(kernel32=k32))
        self.assertEqual(k32.set_calls, [])


class MainWiringTests(unittest.TestCase):
    def test_backend_main_installs_nonblocking_logging_and_quick_edit_off(self):
        import inspect
        from terminal.runtime import paper_http_server

        source = inspect.getsource(paper_http_server.main)
        self.assertIn("install_nonblocking_console_logging(", source)
        self.assertIn("disable_console_quick_edit()", source)
        self.assertNotIn("logging.basicConfig", source)


if __name__ == "__main__":
    unittest.main()
