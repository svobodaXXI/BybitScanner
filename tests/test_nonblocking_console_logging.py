"""A3-R8 focused regression: a hung console writer must not stop the PAPER owner.

Reproduces the 2026-10-12 dump: after a slow owner task the owner thread logged
"Slow PAPER owner task" and stayed inside WriteConsoleW, so no later task ran.
The console stream below is a stub whose write() blocks until released.
"""
import io
import logging
import threading
import time
import unittest

from terminal.runtime import paper_http_server
from terminal.runtime.paper_http_server import (
    SLOW_OWNER_TASK_WARNING_MS, SerializedPaperRuntime, _install_console_log_queue,
)

FORMAT = "%(levelname)s %(name)s %(message)s"


class _HungConsole:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.text = []

    def write(self, text):
        self.entered.set()
        self.release.wait(10)
        self.text.append(text)

    def flush(self):
        pass


class _StubRuntime:
    def close(self):
        pass


class ConsoleLogQueueTests(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        saved = (root.handlers[:], root.level)

        def restore():
            root.handlers[:] = saved[0]
            root.setLevel(saved[1])
        self.addCleanup(restore)

    def install(self, stream, **kwargs):
        listener = _install_console_log_queue("INFO", FORMAT, stream=stream, **kwargs)
        return listener

    def test_owner_keeps_processing_tasks_while_the_console_writer_hangs(self):
        console = _HungConsole()
        listener = self.install(console)
        self.addCleanup(listener.stop)
        self.addCleanup(console.release.set)  # cleanups run LIFO: release first, then stop
        logging.getLogger("warmup").warning("occupies the console writer")
        self.assertTrue(console.entered.wait(2))  # the only console writer is now stuck

        owner = SerializedPaperRuntime(_StubRuntime)
        self.addCleanup(owner.close)
        slow_s = (SLOW_OWNER_TASK_WARNING_MS + 100.0) / 1000.0
        owner.call(lambda runtime: time.sleep(slow_s), timeout=5)  # logs "Slow PAPER owner task"
        started = time.perf_counter()
        results = [owner.call(lambda runtime, i=i: i, timeout=2) for i in range(20)]
        self.assertEqual(results, list(range(20)))
        self.assertLess(time.perf_counter() - started, 2.0)
        self.assertGreaterEqual(owner.protection_ingress_metrics()["slowest_task_ms"], SLOW_OWNER_TASK_WARNING_MS)

    def test_full_queue_drops_records_without_blocking(self):
        console = _HungConsole()
        listener = self.install(console, queue_size=10)

        def drain_then_stop():
            console.release.set()
            deadline = time.monotonic() + 5
            while listener.queue.qsize() and time.monotonic() < deadline:
                time.sleep(0.01)
            listener.stop()
        self.addCleanup(drain_then_stop)
        log = logging.getLogger("terminal.runtime.paper_http_server")
        log.warning("occupies the console writer")
        self.assertTrue(console.entered.wait(2))
        started = time.perf_counter()
        for i in range(2000):
            log.warning("record %d", i)
        self.assertLess(time.perf_counter() - started, 1.0)
        self.assertLessEqual(listener.queue.qsize(), 10)

    def test_records_reach_the_console_in_order_with_exception_text(self):
        stream = io.StringIO()
        listener = self.install(stream)
        log = logging.getLogger("terminal.runtime.paper_http_server")
        for i in range(3):
            log.warning("message %d", i)
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            log.exception("failure")
        listener.stop()  # drains the queue
        text = stream.getvalue()
        self.assertEqual([line for line in text.splitlines() if "message" in line],
                         [f"WARNING terminal.runtime.paper_http_server message {i}" for i in range(3)])
        self.assertIn("RuntimeError: boom", text)
        self.assertTrue(listener._thread is None)

    def test_listener_thread_is_a_daemon(self):
        listener = self.install(io.StringIO())
        self.addCleanup(listener.stop)
        self.assertTrue(listener._thread.daemon)

    def test_backend_main_uses_the_queue_instead_of_basic_config(self):
        import inspect
        source = inspect.getsource(paper_http_server.main)
        self.assertIn("_install_console_log_queue(", source)
        self.assertNotIn("logging.basicConfig", source)


if __name__ == "__main__":
    unittest.main()
